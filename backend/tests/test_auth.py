"""API key authentication, admin key management and per-key document scoping."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import SessionLocal, init_db
from app.models import ApiKey, ApiKeyRole, Document, DocumentStatus, ImageBatch

BOOTSTRAP_ADMIN = "sts_bootstrap_admin_secret"


@pytest.fixture
def auth_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A TestClient with authentication switched on for the duration of a test."""
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "admin_api_key", BOOTSTRAP_ADMIN)
    from app.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture
def open_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A TestClient with document auth disabled (the default posture).

    An admin credential is still configured: key administration is a separate,
    always-authenticated surface.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(settings, "admin_api_key", BOOTSTRAP_ADMIN)
    from app.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture
def unconfigured_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A TestClient with no administrator credential configured at all."""
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(settings, "admin_api_key", None)
    from app.main import app

    with TestClient(app) as client:
        yield client


def _admin(key: str = BOOTSTRAP_ADMIN) -> dict[str, str]:
    return {"X-API-Key": key}


def _create_key(client: TestClient, label: str, role: str = "user") -> str:
    response = client.post(
        "/api/admin/keys", json={"label": label, "role": role}, headers=_admin()
    )
    assert response.status_code == 201, response.text
    return response.json()["key"]


# --------------------------------------------------------------------------- #
# Auth disabled (default)
# --------------------------------------------------------------------------- #


def test_open_mode_needs_no_key(open_client: TestClient) -> None:
    """Document endpoints stay open so the web UI works without a key."""
    assert open_client.get("/api/documents").status_code == 200
    assert open_client.get("/api/health").json()["auth_enabled"] is False


def test_admin_is_protected_even_when_document_auth_is_off(
    open_client: TestClient,
) -> None:
    """Key administration must never inherit the open posture."""
    assert open_client.get("/api/admin/keys").status_code == 401
    assert (
        open_client.post("/api/admin/keys", json={"label": "evil"}).status_code == 401
    )
    # ...but the configured admin credential still works.
    assert open_client.get("/api/admin/keys", headers=_admin()).status_code == 200


def test_admin_without_credential_reports_misconfiguration(
    unconfigured_client: TestClient,
) -> None:
    """With no ADMIN_API_KEY and no admin key in DB, say so explicitly."""
    # Guarantee the precondition: a database-backed admin key left behind by
    # another test would legitimately keep the admin API reachable.
    db = SessionLocal()
    for record in db.query(ApiKey).filter(ApiKey.role == ApiKeyRole.ADMIN).all():
        record.is_active = False
    db.commit()
    db.close()

    response = unconfigured_client.get("/api/admin/keys", headers=_admin())
    assert response.status_code == 503
    assert "ADMIN_API_KEY" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# Auth enabled
# --------------------------------------------------------------------------- #


def test_missing_key_is_rejected(auth_client: TestClient) -> None:
    response = auth_client.get("/api/documents")
    assert response.status_code == 401
    assert "Missing" in response.json()["detail"]


def test_malformed_and_unknown_keys_are_rejected(auth_client: TestClient) -> None:
    assert auth_client.get("/api/documents", headers={"X-API-Key": "nope"}).status_code == 401
    unknown = "sts_deadbeef_" + "0" * 48
    assert auth_client.get("/api/documents", headers={"X-API-Key": unknown}).status_code == 401


def test_health_stays_public_when_auth_enabled(auth_client: TestClient) -> None:
    """Health must remain reachable without a key (container healthcheck)."""
    response = auth_client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["auth_enabled"] is True


def test_bootstrap_admin_can_mint_and_use_keys(auth_client: TestClient) -> None:
    created = auth_client.post(
        "/api/admin/keys", json={"label": "Alice", "role": "user"}, headers=_admin()
    )
    assert created.status_code == 201
    body = created.json()
    assert body["key"].startswith("sts_")
    assert body["label"] == "Alice"
    assert body["role"] == ApiKeyRole.USER.value

    # The minted key authenticates.
    assert auth_client.get(
        "/api/documents", headers={"X-API-Key": body["key"]}
    ).status_code == 200


def test_secret_is_never_returned_again(auth_client: TestClient) -> None:
    plaintext = _create_key(auth_client, "Bob")
    listing = auth_client.get("/api/admin/keys", headers=_admin())
    assert listing.status_code == 200
    for item in listing.json():
        assert "key" not in item
        assert plaintext not in str(item)


def test_non_admin_cannot_manage_keys(auth_client: TestClient) -> None:
    user_key = _create_key(auth_client, "Carol")
    response = auth_client.get("/api/admin/keys", headers={"X-API-Key": user_key})
    assert response.status_code == 403
    create = auth_client.post(
        "/api/admin/keys", json={"label": "evil"}, headers={"X-API-Key": user_key}
    )
    assert create.status_code == 403


def test_admin_role_key_can_manage_keys(auth_client: TestClient) -> None:
    admin_key = _create_key(auth_client, "Dana", role="admin")
    assert auth_client.get(
        "/api/admin/keys", headers={"X-API-Key": admin_key}
    ).status_code == 200


def test_revoked_key_is_refused(auth_client: TestClient) -> None:
    user_key = _create_key(auth_client, "Erin")
    key_id = [
        k for k in auth_client.get("/api/admin/keys", headers=_admin()).json()
        if k["label"] == "Erin"
    ][0]["id"]

    revoked = auth_client.delete(f"/api/admin/keys/{key_id}", headers=_admin())
    assert revoked.status_code == 200
    assert revoked.json()["is_active"] is False

    response = auth_client.get("/api/documents", headers={"X-API-Key": user_key})
    assert response.status_code == 401
    assert "revoked" in response.json()["detail"].lower()

    # Revoking twice is a conflict, not a silent success.
    assert auth_client.delete(f"/api/admin/keys/{key_id}", headers=_admin()).status_code == 409


# --------------------------------------------------------------------------- #
# Per-key document scoping
# --------------------------------------------------------------------------- #


def _seed_document(label_key_id: int | None, filename: str) -> int:
    db = SessionLocal()
    doc = Document(
        filename=filename,
        stored_filename=filename,
        status=DocumentStatus.DONE,
        page_count=1,
        language="fra",
        preprocessing=True,
        api_key_id=label_key_id,
    )
    db.add(doc)
    db.commit()
    doc_id = doc.id
    db.close()
    return doc_id


def _key_id_for(client: TestClient, label: str) -> int:
    keys = client.get("/api/admin/keys", headers=_admin()).json()
    return [k for k in keys if k["label"] == label][0]["id"]


def test_users_only_see_their_own_documents(auth_client: TestClient) -> None:
    init_db()
    key_a = _create_key(auth_client, "UserA")
    key_b = _create_key(auth_client, "UserB")
    id_a = _seed_document(_key_id_for(auth_client, "UserA"), "a.pdf")
    id_b = _seed_document(_key_id_for(auth_client, "UserB"), "b.pdf")

    listing_a = auth_client.get("/api/documents", headers={"X-API-Key": key_a}).json()
    names_a = {item["filename"] for item in listing_a["items"]}
    assert "a.pdf" in names_a
    assert "b.pdf" not in names_a

    # Cross-tenant access is masked as 404, never 403.
    assert auth_client.get(f"/api/documents/{id_b}", headers={"X-API-Key": key_a}).status_code == 404
    assert auth_client.get(f"/api/documents/{id_a}", headers={"X-API-Key": key_a}).status_code == 200
    # Deleting someone else's document is refused too.
    assert auth_client.delete(
        f"/api/documents/{id_b}", headers={"X-API-Key": key_a}
    ).status_code == 404
    # ...and B still sees its own document.
    assert auth_client.get(f"/api/documents/{id_b}", headers={"X-API-Key": key_b}).status_code == 200


def test_admin_sees_every_document(auth_client: TestClient) -> None:
    init_db()
    _create_key(auth_client, "UserC")
    doc_id = _seed_document(_key_id_for(auth_client, "UserC"), "c.pdf")
    assert auth_client.get(f"/api/documents/{doc_id}", headers=_admin()).status_code == 200


def _seed_batch(api_key_id: int | None, name: str) -> int:
    db = SessionLocal()
    batch = ImageBatch(name=name, quality="standard", page_size="a4", api_key_id=api_key_id)
    db.add(batch)
    db.commit()
    batch_id = batch.id
    db.close()
    return batch_id


def test_users_only_see_their_own_image_batches(auth_client: TestClient) -> None:
    """Image batches follow the same per-key scoping as documents."""
    init_db()
    key_a = _create_key(auth_client, "BatchUserA")
    key_b = _create_key(auth_client, "BatchUserB")
    id_a = _seed_batch(_key_id_for(auth_client, "BatchUserA"), "lot-a")
    id_b = _seed_batch(_key_id_for(auth_client, "BatchUserB"), "lot-b")

    listing_a = auth_client.get(
        "/api/images/batches", headers={"X-API-Key": key_a}
    ).json()
    names_a = {item["name"] for item in listing_a}
    assert "lot-a" in names_a
    assert "lot-b" not in names_a

    # Cross-tenant access is masked as 404, never 403.
    assert auth_client.get(
        f"/api/images/batches/{id_b}", headers={"X-API-Key": key_a}
    ).status_code == 404
    assert auth_client.get(
        f"/api/images/batches/{id_a}", headers={"X-API-Key": key_a}
    ).status_code == 200
    assert auth_client.delete(
        f"/api/images/batches/{id_b}", headers={"X-API-Key": key_a}
    ).status_code == 404
    assert auth_client.get(
        f"/api/images/batches/{id_b}", headers={"X-API-Key": key_b}
    ).status_code == 200
