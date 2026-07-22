"""Reference ScanToSheet API client for third-party integrations.

Demonstrates the full flow: upload -> poll until processed -> read structured
data -> download the spreadsheet.

Only the standard library plus ``requests`` is required::

    pip install requests

Usage::

    python client.py scan.pdf
    python client.py scan.pdf --api-url http://scantosheet.lan:8000 --api-key sts_...
    python client.py scan.pdf --format csv --out result.csv
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests

DEFAULT_API_URL = "http://localhost:8000"
# Processing is asynchronous; poll until the document leaves the queue.
POLL_INTERVAL_SECONDS = 2.0
DEFAULT_TIMEOUT_SECONDS = 600


class ScanToSheetError(RuntimeError):
    """Raised when the API returns an error or processing fails."""


class ScanToSheetClient:
    """Thin wrapper around the ScanToSheet REST API."""

    def __init__(self, api_url: str = DEFAULT_API_URL, api_key: str | None = None) -> None:
        self.api_url = api_url.rstrip("/")
        self.session = requests.Session()
        if api_key:
            # Required only when the server runs with AUTH_ENABLED=true.
            self.session.headers["X-API-Key"] = api_key

    # -- internal ---------------------------------------------------------- #

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        response = self.session.request(method, f"{self.api_url}{path}", **kwargs)
        if not response.ok:
            try:
                detail = response.json().get("detail", response.reason)
            except ValueError:
                detail = response.reason
            raise ScanToSheetError(f"{method} {path} -> {response.status_code}: {detail}")
        return response

    # -- public API -------------------------------------------------------- #

    def health(self) -> dict:
        """Return service health. Never requires a key."""
        return self._request("GET", "/api/health").json()

    def upload(
        self,
        pdf_path: Path,
        language: str = "fra",
        preprocessing: bool = True,
        merge_pages: bool = False,
        callback_url: str | None = None,
    ) -> dict:
        """Upload a PDF and queue it for OCR. Returns the created document.

        Args:
            merge_pages: Export every page into a single sheet instead of one
                sheet per page. Becomes the document's default export layout.
            callback_url: If given, the server POSTs the result there when done
                and no polling is needed.
        """
        with pdf_path.open("rb") as handle:
            files = {"file": (pdf_path.name, handle, "application/pdf")}
            data = {
                "language": language,
                "preprocessing": str(preprocessing).lower(),
                "merge_pages": str(merge_pages).lower(),
            }
            if callback_url:
                data["callback_url"] = callback_url
            return self._request("POST", "/api/documents", files=files, data=data).json()

    def get(self, document_id: int) -> dict:
        """Fetch a document with its per-page OCR data."""
        return self._request("GET", f"/api/documents/{document_id}").json()

    def wait_until_ready(
        self, document_id: int, timeout: float = DEFAULT_TIMEOUT_SECONDS
    ) -> dict:
        """Poll until the document is processed.

        Raises:
            ScanToSheetError: if processing fails or the timeout elapses.
        """
        deadline = time.monotonic() + timeout
        while True:
            document = self.get(document_id)
            status = document["status"]
            if status == "done":
                return document
            if status == "error":
                raise ScanToSheetError(
                    f"Processing failed: {document.get('error_message')}"
                )
            if time.monotonic() > deadline:
                raise ScanToSheetError(f"Timed out after {timeout}s (status={status})")
            time.sleep(POLL_INTERVAL_SECONDS)

    def preview(self, document_id: int) -> dict:
        """Return the structured, page-by-page table data."""
        return self._request("GET", f"/api/documents/{document_id}/preview").json()

    def download(
        self,
        document_id: int,
        destination: Path,
        fmt: str = "xlsx",
        merge: bool | None = None,
    ) -> Path:
        """Download the extraction as ``xlsx`` or ``csv``.

        Args:
            merge: Leave as ``None`` to use the layout chosen at upload time;
                pass a bool only to override it for this download.
        """
        params: dict[str, str] = {"fmt": fmt}
        if merge is not None:
            params["merge"] = str(merge).lower()
        response = self._request(
            "GET", f"/api/documents/{document_id}/download", params=params
        )
        destination.write_bytes(response.content)
        return destination

    def delete(self, document_id: int) -> None:
        """Delete a document and its files."""
        self._request("DELETE", f"/api/documents/{document_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="ScanToSheet API example client")
    parser.add_argument("pdf", type=Path, help="PDF file to process")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--api-key", default=None, help="Required if AUTH_ENABLED=true")
    parser.add_argument("--language", default="fra", help="fra | eng | ara | fra+eng")
    parser.add_argument("--format", dest="fmt", default="xlsx", choices=["xlsx", "csv"])
    parser.add_argument(
        "--merge", action="store_true", help="All pages in one sheet (set at import)"
    )
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--callback-url",
        default=None,
        help="Get notified instead of polling; the script exits after upload",
    )
    args = parser.parse_args()

    if not args.pdf.is_file():
        print(f"No such file: {args.pdf}", file=sys.stderr)
        return 1

    client = ScanToSheetClient(args.api_url, args.api_key)

    health = client.health()
    print(f"Service OK — auth_enabled={health['auth_enabled']}, "
          f"languages={','.join(health['tesseract_languages'])}")

    document = client.upload(
        args.pdf,
        language=args.language,
        merge_pages=args.merge,
        callback_url=args.callback_url,
    )
    print(f"Uploaded '{document['filename']}' -> id={document['id']} "
          f"({document['page_count']} pages), status={document['status']}")

    if args.callback_url:
        # Nothing left to do: the server will POST the result (with a direct
        # download link) to the callback URL once processing finishes.
        print(f"Result will be POSTed to {args.callback_url} — not polling.")
        return 0

    document = client.wait_until_ready(document["id"])
    print(f"Processed: status={document['status']}")

    # Structured data: pages[].data is a 2D array of {value, confidence} cells.
    preview = client.preview(document["id"])
    for page in preview["pages"]:
        rows = page["data"]
        print(f"  page {page['page_number']}: {len(rows)} rows "
              f"(mean confidence {page['mean_confidence']:.0f}%)")
        if rows:
            print("    first row:", [cell["value"] for cell in rows[0]])

    # merge is already stored on the document; no need to repeat it here.
    out = args.out or args.pdf.with_name(f"{args.pdf.stem}_extracted.{args.fmt}")
    client.download(document["id"], out, fmt=args.fmt)
    print(f"Saved {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
