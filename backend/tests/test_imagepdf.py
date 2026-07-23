"""Unit tests for the Images -> PDF module's validation and PDF assembly."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from pdf2image import pdfinfo_from_path
from PIL import Image

from app.services import imagepdf


def _image_bytes(size: tuple[int, int] = (200, 100), color=(255, 0, 0), fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt)
    return buf.getvalue()


def test_is_valid_image_accepts_supported_formats() -> None:
    assert imagepdf.is_valid_image(_image_bytes(fmt="PNG"))
    assert imagepdf.is_valid_image(_image_bytes(fmt="JPEG"))


def test_is_valid_image_rejects_non_images() -> None:
    assert not imagepdf.is_valid_image(b"just some text")
    assert not imagepdf.is_valid_image(b"%PDF-1.7\nfake")
    assert not imagepdf.is_valid_image(b"")


def test_prepare_page_rotation_swaps_dimensions() -> None:
    image = Image.new("RGB", (200, 100), "white")
    rotated = imagepdf.prepare_page(image, rotation=90, quality="high", page_size="original")
    assert rotated.size == (100, 200)


def test_prepare_page_no_rotation_keeps_dimensions() -> None:
    image = Image.new("RGB", (200, 100), "white")
    result = imagepdf.prepare_page(image, rotation=0, quality="high", page_size="original")
    assert result.size == (200, 100)


def test_prepare_page_downscales_to_quality_preset() -> None:
    image = Image.new("RGB", (5000, 2500), "white")
    result = imagepdf.prepare_page(image, rotation=0, quality="compact", page_size="original")
    assert max(result.size) <= imagepdf.QUALITY_PRESETS["compact"][0]


def test_prepare_page_fits_a4_canvas() -> None:
    image = Image.new("RGB", (200, 100), "white")
    result = imagepdf.prepare_page(image, rotation=0, quality="high", page_size="a4")
    # A landscape source image is framed on a landscape A4 canvas.
    portrait_w, portrait_h = imagepdf.PAGE_SIZES["a4"]
    assert result.size == (portrait_h, portrait_w)


def test_prepare_page_rejects_unknown_presets() -> None:
    image = Image.new("RGB", (10, 10), "white")
    with pytest.raises(ValueError):
        imagepdf.prepare_page(image, rotation=0, quality="ultra", page_size="a4")
    with pytest.raises(ValueError):
        imagepdf.prepare_page(image, rotation=0, quality="high", page_size="letter")


def test_build_pdf_produces_valid_multi_page_pdf(tmp_path: Path) -> None:
    paths = []
    for i in range(3):
        path = tmp_path / f"page{i}.png"
        Image.new("RGB", (300, 400), (i * 50, 0, 0)).save(path)
        paths.append(path)

    output = tmp_path / "out.pdf"
    imagepdf.build_pdf(paths, output, rotations=[0, 90, 0], quality="standard", page_size="a4")

    assert output.read_bytes().startswith(b"%PDF-")
    info = pdfinfo_from_path(str(output))
    assert int(info["Pages"]) == 3


def test_build_pdf_rejects_rotation_length_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "page.png"
    Image.new("RGB", (100, 100), "white").save(path)
    output = tmp_path / "out.pdf"
    with pytest.raises(ValueError):
        imagepdf.build_pdf([path], output, rotations=[0, 90], quality="standard", page_size="a4")


def test_build_pdf_high_quality_larger_than_compact(tmp_path: Path) -> None:
    """A noisy (photo-like) image compresses more aggressively at low quality."""
    rng = np.random.default_rng(0)
    array = rng.integers(0, 256, size=(600, 800, 3), dtype=np.uint8)
    path = tmp_path / "noisy.png"
    Image.fromarray(array).save(path)

    high_out = tmp_path / "high.pdf"
    compact_out = tmp_path / "compact.pdf"
    imagepdf.build_pdf([path], high_out, rotations=[0], quality="high", page_size="original")
    imagepdf.build_pdf([path], compact_out, rotations=[0], quality="compact", page_size="original")

    assert high_out.stat().st_size > compact_out.stat().st_size
