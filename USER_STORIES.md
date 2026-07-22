# ScanToSheet — User Stories

## Overview

**ScanToSheet** is a self-hosted web application that converts scanned multi-page PDF documents into structured Excel spreadsheets using OCR.

---

## Epic 1 — PDF Upload & Management

### US-1.1 — Upload a PDF
**As a** user,
**I want to** upload a scanned PDF file via a web interface,
**So that** I can extract its content without installing any software locally.

**Acceptance Criteria:**
- Drag-and-drop or file picker upload
- Accepts `.pdf` files only, max 50 MB
- Shows upload progress bar
- Validates the file before processing (not corrupted, at least 1 page)

### US-1.2 — View Upload History
**As a** user,
**I want to** see a list of my past uploads with their processing status,
**So that** I can track and re-download previous extractions.

**Acceptance Criteria:**
- Table showing: filename, page count, status (queued / processing / done / error), date, download link
- Sortable by date
- Ability to delete an entry

---

## Epic 2 — OCR Processing

### US-2.1 — Automatic OCR on Upload
**As a** user,
**I want** the system to automatically run OCR on every page of my PDF after upload,
**So that** I don't have to trigger processing manually.

**Acceptance Criteria:**
- Each page is converted to an image then processed by Tesseract
- Processing runs asynchronously (non-blocking)
- Status updates in real-time (or near real-time via polling)

### US-2.2 — Language Selection
**As a** user,
**I want to** select the document language before uploading,
**So that** OCR accuracy is maximized for my document.

**Acceptance Criteria:**
- Dropdown with at least: French, English, Arabic, combined French+English
- Default: French
- Language packs are bundled in the Docker image

### US-2.3 — Image Preprocessing
**As a** user,
**I want** the system to automatically enhance scanned images before OCR,
**So that** I get better extraction results from low-quality scans.

**Acceptance Criteria:**
- Auto-deskew (straighten tilted scans)
- Binarization (convert to black & white)
- Noise removal
- Configurable: user can toggle preprocessing on/off

---

## Epic 3 — Data Structuring & Table Detection

### US-3.1 — Detect Tables in Scanned Pages
**As a** user,
**I want** the system to detect tabular structures in scanned pages,
**So that** extracted data preserves its row/column layout in Excel.

**Acceptance Criteria:**
- Detects bordered and borderless tables
- Maps cells to correct row/column positions
- Falls back to line-by-line text if no table is detected

### US-3.2 — Preview Extracted Data
**As a** user,
**I want to** preview the extracted data in a table view before downloading,
**So that** I can verify accuracy and catch errors.

**Acceptance Criteria:**
- Shows extracted data page by page in an HTML table
- Highlights low-confidence cells (OCR confidence < 70%)
- User can manually edit cells before export

### US-3.3 — Manual Column Mapping
**As a** user,
**I want to** define or adjust column headers for the extracted table,
**So that** my Excel output has meaningful headers.

**Acceptance Criteria:**
- Auto-suggest headers from first detected row
- User can rename, reorder, add, or remove columns
- Mapping is saved per document

---

## Epic 4 — Excel Export

### US-4.1 — Download as Excel
**As a** user,
**I want to** download the extracted data as an `.xlsx` file,
**So that** I can use it in Excel, Google Sheets, or any spreadsheet tool.

**Acceptance Criteria:**
- One sheet per PDF page, or all pages merged into one sheet (user choice)
- Proper column widths auto-sized
- File named `{original_filename}_extracted.xlsx`

### US-4.2 — Download as CSV
**As a** user,
**I want to** optionally download data as CSV,
**So that** I can import it into databases or other tools.

**Acceptance Criteria:**
- UTF-8 encoding with BOM for Excel compatibility
- Delimiter: comma (configurable to semicolon)

---

## Epic 5 — Self-Hosting & Deployment

### US-5.1 — One-Command Deployment
**As a** sysadmin,
**I want to** deploy the entire stack with a single `docker compose up` command,
**So that** setup is fast and reproducible.

**Acceptance Criteria:**
- `docker-compose.yml` with all services (API, frontend, worker, Redis)
- `.env.example` with all configurable variables
- Works on Linux x86_64 and ARM64

### US-5.2 — Persistent Storage
**As a** sysadmin,
**I want** uploaded files and results to persist across container restarts,
**So that** data is not lost on redeployment.

**Acceptance Criteria:**
- Volumes for: uploads, processed results, SQLite database
- Configurable storage path via env variable

### US-5.3 — Resource Limits
**As a** sysadmin,
**I want to** configure max concurrent OCR jobs and memory limits,
**So that** the server remains stable under load.

**Acceptance Criteria:**
- `MAX_WORKERS` env variable (default: 2)
- `MAX_FILE_SIZE_MB` env variable (default: 50)
- Queue system prevents overload

---

## Epic 6 — API Access

### US-6.1 — REST API for Programmatic Access
**As a** developer,
**I want** a REST API to upload PDFs and retrieve results,
**So that** I can integrate OCR into my own workflows.

**Acceptance Criteria:**
- `POST /api/documents` — upload PDF
- `GET /api/documents/{id}` — get status + results
- `GET /api/documents/{id}/download` — download Excel
- `DELETE /api/documents/{id}` — remove document
- OpenAPI/Swagger docs at `/api/docs`

---

## Non-Functional Requirements

| Requirement | Target |
|---|---|
| OCR processing speed | < 5s per page (A4, 300 DPI) |
| Max concurrent uploads | 5 |
| Supported PDF size | Up to 50 MB / 100 pages |
| Browser support | Chrome, Firefox, Safari (latest 2 versions) |
| Availability | Self-hosted, no external API calls |
| Data privacy | All processing local, no data leaves the server |
