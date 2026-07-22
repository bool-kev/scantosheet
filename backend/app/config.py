"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings.

    All values are overridable through environment variables (or a ``.env``
    file). See ``.env.example`` at the repository root for the full list.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:5173"

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

    @property
    def cors_origin_list(self) -> list[str]:
        """Return CORS origins as a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def max_file_size_bytes(self) -> int:
        """Maximum upload size in bytes."""
        return self.max_file_size_mb * 1024 * 1024

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
        ):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""
    return Settings()
