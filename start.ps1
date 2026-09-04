# Backend ve frontend'i iki ayrı pencerede başlatır.
$root = $PSScriptRoot
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\backend'; .\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\frontend'; npm run dev"
Start-Sleep -Seconds 3
Start-Process "http://127.0.0.1:5173"
