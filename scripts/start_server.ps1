# Поднимает основной сервер (API + фронт + Telegram-бот) на :8000 отдельным
# процессом, который живёт сам по себе и не умирает вместе с терминалом.
#
#   .\scripts\start_server.ps1          — запустить
#   .\scripts\start_server.ps1 -Stop    — остановить
#   .\scripts\start_server.ps1 -Status  — проверить, жив ли
#
# Логи: logs\server.log

param(
    [switch]$Stop,
    [switch]$Status
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$logDir = Join-Path $root "logs"
$log = Join-Path $logDir "server.log"

function Get-ServerProcesses {
    Get-CimInstance Win32_Process -Filter "Name like '%python%'" |
        Where-Object { $_.CommandLine -like "*uvicorn*backend.app.main*--port 8000*" }
}

function Test-Health {
    try {
        $r = Invoke-WebRequest "http://localhost:8000/api/health" -UseBasicParsing -TimeoutSec 4
        return $r.StatusCode -eq 200
    } catch {
        return $false
    }
}

if ($Status) {
    $procs = Get-ServerProcesses
    if ($procs -and (Test-Health)) {
        Write-Host "Сервер работает (PID: $($procs.ProcessId -join ', '))" -ForegroundColor Green
    } elseif ($procs) {
        Write-Host "Процесс есть, но /api/health не отвечает — смотри $log" -ForegroundColor Yellow
    } else {
        Write-Host "Сервер не запущен" -ForegroundColor Red
    }
    return
}

if ($Stop) {
    $procs = Get-ServerProcesses
    if (-not $procs) { Write-Host "Сервер и так не запущен"; return }
    $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    Write-Host "Остановлен" -ForegroundColor Green
    return
}

if (Get-ServerProcesses) {
    Write-Host "Сервер уже запущен. Сначала: .\scripts\start_server.ps1 -Stop" -ForegroundColor Yellow
    return
}

if (-not (Test-Path $python)) { Write-Error "Не найден $python" }
if (-not (Test-Path (Join-Path $root "frontend\dist\index.html"))) {
    Write-Error "Нет собранного фронтенда. Сделай: cd frontend; npm run build"
}
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

# -WindowStyle Hidden + отдельный процесс: сервер переживает закрытие терминала.
Start-Process -FilePath $python `
    -ArgumentList "-m", "uvicorn", "backend.app.main:app", "--port", "8000" `
    -WorkingDirectory $root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $log `
    -RedirectStandardError (Join-Path $logDir "server.err.log")

Write-Host "Запускаю..." -NoNewline
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 500
    if (Test-Health) {
        $procs = Get-ServerProcesses
        Write-Host " готово (PID: $($procs.ProcessId -join ', '))" -ForegroundColor Green
        Write-Host "Логи: $log" -ForegroundColor DarkGray
        return
    }
    Write-Host "." -NoNewline
}
Write-Host ""
Write-Error "Сервер не поднялся за 10 секунд. Смотри $log и $logDir\server.err.log"
