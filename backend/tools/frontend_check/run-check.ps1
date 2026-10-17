# Starts the Harbor backend (port 8000) and the frontend check page (port 3000), then opens the page.
# Works from any folder:
#   powershell -ExecutionPolicy Bypass -File C:\Users\matth\harbor\backend\tools\frontend_check\run-check.ps1
# Each server opens in its own window; close those windows (or press Ctrl+C in them) to stop.

$backend = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$python = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "No virtual environment at $python. Set it up first (see backend\README.md)." -ForegroundColor Red
    exit 1
}

Start-Process -FilePath $python -WorkingDirectory $backend `
    -ArgumentList "-m", "uvicorn", "harbor.main:app", "--port", "8000", "--workers", "1"
Start-Process -FilePath $python -WorkingDirectory $PSScriptRoot `
    -ArgumentList "-m", "http.server", "3000", "--directory", $PSScriptRoot

Write-Host "Starting the backend and the check page..."
Start-Sleep -Seconds 5
Start-Process "http://localhost:3000/"
Write-Host "Opened http://localhost:3000/ - wait about 15 seconds for 'ALL PASSED'."
