"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.logging_config import configure_logging, get_logger
from app.routers import admin, documents
from app.schemas import HealthResponse
from app.services import ocr

configure_logging()
log = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize storage and database on startup."""
    settings.ensure_dirs()
    init_db()
    log.info("app.startup", data_dir=str(settings.data_dir))
    yield
    log.info("app.shutdown")


app = FastAPI(
    title="ScanToSheet API",
    description="Self-hosted OCR service converting scanned PDFs into structured spreadsheets.",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Browser clients need this to read the server-provided download filename.
    expose_headers=["Content-Disposition"],
)

app.include_router(documents.router)
app.include_router(admin.router)


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    """Report service health, Tesseract availability and auth mode.

    Intentionally unauthenticated so it can be used as a container healthcheck.
    """
    return HealthResponse(
        status="ok",
        tesseract_available=ocr.is_available(),
        tesseract_languages=ocr.available_languages(),
        auth_enabled=settings.auth_enabled,
    )
