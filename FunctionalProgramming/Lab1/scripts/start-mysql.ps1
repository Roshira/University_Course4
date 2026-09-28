# Запуск портативного MySQL 8.4 (zip-версія) та створення БД при першому запуску.
# Використання:  powershell -ExecutionPolicy Bypass -File scripts\start-mysql.ps1
param(
  [string]$MySqlHome = "$env:USERPROFILE\mysql\mysql-8.4.9-winx64",
  [string]$DataDir   = "$env:USERPROFILE\mysql\data",
  [int]$Port         = 3306
)

$ErrorActionPreference = "Continue"
$mysqld = Join-Path $MySqlHome "bin\mysqld.exe"
$mysql  = Join-Path $MySqlHome "bin\mysql.exe"
$sqlDir = Join-Path $PSScriptRoot "..\sql"

if (-not (Test-Path $mysqld)) { throw "Не знайдено $mysqld. Вкажіть -MySqlHome." }

$firstRun = -not (Test-Path $DataDir)
if ($firstRun) {
  Write-Host "Ініціалізація каталогу даних $DataDir ..."
  & $mysqld --initialize-insecure --basedir="$MySqlHome" --datadir="$DataDir" 2>$null
  if ($LASTEXITCODE -ne 0) { throw "Помилка ініціалізації MySQL" }
}

$running = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $running) {
  Write-Host "Запуск MySQL на порту $Port ..."
  Start-Process -FilePath $mysqld -WindowStyle Hidden -ArgumentList @(
    "--basedir=`"$MySqlHome`"", "--datadir=`"$DataDir`"", "--port=$Port",
    "--mysql-native-password=ON",
    "--character-set-server=utf8mb4", "--collation-server=utf8mb4_unicode_ci"
  )
  for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { break }
  }
}

$exists = & $mysql -uroot --port=$Port -N -e "SHOW DATABASES LIKE 'individual_work'"
if (-not $exists) {
  Write-Host "Створення БД individual_work та заповнення тестовими даними ..."
  Get-Content (Join-Path $sqlDir "01_schema.sql") -Raw -Encoding UTF8 | & $mysql -uroot --port=$Port --default-character-set=utf8mb4
  Get-Content (Join-Path $sqlDir "02_seed.sql")   -Raw -Encoding UTF8 | & $mysql -uroot --port=$Port --default-character-set=utf8mb4
}
Write-Host "MySQL готовий (localhost:$Port, БД individual_work, користувач lab1/lab1pass)."
