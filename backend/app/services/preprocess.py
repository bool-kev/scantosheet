"""Image preprocessing pipeline to improve OCR accuracy."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.logging_config import get_logger

log = get_logger(__name__)


def to_grayscale(image: np.ndarray) -> np.ndarray:
    """Convert a BGR image to grayscale."""
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def denoise(image: np.ndarray) -> np.ndarray:
    """Remove speckle noise with a median blur."""
    return cv2.medianBlur(image, 3)


def binarize(image: np.ndarray) -> np.ndarray:
    """Apply adaptive Gaussian thresholding to produce a black & white image."""
    return cv2.adaptiveThreshold(
        image,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31,
        C=15,
    )


def deskew(image: np.ndarray) -> np.ndarray:
    """Detect and correct the skew angle of a (grayscale) scanned image.

    Uses the minimum-area rectangle of the foreground pixels to estimate the
    rotation angle, then rotates the image to straighten it.

    Args:
        image: Grayscale image.

    Returns:
        The deskewed image.
    """
    # Foreground pixels are dark; invert so text becomes white on black.
    inverted = cv2.bitwise_not(image)
    coords = cv2.findNonZero(inverted)
    if coords is None:
        return image

    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = 90 + angle
    # Ignore negligible rotations to avoid unnecessary interpolation blur.
    if abs(angle) < 0.5:
        return image

    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        image,
        matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def preprocess_image(input_path: Path, output_path: Path) -> Path:
    """Run the full preprocessing pipeline on an image and save the result.

    Pipeline: grayscale -> denoise -> deskew -> binarize.

    Args:
        input_path: Path to the source page image.
        output_path: Path where the processed image is written.

    Returns:
        The output path.

    Raises:
        ValueError: If the image cannot be read.
    """
    image = cv2.imread(str(input_path))
    if image is None:
        raise ValueError(f"Unable to read image: {input_path}")

    gray = to_grayscale(image)
    gray = denoise(gray)
    gray = deskew(gray)
    result = binarize(gray)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), result)
    log.info("preprocess.done", src=str(input_path), dst=str(output_path))
    return output_path
