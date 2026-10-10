# Stops the services started by scripts\dev.ps1
$Root = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $Root ".logs\pids.txt"
if (Test-Path $PidFile) {
    Get-Content $PidFile | ForEach-Object {
        if ($_ -match '^\d+$') {
            # kill the whole process tree (venv python.exe and node may have children)
            & taskkill /PID ([int]$_) /T /F 2>$null | Out-Null
            Stop-Process -Id ([int]$_) -Force -ErrorAction SilentlyContinue
        }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped."
} else {
    Write-Host "Nothing to stop (no .logs\pids.txt)."
}
