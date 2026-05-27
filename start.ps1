# Run backend and frontend in separate terminals
$root = $PSScriptRoot
Write-Host "Start backend:  cd $root\backend; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
Write-Host "Start frontend: cd $root\frontend; npm run dev"
