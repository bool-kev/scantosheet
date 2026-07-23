"""API tests for the Images -> PDF module (/api/images)."""

from __future__ import annotations

import io
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import get_settings
from app.main import app


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    """Auth is covered in test_auth.py; these tests run with auth disabled."""
    settings = get_settings()
    original = settings.auth_enabled
    settings.auth_enabled = False
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        settings.auth_enabled = original


def _image_bytes(color=(255, 0, 0), fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (300, 400), color).save(buf, fmt)
    return buf.getvalue()


def _files(count: int = 2) -> list[tuple[str, tuple[str, bytes, str]]]:
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    return [
        ("files", (f"page{i}.png", _image_bytes(colors[i % 3]), "image/png"))
        for i in range(count)
    ]


def test_images_to_pdf_returns_pdf(client: TestClient) -> None:
    response = client.post(
        "/api/images/pdf",
        files=_files(2),
        data={"quality": "standard", "page_size": "a4", "filename": "lot"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")
    assert "lot.pdf" in response.headers["content-disposition"]


def test_images_to_pdf_with_create_document_queues_ocr(client: TestClient) -> None:
    response = client.post(
        "/api/images/pdf",
        files=_files(2),
        data={"quality": "standard", "page_size": "a4", "create_document": "true"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert body["page_count"] == 2

    detail = client.get(f"/api/documents/{body['id']}")
    assert detail.status_code == 200


def test_images_to_pdf_rejects_non_image(client: TestClient) -> None:
    response = client.post(
        "/api/images/pdf",
        files=[("files", ("note.txt", b"just some text", "text/plain"))],
        data={},
    )
    assert response.status_code == 400
    assert "not a supported image" in response.json()["detail"]


def test_images_to_pdf_rejects_oversized_image(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "max_image_size_mb", 0)
    response = client.post(
        "/api/images/pdf",
        files=[("files", ("page.png", _image_bytes(), "image/png"))],
        data={},
    )
    assert response.status_code == 413


def test_images_to_pdf_rejects_rotation_length_mismatch(client: TestClient) -> None:
    response = client.post(
        "/api/images/pdf",
        files=_files(2),
        data={"rotations": "0,90,180"},
    )
    assert response.status_code == 400
    assert "rotations" in response.json()["detail"]


def test_images_to_pdf_rejects_unknown_quality_preset(client: TestClient) -> None:
    response = client.post(
        "/api/images/pdf",
        files=_files(1),
        data={"quality": "ultra"},
    )
    assert response.status_code == 400


def test_batch_lifecycle_save_get_update_delete(client: TestClient) -> None:
    saved = client.post(
        "/api/images/batches",
        files=_files(2),
        data={"name": "Mon lot", "quality": "standard", "page_size": "a4", "rotations": "0,90"},
    )
    assert saved.status_code == 201, saved.text
    body = saved.json()
    assert body["name"] == "Mon lot"
    assert body["image_count"] == 2
    assert len(body["images"]) == 2
    assert body["images"][0]["rotation"] == 0
    assert body["images"][1]["rotation"] == 90
    batch_id = body["id"]

    fetched = client.get(f"/api/images/batches/{batch_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Mon lot"

    image_id = fetched.json()["images"][0]["id"]
    image_response = client.get(f"/api/images/batches/{batch_id}/images/{image_id}")
    assert image_response.status_code == 200
    assert image_response.content

    first_id = fetched.json()["images"][0]["id"]
    second_id = fetched.json()["images"][1]["id"]
    updated = client.put(
        f"/api/images/batches/{batch_id}",
        json={
            "name": "Lot renomme",
            "images": [
                {"image_id": first_id, "position": 2, "rotation": 180},
                {"image_id": second_id, "position": 1, "rotation": 0},
            ],
        },
    )
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["name"] == "Lot renomme"
    by_id = {img["id"]: img for img in updated_body["images"]}
    assert by_id[first_id]["position"] == 2
    assert by_id[first_id]["rotation"] == 180
    assert by_id[second_id]["position"] == 1

    listing = client.get("/api/images/batches")
    assert listing.status_code == 200
    assert any(b["id"] == batch_id for b in listing.json())

    deleted = client.delete(f"/api/images/batches/{batch_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/images/batches/{batch_id}").status_code == 404


def test_update_batch_rejects_unknown_image_id(client: TestClient) -> None:
    saved = client.post(
        "/api/images/batches",
        files=_files(1),
        data={"name": "Solo"},
    )
    batch_id = saved.json()["id"]

    response = client.put(
        f"/api/images/batches/{batch_id}",
        json={"images": [{"image_id": 999999, "position": 1, "rotation": 0}]},
    )
    assert response.status_code == 404
