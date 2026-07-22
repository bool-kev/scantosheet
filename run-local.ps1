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

# --- .env loading -------------------------------------------------------------

function Get-Env([string]$Name) {
    [Environment]::GetEnvironmentVariable($Name, 'Process')
}

function Set-Env([string]$Name, [string]$Value) {
    [Environment]::SetEnvironmentVariable($Name, $Value, 'Process')
}

function Set-DefaultEnv([string]$Name, [string]$Value) {
    if ([string]::IsNullOrWhiteSpace((Get-Env $Name))) { Set-Env $Name $Value }
}

function Import-DotEnv([string]$Path) {
    <#
        Parse a KEY=VALUE .env file into the process environment.
        Blank lines and #-comments are skipped. Surrounding quotes are stripped.
        Inline comments are NOT stripped, so a value may legitimately contain '#'.
    #>
    $names = @()
    if (-not (Test-Path $Path)) { return $names }
    foreach ($line in Get-Content $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }
        $split = $trimmed.IndexOf('=')
        if ($split -lt 1) { continue }
        $name = $trimmed.Substring(0, $split).Trim()
        $value = $trimmed.Substring($split + 1).Trim()
        if ($value.Length -ge 2) {
            $first = $value[0]; $last = $value[$value.Length - 1]
            if (($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'")) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }
        if ($name -match '^[A-Za-z_][A-Za-z0-9_]*$') {
            Set-Env $name $value
            $names += $name
        }
    }
    return $names
}

$envFile = Join-Path $root '.env'
$loaded = Import-DotEnv $envFile
if ($loaded.Count -gt 0) {
    # Names only — never echo values, ADMIN_API_KEY is a secret.
    Write-Host ".env loaded  : $($loaded -join ', ')"
} else {
    Write-Host ".env         : not found, using built-in defaults"
}

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

# Child processes inherit these. Values already provided by .env win, except
# where they cannot possibly work on this host (see DATA_DIR below).
Set-DefaultEnv 'TESSDATA_PREFIX' $tessdata
Set-DefaultEnv 'CORS_ORIGINS'    'http://localhost:5173'
Set-DefaultEnv 'TESSERACT_LANG'  'fra'
Set-DefaultEnv 'VITE_API_URL'    'http://localhost:8000'

# .env ships DATA_DIR=/data for the Docker image. That POSIX path is meaningless
# here, so anything that is not a Windows path falls back to .\data.
$dataDir = Get-Env 'DATA_DIR'
if ([string]::IsNullOrWhiteSpace($dataDir) -or $dataDir -notmatch '^([A-Za-z]:|\.)') {
    if (-not [string]::IsNullOrWhiteSpace($dataDir)) {
        Write-Warning "DATA_DIR='$dataDir' is a container path; using the local .\data folder instead."
    }
    Set-Env 'DATA_DIR' (Join-Path $root 'data')
}

Write-Host "Poppler bin  : $popplerBin"
Write-Host "TESSDATA     : $(Get-Env 'TESSDATA_PREFIX')"
Write-Host "DATA_DIR     : $(Get-Env 'DATA_DIR')"
Write-Host "AUTH_ENABLED : $(Get-Env 'AUTH_ENABLED')  (imports need a key when true)"

if ([string]::IsNullOrWhiteSpace((Get-Env 'ADMIN_API_KEY'))) {
    Write-Warning "ADMIN_API_KEY is empty - /api/admin will answer 503 and you cannot manage keys."
} else {
    Write-Host "ADMIN_API_KEY: configured"
}

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
