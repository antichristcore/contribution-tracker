# Запасной вариант для защиты: показать приложение полностью локально,
# без интернета вообще — ни Cloudflare-туннеля, ни Telegram, ни GitHub.
#
# Запуск:  .\scripts\demo_local.ps1
#
# Поднимает второй сервер на 127.0.0.1:8001 с пустым BOT_TOKEN. Пустой токен
# включает локальный вход по "?as=<member_id>" (см. backend/app/deps.py) —
# поэтому сервер слушает ТОЛЬКО localhost и наружу не смотрит. Основной сервер
# на :8000 с ботом при этом можно не трогать, они работают параллельно.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "Не найден $python — сначала создай venv и поставь зависимости."
}

if (-not (Test-Path (Join-Path $root "frontend\dist\index.html"))) {
    Write-Error "Нет собранного фронтенда. Сделай: cd frontend; npm run build"
}

Write-Host ""
Write-Host "Локальное демо (без интернета). Открывай в браузере:" -ForegroundColor Green
Write-Host ""
Write-Host "  Тимлид демо-команды : http://localhost:8001/?as=1"
Write-Host "  Участница (Olga)    : http://localhost:8001/?as=26"
Write-Host ""
Write-Host "Список участников и их id:  python scripts\list_demo_members.py" -ForegroundColor DarkGray
Write-Host "Остановить: Ctrl+C" -ForegroundColor DarkGray
Write-Host ""

$env:BOT_TOKEN = ""
Push-Location $root
try {
    & $python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001
} finally {
    Pop-Location
}
