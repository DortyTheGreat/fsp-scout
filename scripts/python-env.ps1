# Shared helpers for dev.ps1 and compare-llm.ps1 (dot-sourced): find Python 3.10+, create .venv, install packages.
# ASCII only: Windows PowerShell 5.1 reads scripts without BOM in the ANSI code page.

function Step($msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }

function Fail($msg) {
    Write-Host ""
    Write-Host "ERROR: $msg" -ForegroundColor Red
    if ($Logs) { Write-Host "Logs: $Logs" -ForegroundColor Yellow }
    exit 1
}

function Find-BasePython {
    $candidates = @("py -3.13", "py -3.12", "py -3.11", "py -3.10", "py -3.14", "python", "python3", "py -3")
    foreach ($c in $candidates) {
        $parts = $c.Split(" ")
        $exe = $parts[0]
        $extra = @($parts | Select-Object -Skip 1)
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $v = & $exe @extra -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and "$v" -match '^3\.(\d+)$' -and [int]$Matches[1] -ge 10) {
            return @{ Exe = $exe; Extra = $extra; Version = "$v"; Name = $c }
        }
    }
    return $null
}

# Returns the path to .venv python. Native command output is sent to the host (Out-Host),
# otherwise PowerShell would capture it into the function's return value.
function Initialize-Venv($Root) {
    $venvDir = Join-Path $Root ".venv"
    $venvPy = Join-Path $venvDir "Scripts\python.exe"
    if (Test-Path $venvPy) {
        & $venvPy -c "import sys" 2>$null | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Write-Host "The existing .venv is broken, recreating it."
            Remove-Item -Recurse -Force $venvDir -ErrorAction SilentlyContinue
        }
    }
    if (-not (Test-Path $venvPy)) {
        Step "Looking for Python 3.10+"
        $py = Find-BasePython
        if (-not $py) {
            Fail "Python 3.10 or newer was not found. Install Python 3.12 from https://www.python.org/downloads/ (tick 'Add python.exe to PATH') or run: winget install Python.Python.3.12  - then run this script again."
        }
        Write-Host "Found Python $($py.Version) ($($py.Name))"
        Step "Creating virtual environment .venv"
        $extra = $py.Extra
        & $py.Exe @extra -m venv $venvDir | Out-Host
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPy)) { Fail "Could not create the virtual environment." }
    }
    Step "Installing Python packages (first run takes a few minutes)"
    & $venvPy -m pip install --disable-pip-version-check -q --upgrade pip | Out-Host
    & $venvPy -m pip install --disable-pip-version-check -q -r (Join-Path $Root "backend\requirements.txt") -r (Join-Path $Root "fsp-mock\requirements.txt") | Out-Host
    if ($LASTEXITCODE -ne 0) { Fail "pip install failed (see the messages above)." }
    return $venvPy
}
