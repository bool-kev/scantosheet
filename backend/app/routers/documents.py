"""/api/documents endpoints."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.logging_config import get_logger
from app.models import Document, DocumentStatus, Page
from app.schemas import (
    Cell,
    DataUpdateRequest,
    DocumentDetail,
    DocumentList,
    DocumentSummary,
    PageData,
    PreviewResponse,
)
from app.services import excel
from app.worker import process_document

router = APIRouter(prefix="/api/documents", tags=["documents"])
log = get_logger(__name__)
settings = get_settings()

_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_filename(name: str) -> str:
    """Return a filesystem-safe version of an uploaded filename."""
    base = Path(name).name
    cleaned = _FILENAME_SAFE.sub("_", base).strip("._")
    return cleaned or "upload.pdf"


def _page_to_schema(page: Page) -> PageData:
    """Convert a Page ORM row to its API schema."""
    raw = json.loads(page.data_json or "[]")
    data = [[Cell(**cell) for cell in row] for row in raw]
    return PageData(
        page_number=page.page_number,
        text=page.text,
        data=data,
        mean_confidence=page.mean_confidence,
        warning=page.warning,
    )


@router.post("", response_model=DocumentSummary, status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF file to process"),
    language: str = Form("fra", description="Tesseract language, e.g. 'fra' or 'fra+eng'"),
    preprocessing: bool = Form(True, description="Enable image preprocessing"),
    db: Session = Depends(get_db),
) -> DocumentSummary:
    """Upload a PDF, validate it, persist it and queue OCR processing.

    Validates the MIME type, magic bytes and size, stores the file under a
    sanitized unique name, creates a ``queued`` document row and schedules the
    OCR pipeline as a background task.
    """
    from app.services import pdf  # local import to keep router import light

    content = await file.read()

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of {settings.max_file_size_mb} MB",
        )
    if not pdf.is_valid_pdf(content):
        raise HTTPException(status_code=400, detail="File is not a valid PDF")

    safe_name = _sanitize_filename(file.filename or "upload.pdf")
    stored_name = f"{uuid.uuid4().hex}_{safe_name}"
    stored_path = settings.uploads_dir / stored_name
    stored_path.write_bytes(content)

    # Validate the PDF has at least one page before committing.
    try:
        page_count = pdf.count_pages(stored_path)
    except ValueError as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    document = Document(
        filename=safe_name,
        stored_filename=stored_name,
        status=DocumentStatus.QUEUED,
        page_count=page_count,
        language=language,
        preprocessing=preprocessing,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    background_tasks.add_task(process_document, document.id)
    log.info("upload.queued", document_id=document.id, filename=safe_name, pages=page_count)

    return DocumentSummary.model_validate(document)


@router.get("", response_model=DocumentList)
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> DocumentList:
    """List documents, newest first, paginated."""
    total = db.scalar(select(func.count()).select_from(Document)) or 0
    stmt = (
        select(Document)
        .order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    documents = db.scalars(stmt).all()
    return DocumentList(
        items=[DocumentSummary.model_validate(d) for d in documents],
        total=total,
        page=page,
        page_size=page_size,
    )


def _get_document_or_404(document_id: int, db: Session) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(document_id: int, db: Session = Depends(get_db)) -> DocumentDetail:
    """Return document metadata plus per-page OCR data."""
    document = _get_document_or_404(document_id, db)
    # Validate the scalar metadata as a summary first, then attach the
    # transformed pages — model_validate() on the ORM object would try to coerce
    # the ORM Page rows (which store data_json, not `data`) into PageData.
    summary = DocumentSummary.model_validate(document)
    return DocumentDetail(
        **summary.model_dump(),
        pages=[_page_to_schema(p) for p in document.pages],
    )


@router.get("/{document_id}/preview", response_model=PreviewResponse)
async def preview_document(
    document_id: int, db: Session = Depends(get_db)
) -> PreviewResponse:
    """Return structured, page-by-page preview data."""
    document = _get_document_or_404(document_id, db)
    return PreviewResponse(
        document_id=document.id,
        filename=document.filename,
        status=document.status,
        pages=[_page_to_schema(p) for p in document.pages],
    )


@router.put("/{document_id}/data", response_model=PreviewResponse)
async def update_document_data(
    document_id: int,
    payload: DataUpdateRequest,
    db: Session = Depends(get_db),
) -> PreviewResponse:
    """Update/correct extracted cell data for one or more pages."""
    document = _get_document_or_404(document_id, db)
    pages_by_number = {p.page_number: p for p in document.pages}

    for page_update in payload.pages:
        page = pages_by_number.get(page_update.page_number)
        if page is None:
            raise HTTPException(
                status_code=404,
                detail=f"Page {page_update.page_number} not found",
            )
        serialized = [
            [{"value": cell.value, "confidence": cell.confidence} for cell in row]
            for row in page_update.data
        ]
        page.data_json = json.dumps(serialized, ensure_ascii=False)

    db.commit()
    log.info("data.updated", document_id=document_id, pages=len(payload.pages))
    return PreviewResponse(
        document_id=document.id,
        filename=document.filename,
        status=document.status,
        pages=[_page_to_schema(p) for p in document.pages],
    )


def _document_grids(document: Document) -> list[list[list[str]]]:
    """Return each page's data as a 2D grid of plain string values."""
    grids: list[list[list[str]]] = []
    for page in document.pages:
        raw = json.loads(page.data_json or "[]")
        grids.append([[str(cell.get("value", "")) for cell in row] for row in raw])
    return grids


@router.get("/{document_id}/download")
async def download_document(
    document_id: int,
    fmt: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    merge: bool = Query(False),
    delimiter: str = Query(",", pattern="^[,;]$"),
    db: Session = Depends(get_db),
):
    """Download the extracted data as ``xlsx`` (default) or ``csv``."""
    document = _get_document_or_404(document_id, db)
    if document.status != DocumentStatus.DONE:
        raise HTTPException(status_code=409, detail="Document is not ready for download")

    grids = _document_grids(document)
    base = Path(document.filename).stem

    if fmt == "csv":
        content = excel.export_csv(grids, delimiter=delimiter)
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{base}_extracted.csv"'
            },
        )

    output_path = settings.results_dir / f"{document_id}_{base}_extracted.xlsx"
    excel.export_xlsx(grids, output_path, merge=merge)
    document.result_path = str(output_path)
    db.commit()
    return FileResponse(
        path=output_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{base}_extracted.xlsx",
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: int, db: Session = Depends(get_db)) -> Response:
    """Delete a document and its associated files on disk."""
    document = _get_document_or_404(document_id, db)

    # Remove uploaded PDF, page images, processed images and result files.
    (settings.uploads_dir / document.stored_filename).unlink(missing_ok=True)
    stem = Path(document.stored_filename).stem
    for directory in (settings.pages_dir, settings.processed_dir):
        for image in directory.glob(f"{stem}_page_*.png"):
            image.unlink(missing_ok=True)
    if document.result_path:
        Path(document.result_path).unlink(missing_ok=True)

    db.delete(document)
    db.commit()
    log.info("document.deleted", document_id=document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
