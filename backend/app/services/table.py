"""Table structuring: turn detected cells and OCR words into a 2D grid.

Strategy (precision-focused):

1. **Layout** — ``cells.detect_tables`` finds every drawn cell of every ruled
   table and gives it a logical row/column position and span.
2. **Word mapping** — each OCR word goes to the cell whose box contains its
   centroid. Words outside every cell (titles, footers, paragraphs around the
   table) are dropped.
3. **Grid** — a cell merged over several rows is repeated on every row it
   spans, so each row stays self-contained for import; a cell merged over
   several columns is written once, in its leftmost column.
4. **Fallback** — only when ``tables_only`` is disabled and no table is found,
   the whole page is structured line by line.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2

from app.logging_config import get_logger
from app.services import cells
from app.services.cells import CellBox, TableLayout
from app.services.ocr import OcrResult, Word

log = get_logger(__name__)

# A structured page is a 2D list of cells. Each cell is a (text, confidence).
Cell = tuple[str, float]
Grid = list[list[Cell]]

# Characters a ruling-line or stamp leftover is read as. "|" is deliberately
# absent: at text height it is as likely a roman numeral I, and a leftover of
# a vertical rule is caught by the height checks instead.
_RULE_RESIDUE = frozenset("\\_=~")
# A word is debris when its height is outside these multiples of the page's
# typical word height...
_MIN_HEIGHT_RATIO = 0.3
_MAX_HEIGHT_RATIO = 2.5
# ...or when it is this short and read this unsurely.
_NOISE_CONFIDENCE = 45
_NOISE_MAX_LETTERS = 4


@dataclass
class CellContent:
    """The OCR words that fell inside one cell."""

    box: CellBox
    words: list[Word] = field(default_factory=list)

    @property
    def text(self) -> str:
        """Cell text in reading order (lines top-to-bottom, words left-to-right)."""
        return " ".join(w.text for w in _reading_order(self.words))

    @property
    def confidence(self) -> float:
        """Mean OCR confidence of the cell's words (0 when empty)."""
        if not self.words:
            return 0.0
        return sum(w.confidence for w in self.words) / len(self.words)


def _reading_order(words: list[Word]) -> list[Word]:
    """Order words as text lines, without trusting OCR line numbers.

    Tesseract numbers lines across the whole page, so the words of one cell
    can carry interleaved line numbers; geometry is reliable instead.
    """
    if not words:
        return []
    heights = sorted(w.height for w in words)
    tolerance = heights[len(heights) // 2] * 0.6

    lines: list[list[Word]] = []
    for word in sorted(words, key=lambda w: w.top + w.height / 2):
        centre = word.top + word.height / 2
        if lines:
            last = lines[-1]
            last_centre = sum(w.top + w.height / 2 for w in last) / len(last)
            if abs(centre - last_centre) <= tolerance:
                last.append(word)
                continue
        lines.append([word])
    return [w for line in lines for w in sorted(line, key=lambda w: w.left)]


def is_noise(word: Word, line_height: float) -> bool:
    """Return True if an OCR word is debris rather than printed text.

    Three kinds of debris show up inside table cells: leftovers of ruling
    lines (``|``, ``_``), marks whose size is nothing like a line of text
    (specks, or a stamp read as one giant glyph), and short low-confidence
    fragments, which is how a stamp or signature crossing the text is read.
    A long word read with low confidence is kept: it is usually real text.
    """
    text = word.text
    if all(ch in _RULE_RESIDUE for ch in text):
        return True
    letters = sum(ch.isalnum() for ch in text)
    if line_height > 0:
        if word.height > _MAX_HEIGHT_RATIO * line_height:
            return True
        if letters and word.height < _MIN_HEIGHT_RATIO * line_height:
            return True
    return word.confidence < _NOISE_CONFIDENCE and letters <= _NOISE_MAX_LETTERS


def map_words(
    layout: TableLayout, words: list[Word], line_height: float = 0.0
) -> list[CellContent]:
    """Assign each OCR word to the cell containing its centroid.

    Args:
        layout: The table whose cells receive the words.
        words: OCR words of the page.
        line_height: Typical word height on the page, used to discard debris
            (see ``is_noise``); 0 disables the size checks.

    Returns:
        One ``CellContent`` per cell of the layout, in the layout's order.
    """
    contents = [CellContent(box=box) for box in layout.cells]
    for word in words:
        if is_noise(word, line_height):
            continue
        cx = word.left + word.width // 2
        cy = word.top + word.height // 2
        for content in contents:
            if content.box.contains(cx, cy):
                content.words.append(word)
                break
    return contents


def build_grid(layout: TableLayout, contents: list[CellContent]) -> Grid:
    """Write cell contents onto the layout's logical grid.

    A vertically merged cell is repeated on each row it spans; a horizontally
    merged one is written only in its leftmost column.
    """
    grid: Grid = [[("", 0.0)] * layout.n_cols for _ in range(layout.n_rows)]
    for content in contents:
        box = content.box
        value = (content.text, content.confidence)
        if not value[0] or box.col >= layout.n_cols:
            continue
        for row in range(box.row, min(box.row + box.rowspan, layout.n_rows)):
            grid[row][box.col] = value
    return _trim_empty(grid)


def _trim_empty(grid: Grid) -> Grid:
    """Drop fully empty rows and fully empty columns (e.g. margin gutters)."""
    grid = [row for row in grid if any(cell[0].strip() for cell in row)]
    if not grid:
        return []
    n_cols = max(len(row) for row in grid)
    keep_cols = [
        c
        for c in range(n_cols)
        if any(c < len(row) and row[c][0].strip() for row in grid)
    ]
    return [[row[c] if c < len(row) else ("", 0.0) for c in keep_cols] for row in grid]


def concat_grids(grids: list[Grid]) -> Grid:
    """Stack multiple table grids vertically, padding to a common width."""
    if len(grids) == 1:
        return grids[0]
    width = max((len(row) for grid in grids for row in grid), default=0)
    combined: Grid = []
    for grid in grids:
        for row in grid:
            combined.append(list(row) + [("", 0.0)] * (width - len(row)))
    return combined


def structure_by_lines(words: list[Word]) -> Grid:
    """Fallback: group words by OCR line, split into columns on wide gaps."""
    if not words:
        return []

    lines: dict[tuple[int, int, int], list[Word]] = {}
    for word in words:
        key = (word.block_num, word.par_num, word.line_num)
        lines.setdefault(key, []).append(word)

    # Estimate a "column gap" threshold from median word width.
    widths = sorted(w.width for w in words)
    median_width = widths[len(widths) // 2] if widths else 20
    gap_threshold = max(median_width * 1.5, 30)

    grid: Grid = []
    for key in sorted(lines.keys()):
        row_words = sorted(lines[key], key=lambda w: w.left)
        row: list[Cell] = []
        current: list[Word] = []
        prev_right: int | None = None
        for word in row_words:
            if prev_right is not None and (word.left - prev_right) > gap_threshold:
                row.append(_merge_cell(current))
                current = []
            current.append(word)
            prev_right = word.left + word.width
        if current:
            row.append(_merge_cell(current))
        if row:
            grid.append(row)

    return _pad_rows(grid)


def _merge_cell(words: list[Word]) -> Cell:
    text = " ".join(w.text for w in words)
    conf = sum(w.confidence for w in words) / len(words) if words else 0.0
    return (text, conf)


def _pad_rows(grid: Grid) -> Grid:
    """Pad all rows to the maximum column count with empty cells."""
    if not grid:
        return grid
    width = max(len(row) for row in grid)
    for row in grid:
        while len(row) < width:
            row.append(("", 0.0))
    return grid


def structure_page(
    image_path: Path, ocr_result: OcrResult, tables_only: bool = True
) -> Grid:
    """Structure a page's OCR words into a 2D grid of cells.

    Isolates ruled table regions and keeps only the words inside them. When
    ``tables_only`` is True (default), a page with no detectable table yields no
    data — surrounding free text is intentionally ignored. When False, such a
    page falls back to line-by-line structuring of the whole text.

    Args:
        image_path: Path to the page image used for line detection.
        ocr_result: OCR output for the same page.
        tables_only: If True, ignore everything that is not inside a table.

    Returns:
        A 2D grid of ``(text, confidence)`` cells (possibly empty).
    """
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is not None:
        layouts = cells.detect_tables(cells.find_rules(image))
        grids = [build_grid(layout, map_words(layout, ocr_result.words)) for layout in layouts]
        grids = [grid for grid in grids if grid]
        if grids:
            return concat_grids(grids)

    if tables_only:
        log.info("table.none", note="no table region detected; free text ignored")
        return []

    log.info("table.fallback", reason="no_grid")
    return structure_by_lines(ocr_result.words)
