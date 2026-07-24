"""Tesseract OCR wrapper."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytesseract
from PIL import Image

from app.logging_config import get_logger

log = get_logger(__name__)


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


def run_ocr(image_path: Path, lang: str = "fra") -> OcrResult:
    """Run OCR on an image and return text plus per-word confidence data.

    Args:
        image_path: Path to the (preprocessed) page image.
        lang: Tesseract language string, e.g. ``"fra"`` or ``"fra+eng"``.

    Returns:
        An ``OcrResult`` with full text, per-word data and the mean confidence.
    """
    image = Image.open(image_path)
    data = pytesseract.image_to_data(
        image, lang=lang, output_type=pytesseract.Output.DICT
    )

    words: list[Word] = []
    confidences: list[float] = []
    n = len(data["text"])
    for i in range(n):
        text = data["text"][i].strip()
        conf = float(data["conf"][i])
        if not text or conf < 0:
            continue
        words.append(
            Word(
                text=text,
                confidence=conf,
                left=int(data["left"][i]),
                top=int(data["top"][i]),
                width=int(data["width"][i]),
                height=int(data["height"][i]),
                line_num=int(data["line_num"][i]),
                block_num=int(data["block_num"][i]),
                par_num=int(data["par_num"][i]),
            )
        )
        confidences.append(conf)

    full_text = _rebuild_text(words)
    mean_conf = sum(confidences) / len(confidences) if confidences else 0.0

    log.info(
        "ocr.done",
        image=str(image_path),
        lang=lang,
        words=len(words),
        mean_confidence=round(mean_conf, 1),
    )
    return OcrResult(text=full_text, words=words, mean_confidence=mean_conf)
