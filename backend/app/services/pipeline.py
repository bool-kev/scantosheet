"""Per-page extraction pipeline: prepare -> find cells -> OCR -> grid.

Kept free of any database access so the exact same code path can be run by the
background worker and by the offline benchmark (``backend/bench``).
"""

from __future__ import annotations

from pathlib import Path

import cv2

from app.config import get_settings
from app.logging_config import get_logger
from app.services import cells, ocr, preprocess, reread, table
from app.services.ocr import OcrResult
from app.services.table import Grid

log = get_logger(__name__)

def extract_page(
    image_path: Path,
    language: str,
    preprocessing: bool,
    tables_only: bool = True,
) -> tuple[OcrResult, Grid]:
    """Run the full extraction pipeline on one page image.

    The page is straightened, its table cells are located from the ruling
    lines, and the text is read from a copy with those lines erased. Cells the
    page-wide OCR pass missed or was unsure about are then re-read one by one.

    Args:
        image_path: Path to the rendered page image.
        language: Tesseract language string, e.g. ``"fra"`` or ``"fra+eng"``.
        preprocessing: Whether to straighten the page and fade colored ink.
        tables_only: If True, ignore everything that is not inside a table.

    Returns:
        The page's OCR result and its structured grid of cells.

    Raises:
        ValueError: If the image cannot be read.
    """
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"Unable to read image: {image_path}")

    page = preprocess.prepare_page(image, enhance=preprocessing)
    rules = cells.find_rules(page.gray)
    layouts = cells.detect_tables(rules)
    text_image = cells.erase_rules(page.ocr, rules)

    result = ocr.run_ocr(text_image, lang=language, psm=get_settings().ocr_psm)
    heights = sorted(w.height for w in result.words)
    line_height = float(heights[len(heights) // 2]) if heights else 40.0

    grids: list[Grid] = []
    reread_count = 0
    for layout in layouts:
        contents = table.map_words(layout, result.words, line_height)
        reread_count += reread.reread_weak_cells(text_image, contents, language, line_height)
        reread_count += reread.reread_numeric_columns(text_image, contents, language)
        reread_count += reread.reread_tally_columns(text_image, contents)
        grid = table.build_grid(layout, contents)
        if grid:
            grids.append(grid)

    if grids:
        combined = table.concat_grids(grids)
        log.info(
            "table.detected",
            tables=len(grids),
            rows=len(combined),
            cols=max((len(r) for r in combined), default=0),
            reread_cells=reread_count,
        )
        return result, combined

    if tables_only:
        log.info("table.none", note="no table region detected; free text ignored")
        return result, []

    log.info("table.fallback", reason="no_grid")
    return result, table.structure_by_lines(result.words)
