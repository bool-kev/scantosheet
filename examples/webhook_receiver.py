"""Minimal webhook receiver, to test the ScanToSheet callback chain end to end.

Standard library only — no dependencies. It verifies the HMAC signature, rejects
stale or forged calls, prints the payload and downloads the generated
spreadsheet.

Usage::

    # Must match the server's WEBHOOK_SECRET (omit to skip verification)
    export WEBHOOK_SECRET=...            # PowerShell: $env:WEBHOOK_SECRET="..."
    python webhook_receiver.py --port 9000 --out-dir ./received

Then upload with a callback pointing here::

    curl -X POST http://localhost:8000/api/documents \\
      -F "file=@scan.pdf" -F "language=fra" \\
      -F "callback_url=http://127.0.0.1:9000/hook"
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# Reject callbacks whose timestamp is older than this, to block replays.
MAX_SIGNATURE_AGE_SECONDS = 300

SECRET = os.environ.get("WEBHOOK_SECRET", "")
API_KEY = os.environ.get("SCANTOSHEET_API_KEY", "")
OUT_DIR = Path("./received")


def verify(raw_body: bytes, timestamp: str, signature: str, secret: str) -> bool:
    """Return True if the signature matches the documented HMAC scheme."""
    expected = hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}.".encode("utf-8") + raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature.removeprefix("sha256="))


def download(url: str, destination: Path) -> int:
    """Fetch the result file, returning the number of bytes written."""
    request = urllib.request.Request(url)
    if API_KEY:
        request.add_header("X-API-Key", API_KEY)
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return len(payload)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length)

        event = self.headers.get("X-ScanToSheet-Event", "?")
        timestamp = self.headers.get("X-ScanToSheet-Timestamp", "")
        signature = self.headers.get("X-ScanToSheet-Signature", "")

        print(f"\n--- {event} on {self.path} ---")

        if SECRET:
            if not signature:
                self._reject("missing signature")
                return
            if not verify(raw_body, timestamp, signature, SECRET):
                self._reject("BAD SIGNATURE - forged or wrong secret")
                return
            age = abs(int(time.time()) - int(timestamp or 0))
            if age > MAX_SIGNATURE_AGE_SECONDS:
                self._reject(f"stale timestamp ({age}s old)")
                return
            print(f"signature OK (age {age}s)")
        else:
            print("WARNING: WEBHOOK_SECRET unset - signature NOT verified")

        payload = json.loads(raw_body.decode("utf-8"))
        print(json.dumps(payload, indent=2, ensure_ascii=False))

        # Answer immediately; real integrations should queue the heavy work.
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"received":true}')

        url = payload.get("download_url")
        if url:
            target = OUT_DIR / f"{payload['document_id']}_{Path(payload['filename']).stem}.xlsx"
            try:
                size = download(url, target)
                print(f"downloaded {target} ({size} bytes)")
            except Exception as exc:  # noqa: BLE001 - report and keep serving
                print(f"download failed: {exc}")

    def _reject(self, reason: str) -> None:
        print(f"REJECTED: {reason}")
        self.send_response(401)
        self.end_headers()

    def log_message(self, *_args) -> None:
        """Silence the default per-request access log."""


def main() -> int:
    global OUT_DIR
    parser = argparse.ArgumentParser(description="ScanToSheet webhook receiver")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--out-dir", type=Path, default=Path("./received"))
    args = parser.parse_args()

    OUT_DIR = args.out_dir
    # Without this, Python block-buffers stdout when it is piped to a file or
    # another process, and none of the callback logs appear until exit.
    sys.stdout.reconfigure(line_buffering=True)

    print(f"Listening on http://{args.host}:{args.port}/hook")
    print(f"Signature verification: {'ON' if SECRET else 'OFF (set WEBHOOK_SECRET)'}")
    HTTPServer((args.host, args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
