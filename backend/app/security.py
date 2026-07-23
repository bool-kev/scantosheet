"""API key generation, verification and FastAPI auth dependencies.

Keys look like ``sts_<prefix>_<secret>``. Only the SHA-256 digest of the full
key is stored; the plaintext is returned once at creation and is unrecoverable
afterwards. Because keys are high-entropy random secrets (not user-chosen
passwords), a plain SHA-256 digest is sufficient — a slow KDF would only add
latency to every request without adding meaningful resistance.

Two independent surfaces:

* **Document endpoints** use :func:`resolve_principal` and follow the
  ``AUTH_ENABLED`` setting — open by default, so the web UI can import and
  browse without a key.
* **Key administration** uses :func:`require_admin` and is *always*
  authenticated, regardless of ``AUTH_ENABLED``, so nobody can mint keys on an
  otherwise open deployment.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.logging_config import get_logger
from app.models import ApiKey, ApiKeyRole

log = get_logger(__name__)
settings = get_settings()

KEY_PREFIX = "sts"
_PREFIX_BYTES = 4  # 8 hex chars
_SECRET_BYTES = 24  # 48 hex chars

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass(frozen=True)
class Principal:
    """The authenticated caller for the current request."""

    label: str
    role: ApiKeyRole
    api_key_id: int | None = None

    @property
    def is_admin(self) -> bool:
        return self.role is ApiKeyRole.ADMIN

    @property
    def scopes_documents(self) -> bool:
        """True when this caller may only see its own documents."""
        return self.api_key_id is not None and not self.is_admin


# Used when authentication is disabled: full access, no per-key scoping.
ANONYMOUS = Principal(label="anonymous", role=ApiKeyRole.ADMIN, api_key_id=None)


def hash_key(plaintext: str) -> str:
    """Return the SHA-256 hex digest of an API key."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def generate_key() -> tuple[str, str, str]:
    """Mint a new API key.

    Returns:
        A ``(plaintext, prefix, key_hash)`` tuple. The plaintext must be shown to
        the operator once and then discarded.
    """
    prefix = secrets.token_hex(_PREFIX_BYTES)
    secret = secrets.token_hex(_SECRET_BYTES)
    plaintext = f"{KEY_PREFIX}_{prefix}_{secret}"
    return plaintext, prefix, hash_key(plaintext)


def _parse_prefix(plaintext: str) -> str | None:
    """Extract the lookup prefix from a well-formed key."""
    parts = plaintext.split("_")
    if len(parts) != 3 or parts[0] != KEY_PREFIX:
        return None
    return parts[1]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "ApiKey"},
    )


def resolve_principal(
    raw_key: str | None = Security(api_key_header),
    db: Session = Depends(get_db),
) -> Principal:
    """Authenticate the request and return its ``Principal``.

    When ``AUTH_ENABLED`` is false the request is accepted as ``ANONYMOUS`` with
    full, unscoped access — preserving the open self-hosted default.

    Raises:
        HTTPException: 401 when the key is missing, malformed, unknown or
            revoked.
    """
    if not settings.auth_enabled:
        return ANONYMOUS

    if not raw_key:
        raise _unauthorized("Missing X-API-Key header")

    # Bootstrap admin key from the environment (not stored in the database).
    if settings.admin_api_key and secrets.compare_digest(
        raw_key, settings.admin_api_key
    ):
        return Principal(label="bootstrap-admin", role=ApiKeyRole.ADMIN)

    prefix = _parse_prefix(raw_key)
    if prefix is None:
        raise _unauthorized("Malformed API key")

    record = db.scalar(select(ApiKey).where(ApiKey.prefix == prefix))
    if record is None or not secrets.compare_digest(record.key_hash, hash_key(raw_key)):
        raise _unauthorized("Invalid API key")
    if not record.is_active:
        raise _unauthorized("API key has been revoked")

    record.last_used_at = datetime.now(timezone.utc)
    db.commit()

    return Principal(label=record.label, role=record.role, api_key_id=record.id)


def seed_frontend_key(db: Session) -> None:
    """Ensure the frontend's shared key exists in the database as a 'user' key.

    ``settings.frontend_api_key`` (env ``VITE_API_KEY``) is the plaintext key
    baked into the frontend bundle. Rather than requiring an operator to mint
    it by hand through ``/api/admin/keys`` before the UI can do anything,
    the server seeds (or repairs) the matching row on every startup — this is
    idempotent and self-healing if the key value in ``.env`` changes.

    No-op when ``VITE_API_KEY`` is unset (open mode, or key managed manually).
    """
    plaintext = settings.frontend_api_key
    if not plaintext:
        return

    prefix = _parse_prefix(plaintext)
    if prefix is None:
        log.warning("frontend_key.malformed", detail="VITE_API_KEY is not a valid sts_<prefix>_<secret> key")
        return

    key_hash = hash_key(plaintext)
    record = db.scalar(select(ApiKey).where(ApiKey.prefix == prefix))
    if record is None:
        db.add(ApiKey(label="frontend", prefix=prefix, key_hash=key_hash, role=ApiKeyRole.USER))
        db.commit()
        log.info("frontend_key.seeded", prefix=prefix)
        return

    changed = False
    if record.key_hash != key_hash:
        record.key_hash = key_hash
        changed = True
    if not record.is_active:
        record.is_active = True
        record.revoked_at = None
        changed = True
    if changed:
        db.commit()
        log.info("frontend_key.updated", prefix=prefix)


def require_admin(
    raw_key: str | None = Security(api_key_header),
    db: Session = Depends(get_db),
) -> Principal:
    """Dependency enforcing administrator privileges.

    Unlike :func:`resolve_principal`, this **always** authenticates, even when
    ``AUTH_ENABLED`` is false. Key management is a privileged surface: leaving it
    open in the default "trusted network" mode would let anyone mint keys.

    Raises:
        HTTPException: 503 when no administrator credential is configured at
            all, 401 for a missing/invalid key, 403 for a valid non-admin key.
    """
    has_db_admin = (
        db.scalar(
            select(ApiKey).where(
                ApiKey.role == ApiKeyRole.ADMIN, ApiKey.is_active.is_(True)
            )
        )
        is not None
    )
    if not settings.admin_api_key and not has_db_admin:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Key administration is not configured. Set ADMIN_API_KEY in the "
                "server environment and restart."
            ),
        )

    if not raw_key:
        raise _unauthorized("Missing X-API-Key header")

    if settings.admin_api_key and secrets.compare_digest(
        raw_key, settings.admin_api_key
    ):
        return Principal(label="bootstrap-admin", role=ApiKeyRole.ADMIN)

    prefix = _parse_prefix(raw_key)
    if prefix is None:
        raise _unauthorized("Malformed API key")

    record = db.scalar(select(ApiKey).where(ApiKey.prefix == prefix))
    if record is None or not secrets.compare_digest(record.key_hash, hash_key(raw_key)):
        raise _unauthorized("Invalid API key")
    if not record.is_active:
        raise _unauthorized("API key has been revoked")
    if record.role is not ApiKeyRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required",
        )

    record.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return Principal(label=record.label, role=record.role, api_key_id=record.id)
