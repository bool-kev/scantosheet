"""Webhook payload building, HMAC signing, delivery retries and validation."""

from __future__ import annotations

import hashlib
import hmac
import json
from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.models import DocumentStatus
from app.services import webhook


def _page(page_number: int = 1, **overrides):
    """Build a stand-in for a Page ORM row."""
    base = {
        "page_number": page_number,
        "text": "hello",
        "data_json": '[[{"value": "hello", "confidence": 0.9}]]',
        "mean_confidence": 0.9,
        "warning": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _document(status: DocumentStatus = DocumentStatus.DONE, **overrides):
    """Build a stand-in for a processed Document ORM row."""
    base = {
        "id": 7,
        "filename": "scan.pdf",
        "status": status,
        "page_count": 3,
        "language": "fra",
        "error_message": None,
        "callback_url": "https://example.test/hook",
        "pages": [_page(1), _page(2)],
    }
    base.update(overrides)
    return SimpleNamespace(**base)


# --------------------------------------------------------------------------- #
# URL validation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "url",
    ["https://example.test/hook", "http://10.0.0.5:9000/cb"],
)
def test_valid_callback_urls(url: str) -> None:
    assert webhook.is_valid_callback_url(url)


@pytest.mark.parametrize(
    "url",
    ["ftp://example.test/x", "javascript:alert(1)", "/relative/path", "example.test", ""],
)
def test_invalid_callback_urls(url: str) -> None:
    assert not webhook.is_valid_callback_url(url)


# --------------------------------------------------------------------------- #
# Payload
# --------------------------------------------------------------------------- #


def test_payload_for_completed_document(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "public_base_url", "https://ocr.example.com/")
    payload = webhook.build_payload(_document())

    assert payload["event"] == webhook.EVENT_COMPLETED
    assert payload["document_id"] == 7
    assert payload["status"] == "done"
    # Trailing slash on the base URL must not produce a double slash.
    assert payload["download_url"] == (
        "https://ocr.example.com/api/documents/7/download?fmt=xlsx"
    )
    assert payload["preview_url"] == "https://ocr.example.com/api/documents/7/preview"
    assert payload["pages"] == [
        {
            "page_number": 1,
            "text": "hello",
            "data": [[{"value": "hello", "confidence": 0.9}]],
            "mean_confidence": 0.9,
            "warning": None,
        },
        {
            "page_number": 2,
            "text": "hello",
            "data": [[{"value": "hello", "confidence": 0.9}]],
            "mean_confidence": 0.9,
            "warning": None,
        },
    ]


def test_payload_for_failed_document() -> None:
    payload = webhook.build_payload(
        _document(status=DocumentStatus.ERROR, error_message="boom")
    )
    assert payload["event"] == webhook.EVENT_FAILED
    assert payload["error_message"] == "boom"
    # No result links or page data when there is no result.
    assert "download_url" not in payload
    assert "pages" not in payload


# --------------------------------------------------------------------------- #
# Signing
# --------------------------------------------------------------------------- #


def test_signature_matches_documented_verification() -> None:
    body = '{"event":"document.completed"}'
    timestamp = 1_750_000_000
    secret = "topsecret"

    signature = webhook.sign(body, timestamp, secret)

    expected = hmac.new(
        secret.encode(), f"{timestamp}.{body}".encode(), hashlib.sha256
    ).hexdigest()
    assert signature == f"sha256={expected}"


def test_signature_changes_with_timestamp() -> None:
    body = "{}"
    assert webhook.sign(body, 1, "s") != webhook.sign(body, 2, "s")


# --------------------------------------------------------------------------- #
# Delivery
# --------------------------------------------------------------------------- #


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def test_delivery_sends_signed_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "webhook_secret", "topsecret")
    captured: dict = {}

    def fake_post(url, content, headers, timeout):
        captured.update(url=url, content=content, headers=headers)
        return _FakeResponse(200)

    monkeypatch.setattr(webhook.httpx, "post", fake_post)

    assert webhook.deliver(_document()) is None
    assert captured["url"] == "https://example.test/hook"

    body = captured["content"].decode("utf-8")
    assert json.loads(body)["document_id"] == 7
    timestamp = int(captured["headers"]["X-ScanToSheet-Timestamp"])
    assert captured["headers"]["X-ScanToSheet-Signature"] == webhook.sign(
        body, timestamp, "topsecret"
    )
    assert captured["headers"]["X-ScanToSheet-Event"] == "document.completed"


def test_no_signature_header_without_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "webhook_secret", None)
    captured: dict = {}

    monkeypatch.setattr(
        webhook.httpx,
        "post",
        lambda url, content, headers, timeout: (
            captured.update(headers=headers) or _FakeResponse(204)
        ),
    )
    assert webhook.deliver(_document()) is None
    assert "X-ScanToSheet-Signature" not in captured["headers"]


def test_delivery_retries_on_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "webhook_max_attempts", 3)
    monkeypatch.setattr(webhook.time, "sleep", lambda _s: None)  # no real backoff
    calls = {"n": 0}

    def flaky_post(url, content, headers, timeout):
        calls["n"] += 1
        return _FakeResponse(500 if calls["n"] < 3 else 200)

    monkeypatch.setattr(webhook.httpx, "post", flaky_post)

    assert webhook.deliver(_document()) is None
    assert calls["n"] == 3


def test_delivery_does_not_retry_on_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 4xx means the receiver rejected us; retrying is pointless."""
    monkeypatch.setattr(get_settings(), "webhook_max_attempts", 3)
    monkeypatch.setattr(webhook.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def rejecting_post(url, content, headers, timeout):
        calls["n"] += 1
        return _FakeResponse(404)

    monkeypatch.setattr(webhook.httpx, "post", rejecting_post)

    error = webhook.deliver(_document())
    assert error == "HTTP 404"
    assert calls["n"] == 1


def test_delivery_reports_network_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "webhook_max_attempts", 2)
    monkeypatch.setattr(webhook.time, "sleep", lambda _s: None)

    def boom(url, content, headers, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr(webhook.httpx, "post", boom)

    assert webhook.deliver(_document()) == "connection refused"


def test_no_callback_url_is_a_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args, **_kwargs):  # pragma: no cover - must never run
        raise AssertionError("should not POST without a callback_url")

    monkeypatch.setattr(webhook.httpx, "post", fail)
    assert webhook.deliver(_document(callback_url=None)) is None
