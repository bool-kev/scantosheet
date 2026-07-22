"""SQLAlchemy engine, session factory and declarative base."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()
settings.ensure_dirs()

# check_same_thread=False is required because background tasks run in a
# different thread than the request that spawned them.
engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False},
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables and apply lightweight schema migrations."""
    # Import models so they are registered on the metadata before create_all.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _apply_migrations()


# Columns added after the initial release. ``create_all`` only creates missing
# tables, never alters existing ones, so new columns are added here instead of
# pulling in a full migration tool for a single-file SQLite database.
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "documents": {
        "api_key_id": "INTEGER REFERENCES api_keys(id)",
        "callback_url": "VARCHAR(2048)",
        "webhook_error": "TEXT",
        "merge_pages": "BOOLEAN NOT NULL DEFAULT 0",
    },
}


def _apply_migrations() -> None:
    """Add columns that are missing from an existing database file."""
    from sqlalchemy import text

    with engine.begin() as connection:
        for table, columns in _ADDED_COLUMNS.items():
            existing = {
                row[1]
                for row in connection.execute(text(f"PRAGMA table_info({table})"))
            }
            if not existing:
                continue  # table does not exist yet; create_all handled it
            for name, ddl in columns.items():
                if name not in existing:
                    connection.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
                    )
