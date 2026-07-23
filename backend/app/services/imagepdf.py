"""Image validation and PDF assembly for the Images -> PDF module."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.logging_config import get_logger

log = get_logger(__name__)

ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "TIFF", "BMP"}

# quality preset -> (max long edge in px, JPEG quality). `None` for the long
# edge means no downscaling; `None` for JPEG quality lets Pillow's default
# apply (only ever reached if a preset omits it, which none currently do).
QUALITY_PRESETS: dict[str, tuple[int | None, int | None]] = {
    "high": (None, 95),
    "standard": (2480, 85),
    "compact": (1654, 75),
}

# Page size -> (width, height) in pixels at 300 DPI, portrait orientation.
PAGE_SIZES: dict[str, tuple[int, int] | None] = {
    "a4": (2480, 3508),
    "original": None,
}


def is_valid_image(data: bytes) -> bool:
    """Return True if the given bytes decode as a supported image format.

    Uses Pillow's format sniffing (not just the file extension) so a
    renamed non-image file is rejected.

    Args:
        data: The full contents of the uploaded file.

    Returns:
        True if the content is a readable image in an allowed format.
    """
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
            return image.format in ALLOWED_IMAGE_FORMATS
    except (UnidentifiedImageError, OSError, ValueError):
        return False


def _fit_to_page(image: Image.Image, page_size: str) -> Image.Image:
    """Center `image` on a white canvas of the given page size.

    The canvas orientation (portrait/landscape) follows the image's own
    orientation so a landscape photo isn't squeezed into a portrait page.
    """
    dimensions = PAGE_SIZES[page_size]
    if dimensions is None:
        return image

    width, height = image.size
    portrait_canvas = width <= height
    canvas_w, canvas_h = dimensions if portrait_canvas else (dimensions[1], dimensions[0])

    scale = min(canvas_w / width, canvas_h / height)
    new_w = max(1, round(width * scale))
    new_h = max(1, round(height * scale))
    resized = image.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGB", (canvas_w, canvas_h), "white")
    offset = ((canvas_w - new_w) // 2, (canvas_h - new_h) // 2)
    canvas.paste(resized, offset)
    return canvas


def prepare_page(
    image: Image.Image, rotation: int, quality: str, page_size: str
) -> Image.Image:
    """Apply EXIF correction, rotation, downscaling and page framing to one page.

    Args:
        image: The source image, already loaded into memory.
        rotation: Additional clockwise rotation in degrees (0, 90, 180 or 270).
        quality: One of the keys of ``QUALITY_PRESETS``.
        page_size: One of the keys of ``PAGE_SIZES``.

    Returns:
        A new RGB image ready to be embedded as a PDF page.

    Raises:
        ValueError: If ``quality`` or ``page_size`` is not a known preset.
    """
    if quality not in QUALITY_PRESETS:
        raise ValueError(f"Unknown quality preset: {quality}")
    if page_size not in PAGE_SIZES:
        raise ValueError(f"Unknown page size: {page_size}")

    # Smartphone photos carry orientation in EXIF rather than in pixel data.
    result = ImageOps.exif_transpose(image) or image

    if rotation % 360:
        result = result.rotate(-rotation, expand=True)

    long_edge, _ = QUALITY_PRESETS[quality]
    if long_edge is not None:
        width, height = result.size
        longest = max(width, height)
        if longest > long_edge:
            scale = long_edge / longest
            result = result.resize(
                (max(1, round(width * scale)), max(1, round(height * scale))),
                Image.LANCZOS,
            )

    result = result.convert("RGB")
    return _fit_to_page(result, page_size)


def build_pdf(
    image_paths: list[Path],
    output: Path,
    *,
    rotations: list[int],
    quality: str,
    page_size: str,
) -> Path:
    """Assemble a sequence of images into a single multi-page PDF.

    Args:
        image_paths: Source images, in the desired final page order.
        output: Destination path for the generated PDF.
        rotations: Per-image clockwise rotation in degrees, same length and
            order as ``image_paths``.
        quality: One of the keys of ``QUALITY_PRESETS``.
        page_size: One of the keys of ``PAGE_SIZES``.

    Returns:
        The ``output`` path.

    Raises:
        ValueError: If ``rotations`` doesn't match ``image_paths`` in length,
            or an unknown quality/page_size preset is given.
    """
    if len(rotations) != len(image_paths):
        raise ValueError("rotations must have the same length as image_paths")
    if not image_paths:
        raise ValueError("At least one image is required")

    _, jpeg_quality = QUALITY_PRESETS[quality]  # validates the preset name

    pages: list[Image.Image] = []
    for path, rotation in zip(image_paths, rotations):
        with Image.open(path) as source:
            source.load()
            pages.append(prepare_page(source, rotation, quality, page_size))

    output.parent.mkdir(parents=True, exist_ok=True)
    save_kwargs: dict[str, object] = {"save_all": True, "resolution": 300.0}
    if len(pages) > 1:
        save_kwargs["append_images"] = pages[1:]
    if jpeg_quality is not None:
        save_kwargs["quality"] = jpeg_quality

    pages[0].save(output, "PDF", **save_kwargs)
    log.info("build_pdf.done", pages=len(pages), output=str(output))
    return output
