"""Outbound webhook delivery.

Lets an API client skip polling: it passes a ``callback_url`` at upload time and
receives a POST once the document is processed, carrying a direct link to the
generated spreadsheet.

Payloads are signed with HMAC-SHA256 over ``"{timestamp}.{body}"`` so the
receiver can authenticate the call and reject replays::

    X-ScanToSheet-Event:     document.completed
    X-ScanToSheet-Timestamp: 1750000000
    X-ScanToSheet-Signature: sha256=<hex digest>

Verification (Python)::

    expected = hmac.new(secret.encode(), f"{ts}.{raw_body}".encode(),
                        hashlib.sha256).hexdigest()
    hmac.compare_digest(expected, signature.removeprefix("sha256="))
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import get_settings
from app.logging_config import get_logger

log = get_logger(__name__)
settings = get_settings()

EVENT_COMPLETED = "document.completed"
EVENT_FAILED = "document.failed"

# Backoff between delivery attempts, in seconds.
_RETRY_BACKOFF = (1.0, 3.0, 9.0)


def is_valid_callback_url(url: str) -> bool:
    """Return True if the URL is a syntactically usable http(s) callback."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def sign(body: str, timestamp: int, secret: str) -> str:
    """Return the ``sha256=…`` signature header value for a payload."""
    digest = hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}.{body}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


def build_payload(document: Any) -> dict[str, Any]:
    """Build the webhook body for a finished document.

    Args:
        document: The processed ``Document`` ORM row.

    Returns:
        A JSON-serializable payload including direct result links.
    """
    base = settings.public_base_url.rstrip("/")
    succeeded = document.status.value == "done"
    payload: dict[str, Any] = {
        "event": EVENT_COMPLETED if succeeded else EVENT_FAILED,
        "document_id": document.id,
        "filename": document.filename,
        "status": document.status.value,
        "page_count": document.page_count,
        "language": document.language,
        "error_message": document.error_message,
    }
    if succeeded:
        payload["download_url"] = (
            f"{base}/api/documents/{document.id}/download?fmt=xlsx"
        )
        payload["download_csv_url"] = (
            f"{base}/api/documents/{document.id}/download?fmt=csv"
        )
        payload["preview_url"] = f"{base}/api/documents/{document.id}/preview"
    return payload


def deliver(document: Any) -> str | None:
    """POST the completion payload to the document's callback URL.

    Retries with backoff on network errors and 5xx responses. A failed delivery
    never fails the document itself — the result stays retrievable over the API.

    Args:
        document: The processed ``Document`` ORM row.

    Returns:
        ``None`` on success, or an error message describing the failure.
    """
    url = document.callback_url
    if not url:
        return None

    payload = build_payload(document)
    body = json.dumps(payload, ensure_ascii=False)
    timestamp = int(time.time())

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "ScanToSheet-Webhook/1.0",
        "X-ScanToSheet-Event": payload["event"],
        "X-ScanToSheet-Timestamp": str(timestamp),
    }
    if settings.webhook_secret:
        headers["X-ScanToSheet-Signature"] = sign(body, timestamp, settings.webhook_secret)

    attempts = max(1, settings.webhook_max_attempts)
    last_error = "unknown error"

    for attempt in range(1, attempts + 1):
        try:
            response = httpx.post(
                url,
                content=body.encode("utf-8"),
                headers=headers,
                timeout=settings.webhook_timeout_seconds,
            )
            if response.status_code < 300:
                log.info(
                    "webhook.delivered",
                    document_id=document.id,
                    status_code=response.status_code,
                    attempt=attempt,
                )
                return None
            # 4xx means the receiver rejected us; retrying will not help.
            last_error = f"HTTP {response.status_code}"
            if response.status_code < 500:
                break
        except Exception as exc:  # noqa: BLE001 - network failures are expected
            last_error = str(exc)

        log.warning(
            "webhook.attempt_failed",
            document_id=document.id,
            attempt=attempt,
            error=last_error,
        )
        if attempt < attempts:
            time.sleep(_RETRY_BACKOFF[min(attempt - 1, len(_RETRY_BACKOFF) - 1)])

    log.error("webhook.failed", document_id=document.id, error=last_error)
    return last_error
