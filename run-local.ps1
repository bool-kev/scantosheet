# ============================================================================
# ScanToSheet — local launcher (no Docker)
#
# Starts the FastAPI backend (with Tesseract + Poppler wired up) and the Vite
# frontend dev server in two background jobs. Requires:
#   - Tesseract OCR installed (C:\Program Files\Tesseract-OCR)
#   - Poppler installed via winget (oschwartz10612.Poppler)
#   - backend\.venv created with dependencies installed
#   - frontend deps installed (npm install)
#
# Usage:  powershell -ExecutionPolicy Bypass -File .\run-local.ps1
#         Ctrl+C to stop, then the script tears both servers down.
# ============================================================================

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# --- Locate Poppler bin (installed under the WinGet packages folder) ---------
$popplerBin = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse `
    -Filter pdftoppm.exe -ErrorAction SilentlyContinue |
    Select-Object -First 1 -ExpandProperty DirectoryName
if (-not $popplerBin) {
    Write-Warning "Poppler (pdftoppm.exe) not found. Install it: winget install oschwartz10612.Poppler"
}

# --- Locate a tessdata dir that actually contains 'fra' -----------------------
$candidates = @(
    (Join-Path $env:LOCALAPPDATA 'scantosheet-tessdata'),
    'C:\Program Files\Tesseract-OCR\tessdata'
)
$tessdata = $candidates | Where-Object { Test-Path (Join-Path $_ 'fra.traineddata') } | Select-Object -First 1
if (-not $tessdata) {
    Write-Warning "No tessdata dir with fra.traineddata found; OCR in French will fail."
    $tessdata = $candidates[1]
}

Write-Host "Poppler bin : $popplerBin"
Write-Host "TESSDATA    : $tessdata"

# --- Backend job -------------------------------------------------------------
$backend = Start-Job -Name scantosheet-backend -ScriptBlock {
    param($root, $popplerBin, $tessdata)
    Set-Location (Join-Path $root 'backend')
    if ($popplerBin) { $env:PATH = "$popplerBin;$env:PATH" }
    $env:TESSDATA_PREFIX = $tessdata
    $env:DATA_DIR        = (Join-Path $root 'data')
    $env:CORS_ORIGINS    = 'http://localhost:5173'
    $env:TESSERACT_LANG  = 'fra'
    & .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
} -ArgumentList $root, $popplerBin, $tessdata

# --- Frontend job ------------------------------------------------------------
$frontend = Start-Job -Name scantosheet-frontend -ScriptBlock {
    param($root)
    Set-Location (Join-Path $root 'frontend')
    $env:VITE_API_URL = 'http://localhost:8000'
    & npm run dev
} -ArgumentList $root

Write-Host "`nBackend  : http://localhost:8000/api/docs"
Write-Host "Frontend : http://localhost:5173"
Write-Host "Streaming logs — press Ctrl+C to stop both.`n"

try {
    while ($true) {
        Receive-Job $backend, $frontend
        Start-Sleep -Milliseconds 800
    }
}
finally {
    Write-Host "`nStopping servers..."
    Stop-Job $backend, $frontend -ErrorAction SilentlyContinue
    Remove-Job $backend, $frontend -Force -ErrorAction SilentlyContinue
}
