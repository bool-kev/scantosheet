"""Table layout detection: find each drawn cell and place it on a logical grid.

A ruled table is read as what it literally is — a set of closed boxes. The
ruling lines are extracted with OpenCV morphology, and every connected blank
region they enclose is one cell, whether it is a plain cell or one merged over
several rows/columns. Nothing assumes that a column sits at a single x
coordinate down the whole table, so slanted or slightly warped scans still
yield the right boxes.

The boxes are then snapped onto a logical row/column grid by clustering their
edges, giving each cell a ``row``/``col`` origin and a ``rowspan``/``colspan``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

Box = tuple[int, int, int, int]  # (x, y, width, height)

# Rules shorter than 1/_RULE_DIVISOR of the page side are ignored: text strokes
# are far shorter, while even a single small cell's border is longer.
_RULE_DIVISOR = 55
# A table must be at least this fraction of the page wide / tall.
_MIN_TABLE_WIDTH = 0.15
_MIN_TABLE_HEIGHT = 0.04
# A strip hugging the table edge (within _EDGE px) and thinner than this
# fraction of the table is frame residue rather than a cell.
_EDGE = 6
_SLIVER = 0.012
# A rule standing alone (touching no other rule) is kept only if it runs at
# least this fraction of the page.
_MIN_LONE_RULE = 0.1


@dataclass
class CellBox:
    """One drawn cell: pixel bounds plus its position on the logical grid."""

    x: int
    y: int
    width: int
    height: int
    row: int = 0
    col: int = 0
    rowspan: int = 1
    colspan: int = 1

    def contains(self, px: int, py: int) -> bool:
        """Return True if the pixel (px, py) falls inside this cell."""
        return self.x <= px < self.x + self.width and self.y <= py < self.y + self.height


@dataclass
class TableLayout:
    """A detected table: its bounds, its cells and its logical grid size."""

    box: Box
    cells: list[CellBox] = field(default_factory=list)
    n_rows: int = 0
    n_cols: int = 0


def binarize_inverted(gray: np.ndarray) -> np.ndarray:
    """Threshold a grayscale page so ink is white (255) on black."""
    block = max(15, (min(gray.shape[:2]) // 80) | 1)
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, block, 10
    )


def rule_masks(binary: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Extract the horizontal and vertical ruling lines of a binary page.

    Each mask is opened with a long thin kernel (keeping only long straight
    runs) and then closed along its own direction, so the small dropouts a
    scanned rule always has do not let two neighbouring cells leak together.
    """
    h, w = binary.shape
    masks: list[np.ndarray] = []
    for horizontal in (True, False):
        length = max(12, (w if horizontal else h) // _RULE_DIVISOR)
        size = (length, 1) if horizontal else (1, length)
        # A faint rule thresholds into a dotted line; heal those few-pixel
        # dropouts first or the opening below would discard the whole rule.
        heal = max(3, length // 10)
        healed = cv2.morphologyEx(
            binary,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (heal, 1) if horizontal else (1, heal)),
        )
        mask = cv2.morphologyEx(
            healed, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, size)
        )
        gap = max(3, length // 3)
        bridge = (gap, 1) if horizontal else (1, gap)
        mask = cv2.morphologyEx(
            mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, bridge)
        )
        # Lengthen every rule a little at both ends: a hand-ruled or faint line
        # often stops just short of the rule it should meet, and that gap would
        # let the two cells on either side leak into one.
        mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_RECT, bridge))
        masks.append(mask)
    return masks[0], masks[1]


def table_boxes(horizontal: np.ndarray, vertical: np.ndarray) -> list[Box]:
    """Return the bounding box of every region where rules form a frame.

    Boxes are ordered top-to-bottom. Lone underlines and signature strokes are
    rejected because they have no crossing rules and enclose no cell.
    """
    h, w = horizontal.shape
    mask = cv2.add(horizontal, vertical)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: list[Box] = []
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        if bw < w * _MIN_TABLE_WIDTH or bh < h * _MIN_TABLE_HEIGHT:
            continue
        has_h = cv2.countNonZero(horizontal[y : y + bh, x : x + bw]) > 0
        has_v = cv2.countNonZero(vertical[y : y + bh, x : x + bw]) > 0
        if has_h and has_v:
            boxes.append((x, y, bw, bh))
    boxes.sort(key=lambda b: (b[1], b[0]))
    return boxes


def _cells_in_box(horizontal: np.ndarray, vertical: np.ndarray, box: Box) -> list[CellBox]:
    """Find every enclosed blank region (cell) inside one table box."""
    x, y, bw, bh = box
    grid = cv2.add(horizontal[y : y + bh, x : x + bw], vertical[y : y + bh, x : x + bw])
    # Thicken the rules so crossings meet, and close the outer frame so a table
    # drawn without side borders still has closed first/last columns.
    grid = cv2.dilate(grid, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    cv2.rectangle(grid, (0, 0), (bw - 1, bh - 1), 255, 2)

    count, _labels, stats, _ = cv2.connectedComponentsWithStats(
        cv2.bitwise_not(grid), connectivity=4
    )
    min_w = max(8, bw // 150)
    min_h = max(8, bh // 150)
    cells: list[CellBox] = []
    for label in range(1, count):
        cx, cy, cw, ch, area = (int(v) for v in stats[label])
        if cw < min_w or ch < min_h:
            continue
        # A real cell fills most of its bounding box; an L-shaped leak does not.
        if area < 0.6 * cw * ch:
            continue
        # A double-ruled or slightly bowed frame leaves a thin strip between
        # the frame and the box edge: not a cell.
        on_side = cx <= _EDGE or cx + cw >= bw - _EDGE
        on_end = cy <= _EDGE or cy + ch >= bh - _EDGE
        if (on_side and cw < bw * _SLIVER) or (on_end and ch < bh * _SLIVER):
            continue
        cells.append(CellBox(x=x + cx, y=y + cy, width=cw, height=ch))
    return cells


def _cluster(values: list[int], tolerance: int) -> list[int]:
    """Merge 1D coordinates closer than ``tolerance`` into boundary lines."""
    boundaries: list[list[int]] = []
    for value in sorted(values):
        if boundaries and value - boundaries[-1][-1] <= tolerance:
            boundaries[-1].append(value)
        else:
            boundaries.append([value])
    return [int(round(sum(group) / len(group))) for group in boundaries]


def _nearest(value: int, boundaries: list[int]) -> int:
    """Return the index of the boundary closest to ``value``."""
    return min(range(len(boundaries)), key=lambda i: abs(boundaries[i] - value))


def _assign_grid(cells: list[CellBox]) -> tuple[int, int]:
    """Snap cells onto a logical grid, setting row/col/rowspan/colspan in place.

    Returns:
        The grid size as ``(n_rows, n_cols)``.
    """
    tol_x = max(6, min(c.width for c in cells) // 2)
    tol_y = max(6, min(c.height for c in cells) // 2)
    x_bounds = _cluster([e for c in cells for e in (c.x, c.x + c.width)], tol_x)
    y_bounds = _cluster([e for c in cells for e in (c.y, c.y + c.height)], tol_y)

    for cell in cells:
        left = _nearest(cell.x, x_bounds)
        right = _nearest(cell.x + cell.width, x_bounds)
        top = _nearest(cell.y, y_bounds)
        bottom = _nearest(cell.y + cell.height, y_bounds)
        cell.col, cell.colspan = left, max(1, right - left)
        cell.row, cell.rowspan = top, max(1, bottom - top)
    return len(y_bounds) - 1, len(x_bounds) - 1


def _drop_stray_runs(horizontal: np.ndarray, vertical: np.ndarray) -> None:
    """Remove, in place, straight runs that are not part of any ruling.

    The serifs along the baseline of a printed word, or the stem of a large
    letter, can pass for a short rule. Unlike real rules they stand alone: a
    table's rules all touch each other and form one page-sized network. Only
    networks of table size, or single long rules, are kept — which matters
    because whatever is kept is later erased from the image given to OCR.
    """
    h, w = horizontal.shape
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        cv2.add(horizontal, vertical), connectivity=8
    )
    keep = np.zeros(count, dtype=bool)
    for label in range(1, count):
        bw, bh = int(stats[label, cv2.CC_STAT_WIDTH]), int(stats[label, cv2.CC_STAT_HEIGHT])
        table_sized = bw >= w * _MIN_TABLE_WIDTH and bh >= h * _MIN_TABLE_HEIGHT
        long_rule = bw >= w * _MIN_LONE_RULE or bh >= h * _MIN_LONE_RULE
        keep[label] = table_sized or long_rule
    stray = ~keep[labels]
    horizontal[stray] = 0
    vertical[stray] = 0


def find_rules(gray: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return the (horizontal, vertical) ruling-line masks of a grayscale page."""
    horizontal, vertical = rule_masks(binarize_inverted(gray))
    _drop_stray_runs(horizontal, vertical)
    return horizontal, vertical


def erase_rules(image: np.ndarray, rules: tuple[np.ndarray, np.ndarray]) -> np.ndarray:
    """Paint a page's ruling lines white so OCR sees text only.

    Left in place, a rule is read as ``|``, ``l`` or ``_`` and glues the words
    of neighbouring cells together.
    """
    mask = cv2.add(rules[0], rules[1])
    mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)))
    cleaned = image.copy()
    cleaned[mask > 0] = 255
    return cleaned


def detect_tables(rules: tuple[np.ndarray, np.ndarray]) -> list[TableLayout]:
    """Lay out every ruled table found in a page's ruling-line masks.

    Args:
        rules: The ``(horizontal, vertical)`` masks from ``find_rules``.

    Returns:
        One ``TableLayout`` per table, ordered top-to-bottom. A region is kept
        only if it encloses at least two rows and two columns of cells.
    """
    horizontal, vertical = rules
    layouts: list[TableLayout] = []
    for box in table_boxes(horizontal, vertical):
        cells = _cells_in_box(horizontal, vertical, box)
        if len(cells) < 4:
            continue
        n_rows, n_cols = _assign_grid(cells)
        if n_rows < 2 or n_cols < 2:
            continue
        cells.sort(key=lambda c: (c.row, c.col))
        layouts.append(TableLayout(box=box, cells=cells, n_rows=n_rows, n_cols=n_cols))
    return layouts
