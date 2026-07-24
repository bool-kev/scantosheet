"""Table detection and text structuring.

Strategy (precision-focused):

1. **Line masks** — detect horizontal and vertical rules with OpenCV morphology.
2. **Table region(s)** — a table exists only where horizontal *and* vertical
   rules coexist. The bounding box of each such region is isolated so that any
   text *outside* it (titles, headers, footers, paragraphs before/after the
   table) is discarded.
3. **Grid mapping** — within each region, cluster the rules into grid lines and
   map every OCR word into the cell that contains its centroid. Words whose
   centroid falls outside the grid are dropped. Adjacent sub-cells with no rule
   between them are treated as one merged cell: its text is filled into the
   leftmost column of every row it spans, so a vertically-merged cell reads
   correctly on every row and a horizontally-merged cell isn't duplicated.
4. **Fallback** — only when ``tables_only`` is disabled and no grid is found, the
   whole page is structured line by line.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.logging_config import get_logger
from app.services.ocr import OcrResult, Word

log = get_logger(__name__)

# Cap on the continuous pixel run _segment_has_rule requires to call a cell
# boundary a rule (see its docstring): long enough that no text glyph run
# could be mistaken for one, short enough to tolerate the small dropouts real
# scanned rules have over a long span.
_MAX_KERNEL_LEN = 60

# A structured page is a 2D list of cells. Each cell is a (text, confidence).
Cell = tuple[str, float]
Grid = list[list[Cell]]
Box = tuple[int, int, int, int]  # (x, y, width, height)


def _detect_lines(binary: np.ndarray, horizontal: bool) -> np.ndarray:
    """Extract horizontal or vertical lines from a binary (inverted) image."""
    h, w = binary.shape
    if horizontal:
        size = max(10, w // 30)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (size, 1))
    else:
        size = max(10, h // 30)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, size))
    eroded = cv2.erode(binary, kernel, iterations=1)
    return cv2.dilate(eroded, kernel, iterations=1)


def _cluster_positions(positions: list[int], min_gap: int) -> list[int]:
    """Merge nearby coordinates into representative grid lines."""
    if not positions:
        return []
    positions = sorted(positions)
    clusters: list[list[int]] = [[positions[0]]]
    for p in positions[1:]:
        if p - clusters[-1][-1] <= min_gap:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    return [int(sum(c) / len(c)) for c in clusters]


def _line_masks(
    image_path: Path,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple[int, int]] | None:
    """Return (horizontal_mask, vertical_mask, binary, (h, w)) for a page image.

    ``binary`` is the raw thresholded image the two rule masks were derived
    from; it is kept around because the page-wide erosion used to build those
    masks is tuned to find long, table-spanning rules and can erode away a
    short rule that only spans a single cell (see ``_segment_has_rule``, which
    re-derives presence locally, scaled to the segment being tested).
    """
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return None
    binary = cv2.adaptiveThreshold(
        image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 10
    )
    horizontal = _detect_lines(binary, horizontal=True)
    vertical = _detect_lines(binary, horizontal=False)
    return horizontal, vertical, binary, binary.shape[:2]


def _grid_lines_in_box(
    horizontal: np.ndarray, vertical: np.ndarray, box: Box
) -> tuple[list[int], list[int]]:
    """Cluster the rules inside a box into (x-columns, y-rows) grid lines.

    Coordinates are returned in the full-image frame.
    """
    x, y, bw, bh = box
    vsub = vertical[y : y + bh, x : x + bw]
    hsub = horizontal[y : y + bh, x : x + bw]

    col_positions: list[int] = []
    cols = cv2.findNonZero(vsub)
    if cols is not None:
        col_positions = (cols.reshape(-1, 2)[:, 0] + x).tolist()
    row_positions: list[int] = []
    rows = cv2.findNonZero(hsub)
    if rows is not None:
        row_positions = (rows.reshape(-1, 2)[:, 1] + y).tolist()

    x_lines = _cluster_positions(col_positions, min_gap=max(15, bw // 60))
    y_lines = _cluster_positions(row_positions, min_gap=max(15, bh // 60))
    return x_lines, y_lines


def _detect_table_boxes(
    horizontal: np.ndarray, vertical: np.ndarray, shape: tuple[int, int]
) -> list[tuple[Box, list[int], list[int]]]:
    """Detect table regions as bounding boxes with their inner grid lines.

    A region qualifies as a table only if, within its bounds, at least 2 columns
    (3 vertical lines) and 2 rows (3 horizontal lines) are present. This rejects
    lone underlines, signature rules and page borders.

    Returns:
        A list of ``(box, x_lines, y_lines)`` ordered top-to-bottom, one per
        detected table.
    """
    h, w = shape
    mask = cv2.add(horizontal, vertical)
    # Close small gaps so a broken grid still yields a single contour.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    detected: list[tuple[Box, list[int], list[int]]] = []
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        # Ignore regions too small to be a meaningful table.
        if bw < w * 0.15 or bh < h * 0.04:
            continue
        x_lines, y_lines = _grid_lines_in_box(horizontal, vertical, (x, y, bw, bh))
        if len(x_lines) >= 3 and len(y_lines) >= 3:
            detected.append(((x, y, bw, bh), x_lines, y_lines))

    detected.sort(key=lambda item: (item[0][1], item[0][0]))
    return detected


def _bucket(value: int, lines: list[int]) -> int | None:
    """Return the index of the [lines[i], lines[i+1]) span containing value."""
    for i in range(len(lines) - 1):
        if lines[i] <= value < lines[i + 1]:
            return i
    return None


def _segment_has_rule(
    binary: np.ndarray,
    pos: int,
    span_start: int,
    span_end: int,
    axis: str,
    band: int = 20,
    min_ratio: float = 0.5,
) -> bool:
    """Return True if a rule spans (most of) one specific cell boundary segment.

    Unlike the page-wide ``horizontal``/``vertical`` masks (eroded with a kernel
    sized for the whole page, which can erase a rule that only spans a single
    cell), this samples a thin strip of the raw binary image around the
    boundary and applies a morphological opening with a kernel scaled to the
    segment's own length. Only a run of foreground pixels at least
    ``min_ratio`` of the segment length survives the opening, which reliably
    tells a real cell-boundary rule apart from stray text pixels (far shorter
    than the segment) without needing a hand-tuned coverage threshold.

    Args:
        binary: The raw thresholded page image (foreground = "on" pixels).
        pos: Pixel coordinate of the boundary (x for a vertical border, y for a
            horizontal one).
        span_start: Start of the boundary segment along the other axis.
        span_end: End of the boundary segment along the other axis.
        axis: ``"v"`` for a vertical border (between two columns), ``"h"`` for a
            horizontal border (between two rows).
        band: Half-width (in pixels) of the strip sampled around ``pos``. Wider
            than a single hairline rule on purpose: ``pos`` comes from
            clustering rule pixels over the *whole* table, and a long column's
            true rule can drift well past a hairline's width from that average
            (page warp, residual skew) by the time it reaches the row being
            tested — this was observed up to ~16px on a real scan.
        min_ratio: Fraction of the segment length the kernel requires, up to
            ``_MAX_KERNEL_LEN``. A long segment (e.g. a 950px-wide column)
            would otherwise need an implausibly long unbroken run — real
            scanned rules have small pixel dropouts a strict proportional
            requirement keeps failing on — while a run capped at
            ``_MAX_KERNEL_LEN`` is still far longer than any text glyph run
            and long segments stay just as distinguishable from text.
    """
    h, w = binary.shape
    length = span_end - span_start
    if length <= 0:
        return False
    kernel_len = min(max(5, int(length * min_ratio)), _MAX_KERNEL_LEN)

    if axis == "v":
        x0, x1 = max(0, pos - band), min(w, pos + band + 1)
        y0, y1 = max(0, span_start), min(h, span_end)
        if x1 <= x0 or y1 <= y0:
            return False
        strip = binary[y0:y1, x0:x1]
        klen = min(kernel_len, strip.shape[0])
        if klen < 1:
            return False
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, klen))
    else:
        y0, y1 = max(0, pos - band), min(h, pos + band + 1)
        x0, x1 = max(0, span_start), min(w, span_end)
        if x1 <= x0 or y1 <= y0:
            return False
        strip = binary[y0:y1, x0:x1]
        klen = min(kernel_len, strip.shape[1])
        if klen < 1:
            return False
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (klen, 1))

    if strip.size == 0:
        return False
    opened = cv2.morphologyEx(strip, cv2.MORPH_OPEN, kernel)
    return bool(np.count_nonzero(opened))


def _detect_borders(
    binary: np.ndarray, x_lines: list[int], y_lines: list[int]
) -> tuple[np.ndarray, np.ndarray]:
    """Detect which internal grid boundaries are actually drawn as rules.

    Returns:
        ``v_border[r, c]`` is True if a vertical rule separates column ``c``
        from column ``c + 1`` in row ``r`` (shape ``n_rows x (n_cols - 1)``).
        ``h_border[r, c]`` is True if a horizontal rule separates row ``r`` from
        row ``r + 1`` in column ``c`` (shape ``(n_rows - 1) x n_cols``).
    """
    n_cols = len(x_lines) - 1
    n_rows = len(y_lines) - 1

    v_border = np.ones((n_rows, max(n_cols - 1, 0)), dtype=bool)
    for r in range(n_rows):
        y0, y1 = y_lines[r], y_lines[r + 1]
        for c in range(n_cols - 1):
            v_border[r, c] = _segment_has_rule(binary, x_lines[c + 1], y0, y1, axis="v")

    h_border = np.ones((max(n_rows - 1, 0), n_cols), dtype=bool)
    for c in range(n_cols):
        x0, x1 = x_lines[c], x_lines[c + 1]
        for r in range(n_rows - 1):
            h_border[r, c] = _segment_has_rule(binary, y_lines[r + 1], x0, x1, axis="h")

    return v_border, h_border


def _merge_roots(n_rows: int, n_cols: int, v_border: np.ndarray, h_border: np.ndarray) -> list[int]:
    """Union-find over flattened cell indices, merging cells with no rule between them.

    Returns the root index (row * n_cols + col) for every cell, so cells
    belonging to the same merged region share the same root.
    """
    parent = list(range(n_rows * n_cols))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)

    for r in range(n_rows):
        for c in range(n_cols - 1):
            if not v_border[r, c]:
                union(r * n_cols + c, r * n_cols + c + 1)
    for c in range(n_cols):
        for r in range(n_rows - 1):
            if not h_border[r, c]:
                union(r * n_cols + c, (r + 1) * n_cols + c)

    return [find(i) for i in range(n_rows * n_cols)]


def _break_malformed_regions(roots: list[int], n_rows: int, n_cols: int) -> list[int]:
    """Undo any merged region that isn't a filled rectangle.

    A real merged table cell is always rectangular. A non-rectangular region
    can only arise from a false-negative border somewhere in the grid: since
    the "no rule between them" union is transitive, one missed border on an
    otherwise-legitimate long merge chain (e.g. a whole DATE column merged top
    to bottom) can weld it to unrelated cells elsewhere in the row. Rather than
    trust a shape that shouldn't exist, split every cell of such a region back
    into its own singleton — worst case, that handful of cells falls back to
    the unmerged behavior instead of corrupting the page.
    """
    members: dict[int, list[tuple[int, int]]] = {}
    for idx, root in enumerate(roots):
        members.setdefault(root, []).append(divmod(idx, n_cols))

    fixed = list(roots)
    for root, cells in members.items():
        if len(cells) <= 1:
            continue
        r_vals = {r for r, _ in cells}
        c_vals = {c for _, c in cells}
        r_min, r_max = min(r_vals), max(r_vals)
        c_min, c_max = min(c_vals), max(c_vals)
        expected = {
            (r, c) for r in range(r_min, r_max + 1) for c in range(c_min, c_max + 1)
        }
        if set(cells) != expected:
            for r, c in cells:
                fixed[r * n_cols + c] = r * n_cols + c

    return fixed


def _map_words_to_grid(
    words: list[Word],
    x_lines: list[int],
    y_lines: list[int],
    binary: np.ndarray,
) -> Grid:
    """Place each OCR word into its cell, honoring merged (spanned) cells.

    Cells separated by no detected rule are treated as one merged region: its
    text is written into the leftmost column of every row it spans (so each row
    stays self-contained, e.g. for a vertical merge), and nowhere else (so a
    horizontal merge's text isn't duplicated across the columns it spans).

    Words whose centroid falls outside the [min, max] span of the grid lines are
    ignored, so text surrounding the table never leaks into the result.
    """
    n_cols = len(x_lines) - 1
    n_rows = len(y_lines) - 1
    if n_cols <= 0 or n_rows <= 0:
        return []

    v_border, h_border = _detect_borders(binary, x_lines, y_lines)
    roots = _merge_roots(n_rows, n_cols, v_border, h_border)
    roots = _break_malformed_regions(roots, n_rows, n_cols)

    region_col_min: dict[int, int] = {}
    for idx, root in enumerate(roots):
        c = idx % n_cols
        region_col_min[root] = min(region_col_min.get(root, c), c)

    region_text: dict[int, list[str]] = {}
    region_conf: dict[int, list[float]] = {}
    for word in words:
        cx = word.left + word.width // 2
        cy = word.top + word.height // 2
        col = _bucket(cx, x_lines)
        row = _bucket(cy, y_lines)
        if col is None or row is None:
            continue
        root = roots[row * n_cols + col]
        region_text.setdefault(root, []).append(word.text)
        region_conf.setdefault(root, []).append(word.confidence)

    grid: Grid = []
    for r in range(n_rows):
        row_cells: list[Cell] = []
        for c in range(n_cols):
            root = roots[r * n_cols + c]
            if region_col_min[root] == c:
                texts = region_text.get(root, [])
                confs = region_conf.get(root, [])
                text = " ".join(texts)
                conf = sum(confs) / len(confs) if confs else 0.0
            else:
                text, conf = "", 0.0
            row_cells.append((text, conf))
        grid.append(row_cells)

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


def _concat_grids(grids: list[Grid]) -> Grid:
    """Stack multiple table grids vertically, padding to a common width."""
    if len(grids) == 1:
        return grids[0]
    width = max((len(row) for grid in grids for row in grid), default=0)
    combined: Grid = []
    for grid in grids:
        for row in grid:
            padded = list(row) + [("", 0.0)] * (width - len(row))
            combined.append(padded)
    return combined


def _structure_by_lines(words: list[Word]) -> Grid:
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
        cells: list[Cell] = []
        current: list[Word] = []
        prev_right: int | None = None
        for word in row_words:
            if prev_right is not None and (word.left - prev_right) > gap_threshold:
                cells.append(_merge_cell(current))
                current = []
            current.append(word)
            prev_right = word.left + word.width
        if current:
            cells.append(_merge_cell(current))
        if cells:
            grid.append(cells)

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

    Isolates bordered table regions and keeps only the words inside them. When
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
    masks = _line_masks(image_path)
    if masks is not None:
        horizontal, vertical, binary, shape = masks
        tables = _detect_table_boxes(horizontal, vertical, shape)
        grids: list[Grid] = []
        for _box, x_lines, y_lines in tables:
            grid = _map_words_to_grid(ocr_result.words, x_lines, y_lines, binary)
            if grid:
                grids.append(grid)
        if grids:
            combined = _concat_grids(grids)
            log.info(
                "table.detected",
                tables=len(grids),
                rows=len(combined),
                cols=max((len(r) for r in combined), default=0),
            )
            return combined

    if tables_only:
        log.info("table.none", note="no table region detected; free text ignored")
        return []

    log.info("table.fallback", reason="no_grid")
    return _structure_by_lines(ocr_result.words)
