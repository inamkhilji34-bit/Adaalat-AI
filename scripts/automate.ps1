$ErrorActionPreference = "Continue"

Write-Host "Waiting for any running pip installations to finish..."
while ($true) {
    $pip_processes = Get-Process -Name "pip" -ErrorAction SilentlyContinue
    if (-not $pip_processes) {
        break
    }
    Write-Host "Pip is still running, waiting 30 seconds..."
    Start-Sleep -Seconds 30
}

Write-Host "Pip installations finished. Building knowledge index..."
python scripts\build_index.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "Index build failed. Exiting."
    exit 1
}

Write-Host "Index built successfully. Starting FastAPI server..."
uvicorn main:app --reload --port 8000
