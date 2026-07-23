"""/api/images endpoints — Images -> PDF module."""

from __future__ import annotations

import io
import mimetypes
import tempfile
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, Response
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.logging_config import get_logger
from app.models import BatchImage, Document, DocumentStatus, ImageBatch
from app.schemas import (
    BatchImageOut,
    BatchUpdateRequest,
    DocumentSummary,
    ImageBatchDetail,
    ImageBatchSummary,
)
from app.security import Principal, resolve_principal
from app.services import imagepdf
from app.services.files import sanitize_filename
from app.worker import process_document

router = APIRouter(prefix="/api/images", tags=["images"])
log = get_logger(__name__)
settings = get_settings()


def _parse_rotations(raw: str, count: int) -> list[int]:
    """Parse the comma-separated ``rotations`` form field.

    Args:
        raw: Comma-separated integers, e.g. ``"0,90,0"``. Empty means "no
            rotation" for every image.
        count: Expected number of values (one per uploaded image).

    Raises:
        HTTPException: 400 if the count doesn't match or a value is invalid.
    """
    if not raw.strip():
        return [0] * count
    try:
        values = [int(v.strip()) for v in raw.split(",")]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="rotations must be a comma-separated list of integers") from exc
    if len(values) != count:
        raise HTTPException(
            status_code=400,
            detail=f"rotations has {len(values)} value(s) but {count} image(s) were uploaded",
        )
    for value in values:
        if value % 90 != 0:
            raise HTTPException(status_code=400, detail="rotations must be multiples of 90")
    return values


def _validate_presets(quality: str, page_size: str) -> None:
    if quality not in imagepdf.QUALITY_PRESETS:
        raise HTTPException(status_code=400, detail=f"Unknown quality preset: {quality}")
    if page_size not in imagepdf.PAGE_SIZES:
        raise HTTPException(status_code=400, detail=f"Unknown page size: {page_size}")


def _check_batch_length(count: int) -> None:
    if count == 0:
        raise HTTPException(status_code=400, detail="At least one image is required")
    if count > settings.max_batch_images:
        raise HTTPException(
            status_code=400,
            detail=f"A batch cannot contain more than {settings.max_batch_images} images",
        )


async def _read_and_validate_image(upload: UploadFile, index: int) -> bytes:
    """Read an uploaded image and enforce size/format constraints.

    Raises:
        HTTPException: 400 if empty or not a supported image format, 413 if
            it exceeds the per-image size limit.
    """
    content = await upload.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail=f"Image {index} ('{upload.filename}') is empty")
    if len(content) > settings.max_image_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Image {index} exceeds the maximum size of {settings.max_image_size_mb} MB",
        )
    if not imagepdf.is_valid_image(content):
        raise HTTPException(
            status_code=400,
            detail=f"Image {index} ('{upload.filename}') is not a supported image format",
        )
    return content


def _batch_to_schema(batch: ImageBatch) -> ImageBatchDetail:
    """Convert an ``ImageBatch`` ORM row (with images loaded) to its API schema."""
    images = [
        BatchImageOut(
            id=img.id,
            position=img.position,
            rotation=img.rotation,
            filename=img.filename,
            width=img.width,
            height=img.height,
            url=f"/api/images/batches/{batch.id}/images/{img.id}",
        )
        for img in batch.images
    ]
    return ImageBatchDetail(
        id=batch.id,
        name=batch.name,
        quality=batch.quality,
        page_size=batch.page_size,
        image_count=len(images),
        created_at=batch.created_at,
        updated_at=batch.updated_at,
        images=images,
    )


def _get_batch_or_404(batch_id: int, db: Session, principal: Principal) -> ImageBatch:
    """Fetch a batch, enforcing per-key ownership.

    A batch owned by another key yields 404 rather than 403 so callers cannot
    probe for the existence of other users' batches.
    """
    batch = db.get(ImageBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    if principal.scopes_documents and batch.api_key_id != principal.api_key_id:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


@router.post("/pdf")
async def images_to_pdf(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(..., description="Images, in the desired final page order"),
    rotations: str = Form(
        "", description="Comma-separated clockwise rotation in degrees per image, e.g. '0,90,0'"
    ),
    quality: str = Form("standard", description="Quality preset: high, standard or compact"),
    page_size: str = Form("a4", description="Page layout: a4 (fitted) or original"),
    filename: str = Form("document", description="Base filename for the generated PDF"),
    create_document: bool = Form(
        False,
        description="If true, also create a Document from the PDF and queue OCR processing",
    ),
    language: str = Form("fra", description="Tesseract language, used only if create_document"),
    preprocessing: bool = Form(True, description="Enable image preprocessing, used only if create_document"),
    merge_pages: bool = Form(False, description="Export layout, used only if create_document"),
    principal: Principal = Depends(resolve_principal),
    db: Session = Depends(get_db),
):
    """Assemble uploaded images into a single PDF.

    Stateless: nothing is persisted beyond the lifetime of the request unless
    ``create_document`` is set, in which case the PDF is stored and queued
    through the same OCR pipeline as a direct PDF upload.
    """
    _check_batch_length(len(files))
    _validate_presets(quality, page_size)
    rotation_list = _parse_rotations(rotations, len(files))

    with tempfile.TemporaryDirectory(dir=settings.data_dir) as tmp_dir:
        tmp_path = Path(tmp_dir)
        image_paths: list[Path] = []
        for index, upload in enumerate(files, start=1):
            content = await _read_and_validate_image(upload, index)
            safe_name = sanitize_filename(upload.filename or f"page_{index}", fallback=f"page_{index}")
            image_path = tmp_path / f"{index:04d}_{safe_name}"
            image_path.write_bytes(content)
            image_paths.append(image_path)

        try:
            output_path = imagepdf.build_pdf(
                image_paths,
                tmp_path / "output.pdf",
                rotations=rotation_list,
                quality=quality,
                page_size=page_size,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        base_name = sanitize_filename(filename, fallback="document")

        if create_document:
            stored_name = f"{uuid.uuid4().hex}_{base_name}.pdf"
            dest = settings.uploads_dir / stored_name
            dest.write_bytes(output_path.read_bytes())

            document = Document(
                filename=f"{base_name}.pdf",
                stored_filename=stored_name,
                status=DocumentStatus.QUEUED,
                page_count=len(files),
                language=language,
                preprocessing=preprocessing,
                merge_pages=merge_pages,
                api_key_id=principal.api_key_id,
            )
            db.add(document)
            db.commit()
            db.refresh(document)

            background_tasks.add_task(process_document, document.id)
            log.info("images_to_pdf.document_created", document_id=document.id, pages=len(files))
            return DocumentSummary.model_validate(document)

        pdf_bytes = output_path.read_bytes()
        log.info("images_to_pdf.generated", pages=len(files), quality=quality)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{base_name}.pdf"'},
        )


@router.post("/batches", response_model=ImageBatchDetail, status_code=status.HTTP_201_CREATED)
async def save_batch(
    files: list[UploadFile] = File(..., description="Images, in the desired final page order"),
    rotations: str = Form("", description="Comma-separated clockwise rotation in degrees per image"),
    quality: str = Form("standard", description="Quality preset: high, standard or compact"),
    page_size: str = Form("a4", description="Page layout: a4 (fitted) or original"),
    name: str = Form("Sans titre", description="Human-readable name for the batch"),
    principal: Principal = Depends(resolve_principal),
    db: Session = Depends(get_db),
) -> ImageBatchDetail:
    """Persist a new image batch (order, rotations and files) for later retrieval."""
    _check_batch_length(len(files))
    _validate_presets(quality, page_size)
    rotation_list = _parse_rotations(rotations, len(files))

    batch = ImageBatch(
        name=name.strip() or "Sans titre",
        quality=quality,
        page_size=page_size,
        api_key_id=principal.api_key_id,
    )
    db.add(batch)
    db.flush()  # assign batch.id before writing files to disk

    batch_dir = settings.batches_dir / str(batch.id)
    batch_dir.mkdir(parents=True, exist_ok=True)

    for index, (upload, rotation) in enumerate(zip(files, rotation_list), start=1):
        content = await _read_and_validate_image(upload, index)
        safe_name = sanitize_filename(upload.filename or f"page_{index}", fallback=f"page_{index}")
        stored_name = f"{uuid.uuid4().hex}_{safe_name}"
        (batch_dir / stored_name).write_bytes(content)
        with Image.open(io.BytesIO(content)) as image:
            width, height = image.size

        db.add(
            BatchImage(
                batch_id=batch.id,
                position=index,
                rotation=rotation,
                filename=safe_name,
                stored_filename=stored_name,
                width=width,
                height=height,
            )
        )

    db.commit()
    db.refresh(batch)
    log.info("batch.saved", batch_id=batch.id, images=len(files))
    return _batch_to_schema(batch)


@router.get("/batches", response_model=list[ImageBatchSummary])
async def list_batches(
    principal: Principal = Depends(resolve_principal),
    db: Session = Depends(get_db),
) -> list[ImageBatchSummary]:
    """List saved image batches, newest first.

    A non-admin key only sees the batches it created.
    """
    stmt = select(ImageBatch).order_by(ImageBatch.updated_at.desc())
    if principal.scopes_documents:
        stmt = stmt.where(ImageBatch.api_key_id == principal.api_key_id)
    batches = db.scalars(stmt).all()
    return [
        ImageBatchSummary(
            id=b.id,
            name=b.name,
            quality=b.quality,
            page_size=b.page_size,
            image_count=len(b.images),
            created_at=b.created_at,
            updated_at=b.updated_at,
        )
        for b in batches
    ]


@router.get("/batches/{batch_id}", response_model=ImageBatchDetail)
async def get_batch(
    batch_id: int,
    principal: Principal = Depends(resolve_principal),
    db: Session = Depends(get_db),
) -> ImageBatchDetail:
    """Return a saved batch's metadata and images."""
    batch = _get_batch_or_404(batch_id, db, principal)
    return _batch_to_schema(batch)


@router.put("/batches/{batch_id}", response_model=ImageBatchDetail)
async def update_batch(
    batch_id: int,
    payload: BatchUpdateRequest,
    principal: Principal = Depends(resolve_principal),
    db: Session = Depends(get_db),
) -> ImageBatchDetail:
    """Re-synchronize a saved batch's order, rotations, name or export options.

    Does not accept new files — use ``POST /api/images/batches`` to save a new
    batch, or delete and re-create this one to change its images.
    """
    batch = _get_batch_or_404(batch_id, db, principal)

    if payload.name is not None:
        batch.name = payload.name
    if payload.quality is not None:
        _validate_presets(payload.quality, payload.page_size or batch.page_size)
        batch.quality = payload.quality
    if payload.page_size is not None:
        _validate_presets(payload.quality or batch.quality, payload.page_size)
        batch.page_size = payload.page_size

    if payload.images is not None:
        images_by_id = {img.id: img for img in batch.images}
        for update in payload.images:
            image = images_by_id.get(update.image_id)
            if image is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Image {update.image_id} not found in batch {batch_id}",
                )
            image.position = update.position
            image.rotation = update.rotation

    db.commit()
    db.refresh(batch)
    log.info("batch.updated", batch_id=batch.id)
    return _batch_to_schema(batch)


@router.get("/batches/{batch_id}/images/{image_id}")
async def get_batch_image(
    batch_id: int,
    image_id: int,
    principal: Principal = Depends(resolve_principal),
    db: Session = Depends(get_db),
):
    """Serve the raw bytes of one image within a saved batch."""
    batch = _get_batch_or_404(batch_id, db, principal)
    image = next((img for img in batch.images if img.id == image_id), None)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")

    path = settings.batches_dir / str(batch.id) / image.stored_filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image file missing on disk")

    media_type = mimetypes.guess_type(image.filename)[0] or "application/octet-stream"
    return FileResponse(path=path, media_type=media_type, filename=image.filename)


@router.delete("/batches/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_batch(
    batch_id: int,
    principal: Principal = Depends(resolve_principal),
    db: Session = Depends(get_db),
) -> Response:
    """Delete a saved batch and its images on disk."""
    batch = _get_batch_or_404(batch_id, db, principal)

    batch_dir = settings.batches_dir / str(batch.id)
    if batch_dir.exists():
        for item in batch_dir.iterdir():
            item.unlink(missing_ok=True)
        batch_dir.rmdir()

    db.delete(batch)
    db.commit()
    log.info("batch.deleted", batch_id=batch_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
