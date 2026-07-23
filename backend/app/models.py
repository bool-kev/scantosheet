"""SQLAlchemy ORM models."""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DocumentStatus(str, enum.Enum):
    """Lifecycle status of an uploaded document."""

    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"


class ApiKeyRole(str, enum.Enum):
    """Privilege level granted by an API key."""

    ADMIN = "admin"
    USER = "user"


class ApiKey(Base):
    """A hashed API key issued by an administrator.

    The plaintext key is shown once at creation and never stored: only its
    SHA-256 digest is persisted. ``prefix`` is the public, non-secret part used
    to look the key up and to display it in listings.
    """

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[ApiKeyRole] = mapped_column(
        Enum(ApiKeyRole), default=ApiKeyRole.USER, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    documents: Mapped[list[Document]] = relationship(back_populates="owner")


class Document(Base):
    """An uploaded PDF and its processing metadata."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus), default=DocumentStatus.QUEUED, nullable=False
    )
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    language: Mapped[str] = mapped_column(String(32), default="fra", nullable=False)
    preprocessing: Mapped[bool] = mapped_column(default=True, nullable=False)
    # Export layout: all pages in one sheet, instead of one sheet per page.
    merge_pages: Mapped[bool] = mapped_column(default=False, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Optional URL notified once processing completes, instead of polling.
    callback_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    webhook_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Owning API key. NULL for documents created while auth was disabled.
    api_key_id: Mapped[int | None] = mapped_column(
        ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )

    owner: Mapped[ApiKey | None] = relationship(back_populates="documents")
    pages: Mapped[list[Page]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="Page.page_number",
    )


class ImageBatch(Base):
    """A user-organized set of images pending assembly into a PDF."""

    __tablename__ = "image_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), default="Sans titre", nullable=False)
    quality: Mapped[str] = mapped_column(String(16), default="standard", nullable=False)
    page_size: Mapped[str] = mapped_column(String(16), default="a4", nullable=False)
    # Owning API key. NULL for batches created while auth was disabled.
    api_key_id: Mapped[int | None] = mapped_column(
        ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )

    images: Mapped[list[BatchImage]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="BatchImage.position",
    )


class BatchImage(Base):
    """A single image within an :class:`ImageBatch`, with its order and rotation."""

    __tablename__ = "batch_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("image_batches.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    rotation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    width: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    height: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    batch: Mapped[ImageBatch] = relationship(back_populates="images")


class Page(Base):
    """OCR result and structured data for a single PDF page."""

    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # JSON-encoded 2D array of cells: [[{"value": str, "confidence": float}, ...], ...]
    data_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    mean_confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    warning: Mapped[str | None] = mapped_column(Text, nullable=True)

    document: Mapped[Document] = relationship(back_populates="pages")
