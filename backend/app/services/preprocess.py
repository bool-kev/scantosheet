"""Image preparation to improve table detection and OCR accuracy."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from app.services import dewarp

# How strongly a pixel's chroma lifts it toward white (see
# ``suppress_colored_ink``): 1.5 whitens stamp ink yet keeps dark-blue print.
_CHROMA_LIFT = 1.5


def to_grayscale(image: np.ndarray) -> np.ndarray:
    """Convert a BGR image to grayscale."""
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def suppress_colored_ink(image: np.ndarray) -> np.ndarray:
    """Convert a BGR image to grayscale while fading colored ink to white.

    Stamps, pen signatures, tinted header fills and photographed backgrounds
    (a desk, a folder) are colored, while printed text is dark and nearly
    neutral. Each pixel's brightest channel is lifted by its chroma, so a
    saturated pixel goes to white and a neutral one keeps its darkness. Being
    continuous, this leaves no halo around text printed on a tinted fill.
    """
    if image.ndim == 2:
        return image
    brightest = image.max(axis=2).astype(np.int16)
    chroma = brightest - image.min(axis=2).astype(np.int16)
    lifted = brightest + (chroma * _CHROMA_LIFT).astype(np.int16)
    return np.clip(lifted, 0, 255).astype(np.uint8)


@dataclass
class PreparedPage:
    """A page in the two forms the pipeline needs.

    Attributes:
        gray: Plain grayscale, used to find ruling lines (which may themselves
            be drawn in dark blue and must not be faded).
        ocr: Grayscale with colored ink faded out, used for text recognition.
    """

    gray: np.ndarray
    ocr: np.ndarray


def prepare_page(image: np.ndarray, enhance: bool = True) -> PreparedPage:
    """Derive the line-detection and OCR versions of a raw page image.

    With ``enhance``, the page is first straightened (perspective) and colored
    ink is faded from the OCR version. Nothing is blurred or binarized:
    Tesseract does its own thresholding, and a median blur erases decimal
    points and thin strokes.

    Args:
        image: BGR (or grayscale) page image.
        enhance: Apply rectification and colored-ink suppression.

    Returns:
        The prepared page.
    """
    if not enhance:
        gray = to_grayscale(image)
        return PreparedPage(gray=gray, ocr=gray)
    straight = dewarp.rectify(image)
    return PreparedPage(gray=to_grayscale(straight), ocr=suppress_colored_ink(straight))
