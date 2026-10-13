"""Tesseract OCR wrapper."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image

from app.logging_config import get_logger

log = get_logger(__name__)

# Tesseract page segmentation modes used by the pipeline.
PSM_BLOCK = 6  # a single uniform block of text
PSM_LINE = 7  # a single text line
PSM_CHAR = 10  # a single character
PSM_SPARSE = 11  # sparse text: find as much text as possible, in no order

# White margin added around a region before OCR.
_REGION_PADDING = 24


@dataclass
class Word:
    """A single recognized word with geometry and confidence."""

    text: str
    confidence: float
    left: int
    top: int
    width: int
    height: int
    line_num: int
    block_num: int
    par_num: int


@dataclass
class OcrResult:
    """OCR output for a single image."""

    text: str
    words: list[Word] = field(default_factory=list)
    mean_confidence: float = 0.0


def available_languages() -> list[str]:
    """Return the list of language packs installed in Tesseract."""
    try:
        return list(pytesseract.get_languages(config=""))
    except Exception:  # pragma: no cover - depends on system tesseract
        return []


def is_available() -> bool:
    """Return True if the Tesseract binary is reachable."""
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:  # pragma: no cover
        return False


def _rebuild_text(words: list[Word]) -> str:
    """Reconstruct page text from word geometry, grouped by OCR line/block.

    Mirrors ``pytesseract.image_to_string`` closely enough for downstream use
    (words joined by spaces within a line, lines joined by newlines, a blank
    line between blocks) without paying for a second Tesseract pass.
    """
    lines: dict[tuple[int, int, int], list[str]] = {}
    for word in words:
        key = (word.block_num, word.par_num, word.line_num)
        lines.setdefault(key, []).append(word.text)

    parts: list[str] = []
    prev_block: int | None = None
    for key in sorted(lines.keys()):
        block_num = key[0]
        if prev_block is not None and block_num != prev_block:
            parts.append("")
        parts.append(" ".join(lines[key]))
        prev_block = block_num

    return "\n".join(parts) + ("\n" if parts else "")


def _parse_words(data: dict[str, list], offset: int = 0) -> list[Word]:
    """Build ``Word`` objects from Tesseract's TSV dict, skipping non-text rows.

    Args:
        data: Output of ``pytesseract.image_to_data`` as a dict.
        offset: Value added to every word's ``left`` and ``top``.
    """
    words: list[Word] = []
    for i in range(len(data["text"])):
        text = data["text"][i].strip()
        conf = float(data["conf"][i])
        if not text or conf < 0:
            continue
        words.append(
            Word(
                text=text,
                confidence=conf,
                left=int(data["left"][i]) + offset,
                top=int(data["top"][i]) + offset,
                width=int(data["width"][i]),
                height=int(data["height"][i]),
                line_num=int(data["line_num"][i]),
                block_num=int(data["block_num"][i]),
                par_num=int(data["par_num"][i]),
            )
        )
    return words


def run_ocr(
    image: Path | np.ndarray, lang: str = "fra", psm: int | None = None
) -> OcrResult:
    """Run OCR on an image and return text plus per-word confidence data.

    Args:
        image: Path to a page image, or an already-loaded grayscale/RGB array.
        lang: Tesseract language string, e.g. ``"fra"`` or ``"fra+eng"``.
        psm: Tesseract page segmentation mode; ``None`` keeps its default.

    Returns:
        An ``OcrResult`` with full text, per-word data and the mean confidence.
    """
    source = Image.open(image) if isinstance(image, Path) else image
    config = f"--psm {psm}" if psm is not None else ""
    data = pytesseract.image_to_data(
        source, lang=lang, config=config, output_type=pytesseract.Output.DICT
    )

    words = _parse_words(data)
    full_text = _rebuild_text(words)
    mean_conf = sum(w.confidence for w in words) / len(words) if words else 0.0

    log.info(
        "ocr.done",
        lang=lang,
        psm=psm,
        words=len(words),
        mean_confidence=round(mean_conf, 1),
    )
    return OcrResult(text=full_text, words=words, mean_confidence=mean_conf)


def read_region(
    image: np.ndarray, lang: str = "fra", psm: int = PSM_BLOCK, digits_only: bool = False
) -> list[Word]:
    """OCR one small region (typically a table cell) on its own.

    Read alone, a cell is not disturbed by its neighbours: Tesseract's page
    layout analysis routinely skips short isolated cells such as ``6`` or
    ``II``. The crop is padded with white, since text touching the image edge
    is recognised poorly.

    Args:
        image: Grayscale crop of the region.
        lang: Tesseract language string.
        psm: Page segmentation mode (block of text by default).
        digits_only: Restrict recognition to the digits 0-9.

    Returns:
        The recognised words, positioned relative to the crop's top-left.
    """
    # Stretch the crop to full contrast: pale gray print on white is otherwise
    # thresholded away.
    stretched = cv2.normalize(image, None, 0, 255, cv2.NORM_MINMAX)
    padded = np.pad(stretched, _REGION_PADDING, mode="constant", constant_values=255)
    config = f"--psm {psm}"
    if digits_only:
        config += " -c tessedit_char_whitelist=0123456789"
    data = pytesseract.image_to_data(
        padded, lang=lang, config=config, output_type=pytesseract.Output.DICT
    )
    return _parse_words(data, offset=-_REGION_PADDING)
