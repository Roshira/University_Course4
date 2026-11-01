# Запуск усієї системи на Windows (потрібен запущений Docker Desktop)
#   powershell -ExecutionPolicy Bypass -File .\run.ps1
Set-Location $PSScriptRoot
if (-not (Test-Path .env)) { Copy-Item .env.example .env; Write-Host "Створено .env з .env.example" }
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { Write-Host "Помилка запуску — див. повідомлення вище." -ForegroundColor Red; exit 1 }
docker compose ps
Write-Host "`nВідкрийте http://localhost:8080  (admin / admin12345)" -ForegroundColor Green
Start-Process "http://localhost:8080"
