"""/api/admin endpoints — API key administration.

Every route here requires an administrator key (or the bootstrap
``ADMIN_API_KEY``). Keys are minted, listed and revoked, but their secret is
only ever exposed once, in the creation response.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.logging_config import get_logger
from app.models import ApiKey
from app.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from app.security import Principal, generate_key, require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])
log = get_logger(__name__)


@router.post("/keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreate,
    admin: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ApiKeyCreated:
    """Mint a new API key for a user.

    The plaintext key is returned **once** in this response and cannot be
    retrieved afterwards — only its hash is stored.
    """
    plaintext, prefix, key_hash = generate_key()
    record = ApiKey(
        label=payload.label,
        prefix=prefix,
        key_hash=key_hash,
        role=payload.role,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    log.info(
        "apikey.created",
        key_id=record.id,
        label=record.label,
        role=record.role.value,
        by=admin.label,
    )
    return ApiKeyCreated(**ApiKeyOut.model_validate(record).model_dump(), key=plaintext)


@router.get("/keys", response_model=list[ApiKeyOut])
async def list_api_keys(
    _admin: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[ApiKeyOut]:
    """List all API keys with their metadata (never their secret)."""
    records = db.scalars(select(ApiKey).order_by(ApiKey.created_at.desc())).all()
    return [ApiKeyOut.model_validate(r) for r in records]


@router.delete("/keys/{key_id}", response_model=ApiKeyOut)
async def revoke_api_key(
    key_id: int,
    admin: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ApiKeyOut:
    """Revoke a key. It is deactivated, not deleted, so the audit trail remains.

    Documents uploaded with this key are preserved.
    """
    record = db.get(ApiKey, key_id)
    if record is None:
        raise HTTPException(status_code=404, detail="API key not found")
    if not record.is_active:
        raise HTTPException(status_code=409, detail="API key is already revoked")

    record.is_active = False
    record.revoked_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(record)

    log.info("apikey.revoked", key_id=record.id, label=record.label, by=admin.label)
    return ApiKeyOut.model_validate(record)
