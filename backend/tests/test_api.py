"""API smoke tests using FastAPI's TestClient.

These cover the request/response wiring that does not require Tesseract or
Poppler (health, listing, validation errors, 404s). The full OCR path is
exercised via Docker.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    # Entering the context manager triggers the lifespan (init_db).
    with TestClient(app) as test_client:
        yield test_client


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "tesseract_available" in body


def test_list_documents_empty_ok(client: TestClient) -> None:
    response = client.get("/api/documents")
    assert response.status_code == 200
    body = response.json()
    assert set(body) >= {"items", "total", "page", "page_size"}


def test_upload_rejects_non_pdf(client: TestClient) -> None:
    response = client.post(
        "/api/documents",
        files={"file": ("note.txt", b"just some text", "text/plain")},
        data={"language": "fra", "preprocessing": "true"},
    )
    assert response.status_code == 400
    assert "not a valid PDF" in response.json()["detail"]


def test_upload_rejects_empty_file(client: TestClient) -> None:
    response = client.post(
        "/api/documents",
        files={"file": ("empty.pdf", b"", "application/pdf")},
        data={"language": "fra"},
    )
    assert response.status_code == 400


def test_get_missing_document_404(client: TestClient) -> None:
    response = client.get("/api/documents/999999")
    assert response.status_code == 404
