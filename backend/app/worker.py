"""Background processing pipeline: PDF -> images -> preprocess -> OCR -> tables."""

from __future__ import annotations

import json
from pathlib import Path

from app.config import get_settings
from app.database import SessionLocal
from app.logging_config import get_logger
from app.models import Document, DocumentStatus, Page
from app.services import ocr, pdf, preprocess, table

log = get_logger(__name__)
settings = get_settings()


def _grid_to_json(grid: list[list[tuple[str, float]]]) -> str:
    """Serialize a ``(text, confidence)`` grid to the stored JSON cell format."""
    payload = [
        [{"value": value, "confidence": round(conf, 1)} for value, conf in row]
        for row in grid
    ]
    return json.dumps(payload, ensure_ascii=False)


def process_document(document_id: int) -> None:
    """Run the full OCR pipeline for a document.

    Status transitions: queued -> processing -> done / error. OCR failures on an
    individual page are logged as page warnings and do not abort the whole
    document.

    Args:
        document_id: Primary key of the document to process.
    """
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            log.warning("worker.document_missing", document_id=document_id)
            return

        document.status = DocumentStatus.PROCESSING
        db.commit()
        log.info("worker.start", document_id=document_id, filename=document.filename)

        pdf_path = settings.uploads_dir / document.stored_filename
        page_images = pdf.pdf_to_images(pdf_path, settings.pages_dir, dpi=settings.ocr_dpi)
        document.page_count = len(page_images)
        db.commit()

        # Reset any previously stored pages (e.g. on reprocessing).
        for old in list(document.pages):
            db.delete(old)
        db.commit()

        for index, image_path in enumerate(page_images, start=1):
            page = _process_page(document, index, image_path)
            db.add(page)
            db.commit()

        document.status = DocumentStatus.DONE
        document.error_message = None
        db.commit()
        log.info("worker.done", document_id=document_id, pages=document.page_count)

    except Exception as exc:  # noqa: BLE001 - top-level pipeline guard
        db.rollback()
        document = db.get(Document, document_id)
        if document is not None:
            document.status = DocumentStatus.ERROR
            document.error_message = str(exc)
            db.commit()
        log.error("worker.error", document_id=document_id, error=str(exc), exc_info=True)
    finally:
        db.close()


def _process_page(document: Document, page_number: int, image_path: Path) -> Page:
    """Preprocess, OCR and structure a single page, returning a Page row.

    A failure here is captured as a page-level warning so sibling pages still
    process.
    """
    warning: str | None = None
    text = ""
    data_json = "[]"
    mean_conf = 0.0

    try:
        ocr_input = image_path
        if document.preprocessing:
            processed_path = settings.processed_dir / image_path.name
            ocr_input = preprocess.preprocess_image(image_path, processed_path)

        result = ocr.run_ocr(ocr_input, lang=document.language)
        grid = table.structure_page(
            ocr_input, result, tables_only=settings.extract_tables_only
        )

        text = result.text
        mean_conf = result.mean_confidence
        data_json = _grid_to_json(grid)
    except Exception as exc:  # noqa: BLE001 - per-page guard
        warning = f"OCR failed on page {page_number}: {exc}"
        log.warning(
            "worker.page_error",
            document_id=document.id,
            page=page_number,
            error=str(exc),
        )

    return Page(
        document_id=document.id,
        page_number=page_number,
        text=text,
        data_json=data_json,
        mean_confidence=mean_conf,
        warning=warning,
    )
