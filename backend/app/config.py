"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings.

    All values are overridable through environment variables (or a ``.env``
    file). See ``.env.example`` at the repository root for the full list.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Server
    host: str = "0.0.0.0"
    port: int = 8082
    cors_origins: str = "http://localhost:8081,http://localhost:8000"
    # Optional regex matching additional allowed origins, for cases where an
    # explicit list is impractical (preview deployments, wildcard subdomains).
    cors_origin_regex: str | None = None

    # Storage
    data_dir: Path = Path("/data")
    max_file_size_mb: int = 50

    # OCR
    tesseract_lang: str = "fra"
    ocr_dpi: int = 300
    max_workers: int = 2
    enable_preprocessing: bool = True

    # When True, only data inside detected table grids is extracted; text before
    # and after tables (titles, headers, footers, paragraphs) is ignored.
    extract_tables_only: bool = True

    # OCR confidence threshold below which a cell is flagged as "low confidence"
    low_confidence_threshold: int = 70

    # Images -> PDF module
    max_image_size_mb: int = 20
    max_batch_images: int = 200

    # Webhooks
    # Absolute base URL used to build the links sent in webhook payloads. The
    # server cannot infer how it is reached from behind a proxy.
    public_base_url: str = "http://localhost:8082"
    # Shared secret used to sign webhook bodies (HMAC-SHA256). Strongly
    # recommended: without it the receiver cannot authenticate the callback.
    webhook_secret: str | None = None
    webhook_timeout_seconds: float = 10.0
    webhook_max_attempts: int = 3

    # Authentication
    # When True (default) every /api/documents call requires a valid
    # X-API-Key header — closed by default so a guest on the network cannot
    # create or read data. Set to False to fall back to the old "trusted
    # network" open posture.
    auth_enabled: bool = True
    # Bootstrap admin key. Solves the chicken-and-egg problem: it is accepted as
    # an admin credential without existing in the database, so it can be used to
    # mint the first real keys. Leave empty to rely solely on database keys.
    admin_api_key: str | None = None
    # Plaintext key baked into the frontend bundle (same value as the
    # frontend's build-time VITE_API_KEY — shared name so operators only set
    # one secret). Seeded into the database as a 'user'-role key on startup,
    # so the frontend authenticates without anyone minting it by hand via
    # /api/admin/keys.
    frontend_api_key: str | None = Field(default=None, validation_alias="VITE_API_KEY")

    @property
    def cors_origin_list(self) -> list[str]:
        """Return CORS origins as a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def max_file_size_bytes(self) -> int:
        """Maximum upload size in bytes."""
        return self.max_file_size_mb * 1024 * 1024

    @property
    def max_image_size_bytes(self) -> int:
        """Maximum per-image upload size in bytes for the Images -> PDF module."""
        return self.max_image_size_mb * 1024 * 1024

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def pages_dir(self) -> Path:
        return self.data_dir / "pages"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def results_dir(self) -> Path:
        return self.data_dir / "results"

    @property
    def batches_dir(self) -> Path:
        return self.data_dir / "batches"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "scantosheet.db"

    def ensure_dirs(self) -> None:
        """Create all storage directories if they do not yet exist."""
        for directory in (
            self.data_dir,
            self.uploads_dir,
            self.pages_dir,
            self.processed_dir,
            self.results_dir,
            self.batches_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""
    return Settings()
