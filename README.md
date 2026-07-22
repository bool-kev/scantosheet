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
| `GET` | `/api/health` | Health + Tesseract availability |

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
| `CORS_ORIGINS` | `http://localhost:5173` | Allowed frontend origins |
| `VITE_API_URL` | `http://localhost:8000` | API URL baked into the frontend |

---

## Security notes

- No authentication by default — designed for a trusted network. Put it behind a
  reverse proxy with basic auth for exposed deployments.
- Uploads are validated by **magic bytes**, not just extension, and filenames
  are sanitized before storage.
