# ============================================================================
# ScanToSheet — local launcher (no Docker)
#
# Starts the FastAPI backend (with Tesseract + Poppler wired up) and the Vite
# frontend dev server as child processes of this console. Requires:
#   - Tesseract OCR installed (C:\Program Files\Tesseract-OCR)
#   - Poppler installed via winget (oschwartz10612.Poppler)
#   - backend\.venv created with dependencies installed
#   - frontend deps installed (npm install)
#
# Usage:  powershell -ExecutionPolicy Bypass -File .\run-local.ps1
#         Ctrl+C to stop, then the script tears both servers down.
#
# NOTE: uvicorn and Vite write their normal logs to stderr. We deliberately do
# NOT use Start-Job + Receive-Job here: that turns those lines into PowerShell
# error records, which (under $ErrorActionPreference='Stop') killed the loop and
# shut both servers down immediately after launch.
# ============================================================================

$root = $PSScriptRoot
$backendDir = Join-Path $root 'backend'
$frontendDir = Join-Path $root 'frontend'
$python = Join-Path $backendDir '.venv\Scripts\python.exe'

# --- Preflight ---------------------------------------------------------------
if (-not (Test-Path $python)) {
    Write-Error "Backend venv not found at $python. Create it first (see README)."
    exit 1
}
if (-not (Test-Path (Join-Path $frontendDir 'node_modules'))) {
    Write-Error "Frontend deps missing. Run 'npm install' in .\frontend first."
    exit 1
}

foreach ($port in 8000, 5173) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        Write-Error "Port $port is already in use. Stop the process using it, then retry."
        exit 1
    }
}

# --- Locate Poppler bin (installed under the WinGet packages folder) ---------
$popplerBin = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse `
    -Filter pdftoppm.exe -ErrorAction SilentlyContinue |
    Select-Object -First 1 -ExpandProperty DirectoryName
if (-not $popplerBin) {
    Write-Warning "Poppler (pdftoppm.exe) not found. Install it: winget install oschwartz10612.Poppler"
} else {
    $env:PATH = "$popplerBin;$env:PATH"
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

# Child processes inherit these environment variables.
$env:TESSDATA_PREFIX = $tessdata
$env:DATA_DIR        = Join-Path $root 'data'
$env:CORS_ORIGINS    = 'http://localhost:5173'
$env:TESSERACT_LANG  = 'fra'
$env:VITE_API_URL    = 'http://localhost:8000'

Write-Host "Poppler bin : $popplerBin"
Write-Host "TESSDATA    : $tessdata"
Write-Host "DATA_DIR    : $env:DATA_DIR"

# --- Launch both servers as children of this console -------------------------
$procs = @()
$procs += Start-Process -FilePath $python `
    -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000', '--reload' `
    -WorkingDirectory $backendDir -NoNewWindow -PassThru
$procs += Start-Process -FilePath 'npm.cmd' `
    -ArgumentList 'run', 'dev' `
    -WorkingDirectory $frontendDir -NoNewWindow -PassThru

Write-Host "`nBackend  : http://localhost:8000/api/docs"
Write-Host "Frontend : http://localhost:5173"
Write-Host "Press Ctrl+C to stop both.`n"

try {
    while ($true) {
        $dead = $procs | Where-Object { $_.HasExited }
        if ($dead) {
            Write-Warning "A server exited (PID $($dead[0].Id), code $($dead[0].ExitCode)). Shutting down."
            break
        }
        Start-Sleep -Seconds 1
    }
}
finally {
    Write-Host "`nStopping servers..."
    foreach ($p in $procs) {
        if (-not $p.HasExited) {
            # /T kills the whole tree (npm.cmd spawns node as a child).
            & taskkill.exe /PID $p.Id /T /F 2>&1 | Out-Null
        }
    }
}
