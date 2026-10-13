"""Unit tests for cell detection, page preparation and grid building.

Everything here runs on synthetic images, without Tesseract.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.services import cells, dewarp, preprocess, table
from app.services.cells import CellBox, TableLayout
from app.services.ocr import Word

# A 3-column x 3-row table whose first column is one cell merged over the two
# body rows:
#   +------+------+------+
#   |  h0  |  h1  |  h2  |
#   +------+------+------+
#   |      |  a1  |  a2  |
#   +  m   +------+------+
#   |      |  b1  |  b2  |
#   +------+------+------+
X0, Y0, CW, CH = 150, 300, 300, 120


def _draw_merged_table(height: int = 1400, width: int = 1300) -> np.ndarray:
    img = np.full((height, width), 255, dtype=np.uint8)
    right, bottom = X0 + 3 * CW, Y0 + 3 * CH
    for r in (0, 1, 3):  # full-width rules
        cv2.line(img, (X0, Y0 + r * CH), (right, Y0 + r * CH), 0, 3)
    # The rule between the two body rows stops short of the merged column.
    cv2.line(img, (X0 + CW, Y0 + 2 * CH), (right, Y0 + 2 * CH), 0, 3)
    for c in range(4):
        cv2.line(img, (X0 + c * CW, Y0), (X0 + c * CW, bottom), 0, 3)
    return img


def _word(text: str, cx: int, cy: int, conf: float = 90.0, height: int = 40) -> Word:
    width = len(text) * 20
    return Word(
        text=text,
        confidence=conf,
        left=cx - width // 2,
        top=cy - height // 2,
        width=width,
        height=height,
        line_num=1,
        block_num=1,
        par_num=1,
    )


def _centre(row: int, col: int) -> tuple[int, int]:
    return X0 + col * CW + CW // 2, Y0 + row * CH + CH // 2


def test_merged_cell_is_one_box_spanning_two_rows() -> None:
    layouts = cells.detect_tables(cells.find_rules(_draw_merged_table()))

    assert len(layouts) == 1
    layout = layouts[0]
    assert (layout.n_rows, layout.n_cols) == (3, 3)
    assert len(layout.cells) == 8  # 9 grid slots, two of them merged into one

    merged = [c for c in layout.cells if c.rowspan == 2]
    assert len(merged) == 1
    assert (merged[0].row, merged[0].col, merged[0].colspan) == (1, 0, 1)


def test_merged_cell_text_is_repeated_on_each_row() -> None:
    layout = cells.detect_tables(cells.find_rules(_draw_merged_table()))[0]
    words = [
        _word("Date", *_centre(0, 0)),
        _word("Nom", *_centre(0, 1)),
        _word("15/07", X0 + CW // 2, Y0 + 2 * CH),  # middle of the merged cell
        _word("Alice", *_centre(1, 1)),
        _word("Bob", *_centre(2, 1)),
        _word("Titre", 600, 100),  # outside the table: must be dropped
    ]
    grid = table.build_grid(layout, table.map_words(layout, words))
    texts = [[cell[0] for cell in row] for row in grid]

    assert texts == [["Date", "Nom"], ["15/07", "Alice"], ["15/07", "Bob"]]


def test_lone_underline_is_not_a_table() -> None:
    img = np.full((1400, 1300), 255, dtype=np.uint8)
    cv2.line(img, (200, 700), (1100, 700), 0, 3)
    assert cells.detect_tables(cells.find_rules(img)) == []


def test_erase_rules_removes_lines_but_not_text() -> None:
    img = _draw_merged_table()
    cx, cy = _centre(1, 1)
    cv2.putText(img, "42", (cx - 40, cy + 20), cv2.FONT_HERSHEY_SIMPLEX, 2, 0, 5)
    ink_before = int(np.count_nonzero(img[cy - 40 : cy + 40, cx - 60 : cx + 60] < 128))

    cleaned = cells.erase_rules(img, cells.find_rules(img))

    assert cleaned[Y0, X0 + CW // 2] == 255  # a point on the top rule
    ink_after = int(np.count_nonzero(cleaned[cy - 40 : cy + 40, cx - 60 : cx + 60] < 128))
    assert ink_after == ink_before


def test_rectify_straightens_a_keystoned_table() -> None:
    flat = _draw_merged_table()
    h, w = flat.shape
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[200, 20], [w - 10, 0], [w, h], [0, h - 30]])  # keystone
    warped = cv2.warpPerspective(
        flat, cv2.getPerspectiveTransform(src, dst), (w, h), borderValue=255
    )

    def left_edge_slant(image: np.ndarray) -> float:
        corners = dewarp._frame_corners(image)
        assert corners is not None
        return abs(float(corners[0][0] - corners[3][0]))  # top-left x vs bottom-left x

    assert left_edge_slant(warped) > 20
    assert left_edge_slant(dewarp.rectify(warped)) < 6


def test_rectify_leaves_a_straight_page_untouched() -> None:
    flat = _draw_merged_table()
    assert dewarp.rectify(flat) is flat


def test_colored_ink_fades_while_black_print_stays() -> None:
    img = np.full((10, 30, 3), 255, dtype=np.uint8)
    img[:, 0:10] = (20, 20, 20)  # black print
    img[:, 10:20] = (170, 60, 50)  # blue stamp ink (BGR)
    gray = preprocess.suppress_colored_ink(img)

    assert gray[5, 5] < 60
    assert gray[5, 15] == 255
    assert gray[5, 25] == 255


def test_is_noise() -> None:
    line_height = 40.0
    assert table.is_noise(_word("_", 0, 0), line_height)  # rule leftover
    assert not table.is_noise(_word("|", 0, 0), line_height)  # may be a roman I
    assert table.is_noise(_word("Ras", 0, 0, height=230), line_height)  # giant glyph
    assert table.is_noise(_word("io", 0, 0, height=7), line_height)  # speck
    assert table.is_noise(_word("eS", 0, 0, conf=30.0), line_height)  # unsure fragment
    assert not table.is_noise(_word("Certifies", 0, 0, conf=15.0), line_height)
    assert not table.is_noise(_word("12", 0, 0, conf=90.0), line_height)
    assert not table.is_noise(_word("-", 0, 0, height=6), line_height)


def test_cell_text_reads_lines_top_to_bottom() -> None:
    box = CellBox(x=0, y=0, width=600, height=200)
    words = [
        _word("Kaya", 100, 150),
        _word("de", 300, 52),  # same line as "Lycee", slightly lower
        _word("Lycee", 100, 50),
    ]
    layout = TableLayout(box=(0, 0, 600, 200), cells=[box], n_rows=1, n_cols=1)
    content = table.map_words(layout, words)[0]

    assert content.text == "Lycee de Kaya"
