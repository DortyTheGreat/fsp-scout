# FSP Scout - local run without Docker (Windows PowerShell 5.1+ or PowerShell 7).
# Easiest: double-click run-local.bat in the project root.
# Or:      powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev.ps1
# Needs:   Python 3.10+ and Node.js 20+. Uses SQLite, no PostgreSQL or Docker required.
# Stop:    stop-local.bat  (or scripts\stop.ps1)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Logs = Join-Path $Root ".logs"
New-Item -ItemType Directory -Force $Logs | Out-Null
$PidFile = Join-Path $Logs "pids.txt"

. (Join-Path $PSScriptRoot "python-env.ps1")   # Step, Fail, Initialize-Venv

function Wait-Http($url, $seconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -lt 500) { return $true }
        } catch { }
        Start-Sleep -Milliseconds 800
    }
    return $false
}

# venv python.exe and next start may spawn child processes: kill the whole tree
function Stop-Tree($id) {
    & taskkill /PID $id /T /F 2>$null | Out-Null
    Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
}

function Test-PortBusy($port) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $c.Connect("127.0.0.1", $port)
        $c.Close()
        return $true
    } catch { return $false }
}

# ---------------------------------------------------------------- 0. stop a previous run
if (Test-Path $PidFile) {
    Get-Content $PidFile | ForEach-Object { if ($_ -match '^\d+$') { Stop-Tree ([int]$_) } }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

# ---------------------------------------------------------------- 1. Python
$venvPy = Initialize-Venv $Root

# ---------------------------------------------------------------- 2. Node.js
Step "Looking for Node.js 20+"
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Fail "Node.js was not found. Install the LTS version from https://nodejs.org/ or run: winget install OpenJS.NodeJS.LTS  - then open a NEW terminal and run this script again."
}
$nodeV = (& node --version) -replace '^v', ''
if ([int]($nodeV.Split('.')[0]) -lt 20) { Fail "Node.js $nodeV is too old, version 20 or newer is required." }
Write-Host "Found Node.js $nodeV"

Set-Location (Join-Path $Root "frontend")
if (-not (Test-Path "node_modules\next")) {
    Step "Installing frontend packages (npm ci)"
    & npm ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { Fail "npm ci failed (see the messages above)." }
}
Step "Building the frontend"
# 127.0.0.1, not localhost: Node.js may resolve localhost to IPv6 (::1), while the API listens on IPv4
$env:BACKEND_URL = "http://127.0.0.1:8000"
$env:NEXT_TELEMETRY_DISABLED = "1"
& npm run build
if ($LASTEXITCODE -ne 0) { Fail "Frontend build failed (see the messages above)." }
Set-Location $Root

# ---------------------------------------------------------------- 3. ports
foreach ($port in 3000, 8000, 8001) {
    if (Test-PortBusy $port) { Fail "Port $port is already in use. Close the program that uses it (or run stop-local.bat) and try again." }
}

# ---------------------------------------------------------------- 4. services
$dbPath = (Join-Path $Root "backend\scout.db") -replace '\\', '/'
$env:DATABASE_URL = "sqlite:///$dbPath"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:FSP_INTERNAL_URL = "http://127.0.0.1:8001"
$pids = @()

Step "Starting FSP mock (FSP ID + achievements registry) on :8001"
$p = Start-Process -FilePath $venvPy -ArgumentList "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8001" `
    -WorkingDirectory (Join-Path $Root "fsp-mock") -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $Logs "fsp.out.log") -RedirectStandardError (Join-Path $Logs "fsp.log")
$pids += $p.Id
Set-Content $PidFile $pids
if (-not (Wait-Http "http://127.0.0.1:8001/health" 60)) { Fail "FSP mock did not start, see .logs\fsp.log" }

if (-not (Test-Path (Join-Path $Root "backend\scout.db"))) {
    Step "Generating demo data: 300 synthetic candidates take the real adaptive test (1-3 minutes)"
    Set-Location (Join-Path $Root "backend")
    & $venvPy -m app.seed --candidates 300
    $seedCode = $LASTEXITCODE
    Set-Location $Root
    if ($seedCode -ne 0) {
        Remove-Item (Join-Path $Root "backend\scout.db") -Force -ErrorAction SilentlyContinue
        Fail "Demo data generation failed (see the messages above)."
    }
}

Step "Starting API on :8000"
$p = Start-Process -FilePath $venvPy -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
    -WorkingDirectory (Join-Path $Root "backend") -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $Logs "api.out.log") -RedirectStandardError (Join-Path $Logs "api.log")
$pids += $p.Id
Set-Content $PidFile $pids
if (-not (Wait-Http "http://127.0.0.1:8000/api/v1/health" 90)) { Fail "API did not start, see .logs\api.log" }

Step "Starting web app on :3000"
$p = Start-Process -FilePath "node" -ArgumentList "node_modules\next\dist\bin\next", "start", "-p", "3000" `
    -WorkingDirectory (Join-Path $Root "frontend") -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $Logs "web.log") -RedirectStandardError (Join-Path $Logs "web.err.log")
$pids += $p.Id
Set-Content $PidFile $pids
if (-not (Wait-Http "http://127.0.0.1:3000/login" 90)) { Fail "Web app did not start, see .logs\web.log" }

Write-Host ""
Write-Host "Ready: http://localhost:3000" -ForegroundColor Green
Write-Host "API docs (Swagger): http://localhost:3000/api/docs"
Write-Host "Demo accounts (password demo12345): candidate@demo.ru, senior@demo.ru, employer@demo.ru, admin@demo.ru"
Write-Host "FSP ID login in the mock: FSP-000777 (prize winner) or FSP-000778 (no history), password demo"
Write-Host "Stop everything: stop-local.bat"
Start-Process "http://localhost:3000"
