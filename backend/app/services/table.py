"""Table detection and text structuring.

Two strategies:

1. **Grid detection** — detect horizontal and vertical lines with OpenCV
   morphology, reconstruct the grid from their intersections, and map OCR words
   into the cell that contains their centroid.
2. **Fallback** — when no reliable grid is found, structure the text line by
   line, splitting each line into columns on whitespace gaps.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.logging_config import get_logger
from app.services.ocr import OcrResult, Word

log = get_logger(__name__)

# A structured page is a 2D list of cells. Each cell is a (text, confidence).
Cell = tuple[str, float]
Grid = list[list[Cell]]


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


def _find_grid_lines(image_path: Path) -> tuple[list[int], list[int]]:
    """Return the (x-columns, y-rows) grid line coordinates for an image."""
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return [], []

    binary = cv2.adaptiveThreshold(
        image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 10
    )
    h, w = binary.shape

    horizontal = _detect_lines(binary, horizontal=True)
    vertical = _detect_lines(binary, horizontal=False)

    # Column boundaries from vertical lines.
    col_positions: list[int] = []
    cols = cv2.findNonZero(vertical)
    if cols is not None:
        col_positions = [pt[0][0] for pt in cols]
    # Row boundaries from horizontal lines.
    row_positions: list[int] = []
    rows = cv2.findNonZero(horizontal)
    if rows is not None:
        row_positions = [pt[0][1] for pt in rows]

    x_lines = _cluster_positions(col_positions, min_gap=max(15, w // 60))
    y_lines = _cluster_positions(row_positions, min_gap=max(15, h // 60))
    return x_lines, y_lines


def _map_words_to_grid(words: list[Word], x_lines: list[int], y_lines: list[int]) -> Grid:
    """Place each OCR word into the cell whose bounds contain its centroid."""
    n_cols = len(x_lines) - 1
    n_rows = len(y_lines) - 1
    grid_text: list[list[list[str]]] = [
        [[] for _ in range(n_cols)] for _ in range(n_rows)
    ]
    grid_conf: list[list[list[float]]] = [
        [[] for _ in range(n_cols)] for _ in range(n_rows)
    ]

    def _bucket(value: int, lines: list[int]) -> int | None:
        for i in range(len(lines) - 1):
            if lines[i] <= value < lines[i + 1]:
                return i
        return None

    for word in words:
        cx = word.left + word.width // 2
        cy = word.top + word.height // 2
        col = _bucket(cx, x_lines)
        row = _bucket(cy, y_lines)
        if col is None or row is None:
            continue
        grid_text[row][col].append(word.text)
        grid_conf[row][col].append(word.confidence)

    grid: Grid = []
    for r in range(n_rows):
        row_cells: list[Cell] = []
        for c in range(n_cols):
            text = " ".join(grid_text[r][c])
            confs = grid_conf[r][c]
            conf = sum(confs) / len(confs) if confs else 0.0
            row_cells.append((text, conf))
        grid.append(row_cells)

    # Drop fully empty rows.
    return [row for row in grid if any(cell[0].strip() for cell in row)]


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


def structure_page(image_path: Path, ocr_result: OcrResult) -> Grid:
    """Structure a page's OCR words into a 2D grid of cells.

    Attempts grid detection first; falls back to line-by-line structuring when
    no usable table grid is detected.

    Args:
        image_path: Path to the page image used for line detection.
        ocr_result: OCR output for the same page.

    Returns:
        A 2D grid of ``(text, confidence)`` cells.
    """
    x_lines, y_lines = _find_grid_lines(image_path)

    if len(x_lines) >= 3 and len(y_lines) >= 3:
        grid = _map_words_to_grid(ocr_result.words, x_lines, y_lines)
        if grid and any(cell[0].strip() for row in grid for cell in row):
            log.info("table.detected", cols=len(x_lines) - 1, rows=len(y_lines) - 1)
            return grid

    log.info("table.fallback", reason="no_grid")
    return _structure_by_lines(ocr_result.words)
