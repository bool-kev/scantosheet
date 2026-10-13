"""PDF utilities: validation and page-to-image conversion."""

from __future__ import annotations

from pathlib import Path

from pdf2image import convert_from_path, pdfinfo_from_path

from app.logging_config import get_logger

log = get_logger(__name__)

# %PDF magic bytes.
PDF_MAGIC = b"%PDF-"


def is_valid_pdf(data: bytes) -> bool:
    """Return True if the given bytes start with the PDF magic number.

    Args:
        data: The first bytes of the uploaded file.

    Returns:
        True if the content looks like a PDF, False otherwise.
    """
    return data[: len(PDF_MAGIC)] == PDF_MAGIC


def count_pages(pdf_path: Path) -> int:
    """Return the number of pages in a PDF.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        The page count.

    Raises:
        ValueError: If the PDF cannot be read or has zero pages.
    """
    try:
        info = pdfinfo_from_path(str(pdf_path))
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError(f"Unable to read PDF: {exc}") from exc

    pages = int(info.get("Pages", 0))
    if pages < 1:
        raise ValueError("PDF has no pages")
    return pages


def pdf_to_images(pdf_path: Path, output_dir: Path, dpi: int = 300) -> list[Path]:
    """Convert every page of a PDF into a PNG image.

    Args:
        pdf_path: Path to the source PDF.
        output_dir: Directory where page images are written.
        dpi: Rendering resolution.

    Returns:
        A list of paths to the generated page images, ordered by page number.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = pdf_path.stem

    log.info("pdf_to_images.start", pdf=str(pdf_path), dpi=dpi)
    images = convert_from_path(str(pdf_path), dpi=dpi, fmt="png")

    paths: list[Path] = []
    for index, image in enumerate(images, start=1):
        page_path = output_dir / f"{stem}_page_{index:03d}.png"
        image.save(page_path, "PNG")
        paths.append(page_path)
        log.info("pdf_to_images.page.done", page=index, path=str(page_path))

    log.info("pdf_to_images.done", pages=len(paths))
    return paths
