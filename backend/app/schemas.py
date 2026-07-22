"""Pydantic request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import DocumentStatus


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
    error_message: str | None = None
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
