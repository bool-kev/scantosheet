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
