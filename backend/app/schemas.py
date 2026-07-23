"""Pydantic request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import ApiKeyRole, DocumentStatus


class Cell(BaseModel):
    """A single structured table cell with its OCR confidence."""

    value: str = ""
    confidence: float = 0.0


class DocumentSummary(BaseModel):
    """Compact document representation for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    status: DocumentStatus
    page_count: int
    language: str
    preprocessing: bool
    merge_pages: bool = False
    error_message: str | None = None
    callback_url: str | None = None
    webhook_error: str | None = None
    created_at: datetime
    updated_at: datetime


class PageData(BaseModel):
    """OCR + structured data for one page."""

    page_number: int
    text: str
    data: list[list[Cell]]
    mean_confidence: float
    warning: str | None = None


class DocumentDetail(DocumentSummary):
    """Full document representation including per-page OCR data."""

    pages: list[PageData] = Field(default_factory=list)


class DocumentList(BaseModel):
    """Paginated document list."""

    items: list[DocumentSummary]
    total: int
    page: int
    page_size: int


class PreviewResponse(BaseModel):
    """Structured, page-by-page preview data."""

    document_id: int
    filename: str
    status: DocumentStatus
    pages: list[PageData]


class PageDataUpdate(BaseModel):
    """Corrected structured data for a single page."""

    page_number: int
    data: list[list[Cell]]


class DataUpdateRequest(BaseModel):
    """Payload to update/correct extracted data before export."""

    pages: list[PageDataUpdate]


class BatchImageOut(BaseModel):
    """One image within a saved batch, with its order, rotation and URL."""

    id: int
    position: int
    rotation: int
    filename: str
    width: int
    height: int
    url: str


class ImageBatchSummary(BaseModel):
    """Compact saved-batch representation for list views."""

    id: int
    name: str
    quality: str
    page_size: str
    image_count: int
    created_at: datetime
    updated_at: datetime


class ImageBatchDetail(ImageBatchSummary):
    """Full saved-batch representation including its images."""

    images: list[BatchImageOut] = Field(default_factory=list)


class BatchImageUpdate(BaseModel):
    """New order/rotation for one existing image in a batch."""

    image_id: int
    position: int
    rotation: int = Field(ge=0, le=270)


class BatchUpdateRequest(BaseModel):
    """Payload to re-synchronize an existing batch's order, rotation or options."""

    name: str | None = Field(default=None, min_length=1, max_length=256)
    quality: str | None = None
    page_size: str | None = None
    images: list[BatchImageUpdate] | None = None


class HealthResponse(BaseModel):
    """Health check payload."""

    status: str = "ok"
    tesseract_available: bool
    tesseract_languages: list[str] = Field(default_factory=list)
    auth_enabled: bool = False


class ApiKeyCreate(BaseModel):
    """Request to mint a new API key."""

    label: str = Field(min_length=1, max_length=128, description="Human-readable owner name")
    role: ApiKeyRole = ApiKeyRole.USER


class ApiKeyOut(BaseModel):
    """API key metadata. Never contains the secret."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    prefix: str
    role: ApiKeyRole
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class ApiKeyCreated(ApiKeyOut):
    """Creation response — the only time the plaintext key is ever returned."""

    key: str = Field(description="Store this now; it cannot be retrieved again")
