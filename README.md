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

## Local development (without Docker)

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
