# CLAUDE.md — ScanToSheet

## Project Identity

**ScanToSheet** — Self-hosted OCR web app that converts scanned multi-page PDFs into structured Excel spreadsheets.

## Architecture

```
scantosheet/
├── backend/          # Python FastAPI application
│   ├── app/
│   │   ├── main.py           # FastAPI entrypoint
│   │   ├── config.py         # Settings via pydantic-settings
│   │   ├── models.py         # SQLAlchemy/SQLite models
│   │   ├── schemas.py        # Pydantic request/response schemas
│   │   ├── routers/
│   │   │   └── documents.py  # /api/documents endpoints
│   │   ├── services/
│   │   │   ├── ocr.py        # Tesseract OCR wrapper
│   │   │   ├── pdf.py        # PDF-to-image conversion
│   │   │   ├── preprocess.py # Image enhancement pipeline
│   │   │   ├── table.py      # Table detection & structuring
│   │   │   └── excel.py      # Excel/CSV export
│   │   └── worker.py         # Background task processing
│   ├── requirements.txt
│   ├── Dockerfile
│   └── tests/
├── frontend/         # React (Vite + TypeScript)
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── api/
│   │   └── App.tsx
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
├── USER_STORIES.md
└── README.md
```

## Tech Stack

### Backend
- **Python 3.12+**
- **FastAPI** — async REST API framework
- **Tesseract OCR 5** — OCR engine (via `pytesseract`)
- **pdf2image** — PDF page to image conversion (uses Poppler)
- **Pillow** — image preprocessing (deskew, binarize, denoise)
- **OpenCV (cv2)** — advanced image preprocessing & table line detection
- **openpyxl** — Excel `.xlsx` generation
- **SQLAlchemy + SQLite** — lightweight persistence (no external DB needed)
- **python-multipart** — file upload handling
- **uvicorn** — ASGI server

### Frontend
- **React 18** with **TypeScript**
- **Vite** — build tool
- **TanStack Query** — data fetching & cache
- **Tailwind CSS** — styling
- **shadcn/ui** — UI components
- **react-dropzone** — file upload UX

### Infrastructure
- **Docker + Docker Compose** — single-command deployment
- **Redis (optional)** — job queue for heavy workloads (can start with FastAPI BackgroundTasks)
- No external API calls. Everything runs locally.

## Coding Conventions

### Python (Backend)
- Use `async def` for all route handlers
- Type hints on every function signature
- Pydantic models for all request/response schemas
- Use `pathlib.Path` instead of `os.path`
- Docstrings: Google style
- Logging: `structlog` with JSON output
- Error handling: raise `HTTPException` with meaningful detail messages
- Config: all settings via env variables loaded through `pydantic-settings`

### TypeScript (Frontend)
- Functional components only, no classes
- Custom hooks for business logic (`useDocuments`, `useUpload`, `useOcrPreview`)
- API calls centralized in `src/api/client.ts`
- Avoid `any` — type everything
- File naming: `kebab-case` for files, `PascalCase` for components
- Use `const` by default

### General
- No hardcoded strings for config — everything via `.env`
- Every API endpoint must have OpenAPI docstring
- Commit messages: conventional commits (`feat:`, `fix:`, `chore:`)
- Keep files under 300 lines — split if larger

## Key Design Decisions

1. **SQLite over Postgres** — single-file DB, zero config, perfect for self-hosted. Sufficient for single-user/small-team use.
2. **Tesseract over cloud OCR** — fully offline, no API keys, no data leakage. Trade-off: slightly lower accuracy on complex layouts, mitigated by preprocessing.
3. **BackgroundTasks first, Redis later** — start simple with FastAPI's built-in BackgroundTasks. Migrate to Celery+Redis only if concurrent processing becomes a bottleneck.
4. **Table detection via OpenCV** — detect horizontal/vertical lines to reconstruct table grid. Fallback: treat each text line as a row, split by whitespace/tabs for columns.
5. **One Docker Compose file** — frontend served by nginx in prod, API behind uvicorn. Both in the same compose file.

## API Endpoints

```
POST   /api/documents              Upload PDF + options (language, preprocessing)
GET    /api/documents              List all documents with status
GET    /api/documents/{id}         Get document details + extracted data
GET    /api/documents/{id}/download Download Excel file
GET    /api/documents/{id}/preview  Get page-by-page preview data
PUT    /api/documents/{id}/data    Update/correct extracted cell data
DELETE /api/documents/{id}         Delete document and associated files
GET    /api/health                 Health check
```

## File Storage Layout

```
/data/
├── uploads/        # Original PDF files
├── pages/          # Individual page images (PNG)
├── processed/      # Preprocessed images
├── results/        # Generated Excel/CSV files
└── scantosheet.db  # SQLite database
```

## Environment Variables

```bash
# Server
HOST=0.0.0.0
PORT=8000
CORS_ORIGINS=http://localhost:5173

# Storage
DATA_DIR=/data
MAX_FILE_SIZE_MB=50

# OCR
TESSERACT_LANG=fra
OCR_DPI=300
MAX_WORKERS=2
ENABLE_PREPROCESSING=true

# Frontend (build-time)
VITE_API_URL=http://localhost:8000
```

## Testing Strategy

- **Backend unit tests**: pytest, test each service in isolation (OCR, preprocessing, table detection, Excel export)
- **API integration tests**: httpx AsyncClient against FastAPI test client
- **Frontend**: Vitest + React Testing Library for component tests
- Test fixtures: include 2-3 sample scanned PDFs (1 table, 1 text-only, 1 mixed)

## Performance Targets

- OCR: < 5 seconds per A4 page at 300 DPI
- Upload to ready: < 30 seconds for a 10-page PDF
- Excel generation: < 2 seconds
- Frontend: First Contentful Paint < 1.5 seconds

## Security Notes

- Authentication is **on by default** (`AUTH_ENABLED=true`): every `/api/documents` call requires a valid `X-API-Key` header, so a guest on the network cannot create or read data. `/api/admin` (key management) is always authenticated regardless of this flag.
- The frontend never shows a login screen: it authenticates with a `user`-role key baked into the bundle at build time (`VITE_API_KEY`, generated in advance via `/api/admin/keys` and stored in `.env`). An operator can still override it per-browser via the admin page's key field (stored in `localStorage`).
- Non-admin keys are scoped to their own documents — cross-tenant access to another key's document returns 404 (not 403), so existence can't be probed. Admin keys see everything.
- File type validation: check magic bytes, not just extension
- Sanitize filenames on upload
- Rate limit uploads: 5 per minute
- Set `AUTH_ENABLED=false` only on a fully trusted, isolated network
