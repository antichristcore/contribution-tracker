# Поднимает публичный HTTPS-туннель до локального сервера и прописывает его
# адрес в .env. Быстрые туннели cloudflared живут недолго и умирают молча:
# сервер работает, а Mini App у всех перестаёт открываться. Поэтому здесь всё
# в одну команду, вместе с обновлением MINI_APP_URL.
#
# Использование:
#   .\scripts\start_tunnel.ps1            запустить (старый процесс снимается)
#   .\scripts\start_tunnel.ps1 -Stop      остановить
#   .\scripts\start_tunnel.ps1 -Status    показать текущий адрес

param(
    [switch]$Stop,
    [switch]$Status,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $root "logs"
$logFile = Join-Path $logDir "tunnel.log"
$envFile = Join-Path $root ".env"
$exe = "C:\Program Files (x86)\cloudflared\cloudflared.exe"

function Get-EnvUrl {
    if (-not (Test-Path $envFile)) { return $null }
    $line = Select-String -Path $envFile -Pattern '^MINI_APP_URL=(.+)$' | Select-Object -First 1
    if ($line) { return $line.Matches[0].Groups[1].Value.Trim() }
    return $null
}

if ($Status) {
    $proc = Get-Process cloudflared -ErrorAction SilentlyContinue
    if ($proc) { Write-Host "Туннель запущен (PID: $($proc.Id -join ', '))" }
    else { Write-Host "Туннель не запущен" }
    Write-Host "MINI_APP_URL: $(Get-EnvUrl)"
    exit 0
}

Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
if ($Stop) {
    Write-Host "Туннель остановлен"
    exit 0
}

if (-not (Test-Path $exe)) {
    Write-Error "Не нашёл cloudflared по пути $exe"
}
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
if (Test-Path $logFile) { Remove-Item $logFile -Force }

Write-Host "Поднимаю туннель на :$Port..."
Start-Process -FilePath $exe `
    -ArgumentList @("tunnel", "--url", "http://127.0.0.1:$Port", "--logfile", $logFile) `
    -WindowStyle Hidden

# Адрес появляется в логе не сразу: cloudflared сначала договаривается с краем сети.
$url = $null
foreach ($i in 1..40) {
    Start-Sleep -Milliseconds 500
    if (Test-Path $logFile) {
        $match = Select-String -Path $logFile -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' |
                 Select-Object -First 1
        if ($match) { $url = $match.Matches[0].Value; break }
    }
}

if (-not $url) {
    Write-Error "Туннель не отдал адрес за 20 секунд. Смотри $logFile"
}

# Перезаписываем MINI_APP_URL, не трогая остальные строки .env.
$content = Get-Content $envFile -Raw -Encoding UTF8
if ($content -match '(?m)^MINI_APP_URL=.*$') {
    $content = $content -replace '(?m)^MINI_APP_URL=.*$', "MINI_APP_URL=$url"
} else {
    $content = $content.TrimEnd() + "`nMINI_APP_URL=$url`n"
}
Set-Content -Path $envFile -Value $content -Encoding UTF8 -NoNewline

Write-Host "Адрес: $url"
Write-Host "Записан в .env. Дальше перезапусти сервер, чтобы бот обновил кнопку меню:"
Write-Host "  .\scripts\start_server.ps1 -Stop; .\scripts\start_server.ps1"
