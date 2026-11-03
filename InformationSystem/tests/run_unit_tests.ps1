# Unit-тести всіх сервісів. Python-тести запускаються в зібраних образах стека
# (потрібен docker compose build або up), C#-тести - через локальний .NET 10 SDK.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$services = Join-Path $root "services"
$failed = 0

Write-Host "== auth-server (unittest + FastAPI TestClient)"
docker run --rm -v "${services}:/src:ro" -w /src/auth-server analytics-monitoring-auth-server `
    sh -c "pip install -q --disable-pip-version-check httpx==0.28.1 && python -m unittest discover -s tests -v"
if ($LASTEXITCODE -ne 0) { $failed++ }

Write-Host "== ingest-worker (consumer.py)"
docker run --rm -v "${services}:/src:ro" -w /src/workers -e PYTHONDONTWRITEBYTECODE=1 analytics-monitoring-ingest-worker `
    python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { $failed++ }

Write-Host "== TelemetrySystem.Api.Tests (dotnet test)"
if (Get-Command dotnet -ErrorAction SilentlyContinue) {
    dotnet test (Join-Path $root "TelemetrySystem.Api.Tests")
    if ($LASTEXITCODE -ne 0) { $failed++ }
} else {
    Write-Host "dotnet SDK не знайдено - C#-тести пропущено"
}

if ($failed) { Write-Host "Не пройшло наборів тестів: $failed"; exit 1 }
Write-Host "Усі unit-тести пройдено"
