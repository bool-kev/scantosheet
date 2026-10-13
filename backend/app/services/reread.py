"""Targeted second OCR passes over the table cells the page-wide pass got wrong.

Three passes, each cheap because it only touches the cells that need it:

* ``reread_weak_cells`` — cells left empty or read with low confidence are
  read again on their own, cropped tightly around their ink.
* ``reread_numeric_columns`` — in a column of numbers, a cell that is not a
  number is read again with recognition restricted to digits.
* ``reread_tally_columns`` — in a column of roman I/II/III, strokes are
  counted in the image instead of being recognised.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import cv2
import numpy as np

from app.config import get_settings
from app.services import ocr, table
from app.services.ocr import Word
from app.services.table import CellContent

# Margin (px) trimmed off each side of a cell before re-reading it, so no
# residue of its border rules enters the crop.
_CELL_INSET = 6
# A pixel is ink when this much darker than the cell's background; pale gray
# print on white paper still clears it, paper grain and JPEG noise do not.
_INK_CONTRAST = 60
_MIN_INK_PIXELS = 30
_INK_MARGIN = 12
# A column counts as numeric when it has at least this many filled cells and
# this share of them are plain numbers; its other short cells are re-read as
# digits, and the digits are kept only if read with this confidence.
_MIN_NUMERIC_CELLS = 3
_NUMERIC_SHARE = 0.6
_MAX_SUSPECT_LENGTH = 6
_MIN_DIGIT_CONFIDENCE = 60
# Characters a roman-numeral tally (I, II, III) is read as, and how its strokes
# are counted: a stroke inks at least this share of the glyph height.
_TALLY_CHARS = frozenset("Il|!1Ti")
_STROKE_FILL = 0.7
_MAX_STROKES = 3
_TALLY_CONFIDENCE = 95.0


def _crop(image: np.ndarray, content: CellContent) -> np.ndarray:
    box = content.box
    return image[
        box.y + _CELL_INSET : box.y + box.height - _CELL_INSET,
        box.x + _CELL_INSET : box.x + box.width - _CELL_INSET,
    ]


def _ink_bounds(crop: np.ndarray) -> tuple[int, int, int, int] | None:
    """Return the (x0, y0, x1, y1) box around a crop's ink, or None if blank."""
    if crop.size == 0:
        return None
    background = float(np.percentile(crop, 90))
    ink = (crop < background - _INK_CONTRAST).astype(np.uint8)
    ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    if int(ink.sum()) < _MIN_INK_PIXELS:
        return None
    ys, xs = np.nonzero(ink)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _reread(
    image: np.ndarray, content: CellContent, language: str, line_height: float
) -> list[Word] | None:
    """Re-OCR one cell alone; return its words if they beat the first pass.

    The crop is tightened around the cell's ink and the segmentation mode is
    chosen from the ink's size: a lone character or a single line is told so,
    which is what makes a stray ``6`` or ``II`` in a large cell readable.
    """
    located = _tight_crop(image, content)
    if located is None:
        return None
    tight, dx, dy = located
    ink_w, ink_h = tight.shape[1] - 2 * _INK_MARGIN, tight.shape[0] - 2 * _INK_MARGIN
    if ink_h > 1.8 * line_height:
        modes = (ocr.PSM_BLOCK,)
    elif ink_w > 0.8 * ink_h:
        modes = (ocr.PSM_LINE, ocr.PSM_BLOCK)
    else:
        modes = (ocr.PSM_CHAR, ocr.PSM_LINE)

    words: list[Word] = []
    for mode in modes:
        words = ocr.read_region(tight, lang=language, psm=mode)
        if words:
            break
    if not words:
        return None
    words = [replace(w, left=w.left + dx, top=w.top + dy) for w in words]
    words = [w for w in words if not table.is_noise(w, line_height)]
    if not words:
        return None
    confidence = sum(w.confidence for w in words) / len(words)
    if content.words and confidence <= content.confidence:
        return None
    return words


def _tight_crop(
    image: np.ndarray, content: CellContent
) -> tuple[np.ndarray, int, int] | None:
    """Crop a cell around its ink; return (crop, x offset, y offset) or None."""
    crop = _crop(image, content)
    bounds = _ink_bounds(crop)
    if bounds is None:
        return None
    x0, y0 = max(0, bounds[0] - _INK_MARGIN), max(0, bounds[1] - _INK_MARGIN)
    tight = crop[y0 : bounds[3] + _INK_MARGIN, x0 : bounds[2] + _INK_MARGIN]
    return tight, content.box.x + _CELL_INSET + x0, content.box.y + _CELL_INSET + y0


def _is_number(text: str) -> bool:
    return text.isdigit()


def reread_numeric_columns(
    image: np.ndarray, contents: list[CellContent], language: str
) -> int:
    """Re-read as digits the odd cells of columns that hold numbers.

    When most cells of a column are plain numbers, a cell read as ``LS`` or
    left empty is almost certainly a number too (``15``). Reading it again
    with Tesseract restricted to digits settles it. The header row is skipped.

    Returns:
        The number of cells whose content was replaced.
    """
    columns: dict[int, list[CellContent]] = {}
    for content in contents:
        if content.box.row > 0 and content.box.colspan == 1:
            columns.setdefault(content.box.col, []).append(content)

    suspects: list[CellContent] = []
    for column in columns.values():
        filled = [c for c in column if c.words]
        numeric = [c for c in filled if _is_number(c.text)]
        if len(filled) < _MIN_NUMERIC_CELLS or len(numeric) < _NUMERIC_SHARE * len(filled):
            continue
        suspects.extend(
            c for c in column if not _is_number(c.text) and len(c.text) <= _MAX_SUSPECT_LENGTH
        )

    def read_digits(content: CellContent) -> list[Word] | None:
        located = _tight_crop(image, content)
        if located is None:
            return None
        tight, dx, dy = located
        words = ocr.read_region(tight, lang=language, psm=ocr.PSM_LINE, digits_only=True)
        if not words or any(w.confidence < _MIN_DIGIT_CONFIDENCE for w in words):
            return None
        return [replace(w, left=w.left + dx, top=w.top + dy) for w in words]

    if not suspects:
        return 0
    with ThreadPoolExecutor(max_workers=get_settings().max_workers) as pool:
        results = list(pool.map(read_digits, suspects))
    replaced = 0
    for content, words in zip(suspects, results):
        if words is not None:
            content.words = words
            replaced += 1
    return replaced


def reread_weak_cells(
    image: np.ndarray, contents: list[CellContent], language: str, line_height: float
) -> int:
    """Re-read, in parallel, the cells the page-wide pass left empty or unsure.

    Returns:
        The number of cells whose content was replaced.
    """
    settings = get_settings()
    weak = [
        c
        for c in contents
        if not c.words or c.confidence < settings.ocr_reread_confidence
    ]
    if not weak:
        return 0
    with ThreadPoolExecutor(max_workers=settings.max_workers) as pool:
        results = list(pool.map(lambda c: _reread(image, c, language, line_height), weak))

    replaced = 0
    for content, words in zip(weak, results):
        if words is not None:
            content.words = words
            replaced += 1
    return replaced


def _count_strokes(crop: np.ndarray) -> int:
    """Count the vertical strokes of a crop holding only a tally such as ``II``."""
    bounds = _ink_bounds(crop)
    if bounds is None:
        return 0
    x0, y0, x1, y1 = bounds
    background = float(np.percentile(crop, 90))
    ink = crop[y0:y1, x0:x1] < background - _INK_CONTRAST
    # A stroke is a run of columns inked over most of the glyph height; the
    # serifs joining two strokes ink only a thin band and do not count.
    tall = ink.sum(axis=0) >= _STROKE_FILL * (y1 - y0)
    return int(np.count_nonzero(tall[1:] & ~tall[:-1]) + int(tall[0]))


def reread_tally_columns(image: np.ndarray, contents: list[CellContent]) -> int:
    """Re-read by stroke counting the columns that hold only roman I, II, III.

    OCR cannot tell a lone ``I`` from ``l``, ``|`` or ``1``, and reads ``II``
    as ``Il`` or ``IT``. When every cell of a column is such a mark, counting
    the vertical strokes in the image is exact where recognition is a guess.

    Returns:
        The number of cells whose content was replaced.
    """
    columns: dict[int, list[CellContent]] = {}
    for content in contents:
        if content.box.row > 0 and content.box.colspan == 1:
            columns.setdefault(content.box.col, []).append(content)

    replaced = 0
    for column in columns.values():
        filled = [c for c in column if c.words]
        if len(filled) < _MIN_NUMERIC_CELLS:
            continue
        if not all(set(c.text.replace(" ", "")) <= _TALLY_CHARS for c in filled):
            continue
        for content in column:
            strokes = _count_strokes(_crop(image, content))
            if not 1 <= strokes <= _MAX_STROKES:
                continue
            text = "I" * strokes
            if content.text != text:
                box = content.box
                content.words = [
                    Word(
                        text=text,
                        confidence=_TALLY_CONFIDENCE,
                        left=box.x,
                        top=box.y,
                        width=box.width,
                        height=box.height,
                        line_num=1,
                        block_num=1,
                        par_num=1,
                    )
                ]
                replaced += 1
    return replaced
