# ScanToSheet

Self-hosted OCR web app that converts scanned multi-page PDFs into structured
Excel spreadsheets. Everything runs locally — **no external API calls, no data
leaves your server.**

- **Backend** — Python 3.12 · FastAPI · Tesseract OCR 5 · Poppler · OpenCV · openpyxl · SQLite
- **Frontend** — React 18 · TypeScript · Vite · Tailwind · TanStack Query · react-dropzone

---

## Quick start (Docker)

```bash
cp .env.example .env          # optional — sensible defaults are baked in
docker compose up --build
```

Then open:

- Web UI — http://localhost:5173
- API docs (Swagger) — http://localhost:8000/api/docs
- Health check — http://localhost:8000/api/health

Upload a PDF, watch its status go `queued → processing → done`, then click
**Aperçu** to preview, edit and download the extracted table as Excel or CSV.

Uploaded files, page images and the SQLite database persist in the
`scantosheet-data` Docker volume across restarts.

---

## How it works

```
PDF ──► pdf2image (300 DPI PNG per page)
     ──► preprocess (grayscale → denoise → deskew → adaptive binarize)   [optional]
     ──► Tesseract OCR (text + per-word confidence)
     ──► table detection (OpenCV line grid → cells, fallback: line-by-line)
     ──► editable preview ──► openpyxl / CSV export
```

Processing runs asynchronously via FastAPI `BackgroundTasks`; the frontend polls
for status updates. OCR failures on one page are recorded as page-level warnings
and do not abort the rest of the document.

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/documents` | Upload a PDF (`file`, `language`, `preprocessing`) |
| `GET` | `/api/documents` | List documents (paginated) |
| `GET` | `/api/documents/{id}` | Document metadata + per-page OCR data |
| `GET` | `/api/documents/{id}/preview` | Structured, page-by-page preview data |
| `PUT` | `/api/documents/{id}/data` | Correct extracted cell data before export |
| `GET` | `/api/documents/{id}/download` | Download `?fmt=xlsx\|csv&merge=&delimiter=` |
| `DELETE` | `/api/documents/{id}` | Delete document + files |
| `GET` | `/api/health` | Health + Tesseract availability (always public) |
| `POST` | `/api/admin/keys` | **admin** — mint an API key |
| `GET` | `/api/admin/keys` | **admin** — list keys (never their secret) |
| `DELETE` | `/api/admin/keys/{id}` | **admin** — revoke a key |

---

## API keys (multi-user REST access)

There are **two independent surfaces**:

| Surface | Protection |
|---|---|
| `/api/documents` (import, preview, download) | Follows `AUTH_ENABLED` — **open by default**, so the web UI works with no key |
| `/api/admin` (key management) | **Always authenticated**, whatever `AUTH_ENABLED` is |

Key administration never inherits the open posture: leaving it public on a
"trusted network" deployment would let anyone mint themselves a key.

Set the administrator credential — without it `/api/admin` answers **503**:

```bash
ADMIN_API_KEY=sts_root_$(python -c "import secrets; print(secrets.token_hex(24))")
```

It authenticates as an administrator without existing in the database, solving
the chicken-and-egg problem of creating the first key. Optionally also close the
document API:

```bash
AUTH_ENABLED=true   # now /api/documents needs a key too
```

### Issuing a key to a user

```bash
curl -X POST http://localhost:8000/api/admin/keys \
  -H "X-API-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"label": "Service Compta", "role": "user"}'
```

```json
{ "id": 1, "label": "Service Compta", "prefix": "20210725",
  "role": "user", "is_active": true,
  "key": "sts_20210725_e12937c…" }
```

> The `key` field is returned **once and never again** — only its SHA-256 digest
> is stored. Revoke and re-issue if it is lost.

### Using a key

```bash
curl http://localhost:8000/api/documents -H "X-API-Key: sts_20210725_e12937c…"
curl -X POST http://localhost:8000/api/documents \
  -H "X-API-Key: sts_20210725_e12937c…" \
  -F "file=@scan.pdf" -F "language=fra"
```

### Roles and isolation

| Role | Documents | Key management |
|---|---|---|
| `user` | Only the documents it uploaded | ✗ (403) |
| `admin` | All documents | ✓ |

Cross-tenant access returns **404, not 403**, so a caller cannot probe for the
existence of another user's documents. Revoked keys are deactivated (not
deleted) so the audit trail and their documents survive; a revoked key gets 401.

`GET /api/health` stays public even when auth is on, so it remains usable as a
container healthcheck.

---

## Using the API from a third-party app

Integrating from another codebase? [`examples/INTEGRATION_PROMPTS.md`](examples/INTEGRATION_PROMPTS.md)
contains ready-to-paste implementation prompts for a Laravel backend-for-frontend
plus a React SPA, along with the ScanToSheet-side settings each requires.

A ready-to-run reference client lives in [`examples/client.py`](examples/client.py):

```bash
pip install requests
python examples/client.py scan.pdf                      # open server
python examples/client.py scan.pdf --api-key sts_...    # AUTH_ENABLED=true
python examples/client.py scan.pdf --format csv --out result.csv
```

### Recommended: webhook callback (no polling)

Pass a `callback_url` at upload time and the server POSTs to it once the
document is processed — the spreadsheet is generated **before** the call, so the
`download_url` in the payload serves the file immediately.

```bash
curl -X POST http://localhost:8000/api/documents \
  -H "X-API-Key: $KEY" \
  -F "file=@scan.pdf" -F "language=fra" \
  -F "callback_url=https://my-app.example.com/hooks/scantosheet"
```

Payload delivered to your endpoint:

```json
{
  "event": "document.completed",
  "document_id": 12,
  "filename": "scan.pdf",
  "status": "done",
  "page_count": 16,
  "language": "fra",
  "error_message": null,
  "download_url": "http://localhost:8000/api/documents/12/download?fmt=xlsx",
  "download_csv_url": "http://localhost:8000/api/documents/12/download?fmt=csv",
  "preview_url": "http://localhost:8000/api/documents/12/preview"
}
```

Failures are reported too, as `"event": "document.failed"` with `error_message`
set and no result links.

#### Verifying the signature

Set `WEBHOOK_SECRET` and every call carries an HMAC-SHA256 signature over
`"{timestamp}.{raw_body}"`. **Verify it** — otherwise anyone who learns your
callback URL can forge completions.

```http
X-ScanToSheet-Event:     document.completed
X-ScanToSheet-Timestamp: 1750000000
X-ScanToSheet-Signature: sha256=<hex digest>
```

```python
import hashlib, hmac

def verify(raw_body: bytes, timestamp: str, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature.removeprefix("sha256="))
```

Reject timestamps older than a few minutes to block replays.

#### Testing the callback chain end to end

[`examples/webhook_receiver.py`](examples/webhook_receiver.py) is a dependency-free
receiver that verifies the signature, prints the payload and downloads the
result. Three terminals:

```bash
# 1. Server, with a signing secret and a base URL the receiver can reach
export WEBHOOK_SECRET=demo_secret PUBLIC_BASE_URL=http://127.0.0.1:8000
uvicorn app.main:app --host 127.0.0.1 --port 8000       # in backend/

# 2. Receiver (same secret)
export WEBHOOK_SECRET=demo_secret
python examples/webhook_receiver.py --port 9000 --out-dir ./received

# 3. Upload pointing at the receiver
curl -X POST http://127.0.0.1:8000/api/documents \
  -F "file=@scan.pdf" -F "language=fra" \
  -F "callback_url=http://127.0.0.1:9000/hook"
```

The receiver prints the verified payload and saves the spreadsheet:

```text
--- document.completed on /hook ---
signature OK (age 0s)
{ "document_id": 5, "status": "done", "page_count": 2,
  "download_url": "http://127.0.0.1:8000/api/documents/5/download?fmt=xlsx", ... }
downloaded ./received/5_scan.xlsx (5677 bytes)
```

To confirm the signature check actually bites, replay a forged call — it must be
refused with **401**:

```bash
curl -i -X POST http://127.0.0.1:9000/hook -H "Content-Type: application/json" \
  -H "X-ScanToSheet-Timestamp: $(date +%s)" \
  -H "X-ScanToSheet-Signature: sha256=deadbeef" \
  -d '{"event":"document.completed","document_id":999}'
```

#### Delivery semantics

- Retries up to `WEBHOOK_MAX_ATTEMPTS` (default 3) with 1s/3s/9s backoff on
  network errors and **5xx**. A **4xx** is treated as a definitive rejection and
  is not retried.
- Respond **2xx quickly** and do the work asynchronously; the server waits at
  most `WEBHOOK_TIMEOUT_SECONDS` (default 10).
- A failed delivery never fails the job — the result stays retrievable over the
  API, and the reason is stored in the document's `webhook_error` field.
- `PUBLIC_BASE_URL` must be set to your externally reachable URL, otherwise the
  links in the payload will point at `localhost`.

### Alternative: polling

Without a `callback_url`, processing is still **asynchronous** — the upload
returns immediately with status `queued`, so a client must poll before reading
results.

```text
POST   /api/documents           -> 201 {id, status: "queued"}
GET    /api/documents/{id}      -> poll until status == "done" (or "error")
GET    /api/documents/{id}/preview    -> structured cells
GET    /api/documents/{id}/download   -> .xlsx / .csv bytes
DELETE /api/documents/{id}      -> clean up (optional)
```

### curl

```bash
# 1. Upload
ID=$(curl -s -X POST http://localhost:8000/api/documents \
       -H "X-API-Key: $KEY" \
       -F "file=@scan.pdf" -F "language=fra" | jq -r .id)

# 2. Poll until done
until [ "$(curl -s -H "X-API-Key: $KEY" \
      http://localhost:8000/api/documents/$ID | jq -r .status)" = "done" ]; do
  sleep 2
done

# 3. Download
curl -s -H "X-API-Key: $KEY" \
  "http://localhost:8000/api/documents/$ID/download?fmt=xlsx" -o result.xlsx
```

### JavaScript / TypeScript (server-side)

```ts
const headers = { "X-API-Key": process.env.SCANTOSHEET_KEY! };

const form = new FormData();
form.append("file", new Blob([pdfBytes], { type: "application/pdf" }), "scan.pdf");
form.append("language", "fra");

const { id } = await (
  await fetch(`${API}/api/documents`, { method: "POST", headers, body: form })
).json();

let status = "queued";
while (status === "queued" || status === "processing") {
  await new Promise((r) => setTimeout(r, 2000));
  status = (await (await fetch(`${API}/api/documents/${id}`, { headers })).json()).status;
}
if (status === "error") throw new Error("OCR failed");

const xlsx = await (
  await fetch(`${API}/api/documents/${id}/download?fmt=xlsx`, { headers })
).arrayBuffer();
```

### Response shape

`GET /api/documents/{id}` and `/preview` return each page's table as a 2D array
of cells, so an integrator can consume the data without touching a spreadsheet:

```json
{ "id": 1, "status": "done", "page_count": 16,
  "pages": [
    { "page_number": 2, "mean_confidence": 86.2, "warning": null,
      "data": [ [ {"value": "Intitule du concours", "confidence": 91.0},
                  {"value": "Lieu",                 "confidence": 88.5} ] ] } ] }
```

### Two things that trip integrators up

- **CORS** — a browser app served from another origin is blocked unless you add
  it to `CORS_ORIGINS` (comma-separated). Server-to-server calls are unaffected.
- **Auth scope** — third-party callers need `AUTH_ENABLED=true` plus a `user`
  key to be isolated from other tenants. With the default `AUTH_ENABLED=false`
  the document API is open to anyone who can reach the port.

Interactive docs (Swagger) are always at `/api/docs`, and the OpenAPI schema at
`/api/openapi.json` — usable to generate a typed client in any language.

---

## Run without Docker

### Windows (one-time setup)

```powershell
# 1. System binaries
winget install oschwartz10612.Poppler          # Poppler (pdftoppm etc.)
#    Tesseract 5: install from https://github.com/UB-Mannheim/tesseract/wiki

# 2. Tesseract language data (Program Files is often read-only, so use a
#    user-writable tessdata dir and point TESSDATA_PREFIX at it)
$tess = "$env:LOCALAPPDATA\scantosheet-tessdata"
New-Item -ItemType Directory -Force $tess | Out-Null
Copy-Item 'C:\Program Files\Tesseract-OCR\tessdata\eng.traineddata' $tess
Copy-Item 'C:\Program Files\Tesseract-OCR\tessdata\osd.traineddata' $tess
foreach ($l in 'fra','ara') {
  Invoke-WebRequest "https://github.com/tesseract-ocr/tessdata_fast/raw/main/$l.traineddata" `
    -OutFile "$tess\$l.traineddata"
}

# 3. Backend venv
cd backend; python -m venv .venv
.\.venv\Scripts\pip install fastapi "uvicorn[standard]" pydantic pydantic-settings `
  python-multipart SQLAlchemy structlog pytesseract pdf2image Pillow `
  opencv-python-headless numpy openpyxl

# 4. Frontend deps
cd ..\frontend; npm install
```

Then start both servers with the bundled launcher:

```powershell
powershell -ExecutionPolicy Bypass -File .\run-local.ps1
```

`run-local.ps1` auto-detects the Poppler bin, points `TESSDATA_PREFIX` at the
tessdata dir that actually contains `fra`, and starts uvicorn (:8000) + Vite
(:5173) together. `Ctrl+C` stops both.

> On Python 3.14 the pinned versions in `requirements.txt` (which target the
> Python 3.12 Docker image) may lack wheels — install the deps unpinned as in
> step 3 above.

### Linux / macOS

Requires **Tesseract OCR** (with `fra`/`eng`/`ara` language packs) and
**Poppler** installed on the host.

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
DATA_DIR=./data uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

### Tests

```bash
cd backend && pytest          # unit tests for excel / table / pdf services
cd frontend && npm run lint   # TypeScript type-check
```

> Note: `test_services.py` covers the pure-Python services (Excel/CSV export,
> table structuring, PDF magic-byte validation) and runs without Tesseract or
> Poppler. The OCR/PDF-rendering path is exercised end-to-end via Docker.

---

## Configuration

All settings are environment variables — see [`.env.example`](.env.example).
Key ones:

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_FILE_SIZE_MB` | `50` | Max upload size |
| `TESSERACT_LANG` | `fra` | Default OCR language (`fra+eng` to combine) |
| `OCR_DPI` | `300` | PDF render resolution |
| `MAX_WORKERS` | `2` | Concurrent OCR budget |
| `ENABLE_PREPROCESSING` | `true` | Default image preprocessing toggle |
| `EXTRACT_TABLES_ONLY` | `true` | Keep only data inside detected tables |
| `AUTH_ENABLED` | `false` | Require `X-API-Key` on `/api/documents` |
| `ADMIN_API_KEY` | *(empty)* | Admin credential; required to reach `/api/admin` |
| `CORS_ORIGINS` | `http://localhost:5173` | Allowed frontend origins (comma-separated) |
| `CORS_ORIGIN_REGEX` | *(empty)* | Regex for extra origins (preview deploys) |
| `VITE_API_URL` | `http://localhost:8000` | API URL baked into the frontend |

---

## Security notes

- No authentication by default — designed for a trusted network. For exposed
  deployments set `AUTH_ENABLED=true` and issue per-user API keys (see
  [API keys](#api-keys-multi-user-rest-access)).
- API keys are stored as SHA-256 digests, never in plaintext, and compared with
  `secrets.compare_digest` to avoid timing leaks.
- Serve over HTTPS when auth is enabled: an `X-API-Key` header is only as
  private as the transport carrying it.
- Uploads are validated by **magic bytes**, not just extension, and filenames
  are sanitized before storage.
