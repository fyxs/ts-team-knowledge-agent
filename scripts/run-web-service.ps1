# Start the local web service on port 8088 if it is not running; safe to run repeatedly.
$ErrorActionPreference = 'Continue'

# Portable: project root from this script's location; workspace from TS_KB_CONFIG,
# then a .ts-kb-workspace pointer written by install-windows-tasks.ps1.
$root = Split-Path -Parent $PSScriptRoot
$configPath = $env:TS_KB_CONFIG
$pointer = Join-Path $root '.ts-kb-workspace'
if (-not $configPath -and (Test-Path -LiteralPath $pointer)) {
    $configPath = (Get-Content -LiteralPath $pointer -TotalCount 1).Trim()
}
if (-not $configPath) { $configPath = Join-Path $root 'ts-kb.json' }
$errorLog = Join-Path $root 'logs\runner-errors.log'
if (-not (Test-Path -LiteralPath $configPath)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $errorLog) | Out-Null
    Add-Content -LiteralPath $errorLog -Value ((Get-Date -Format s) + ' config not found: ' + $configPath)
    exit 1
}
$work = Split-Path -Parent $configPath
$cli = Join-Path $root '.venv\Scripts\ts-team-kb.exe'
if (-not (Test-Path -LiteralPath $cli)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $errorLog) | Out-Null
    Add-Content -LiteralPath $errorLog -Value ((Get-Date -Format s) + ' cli not found: ' + $cli)
    exit 1
}
$logDir = Join-Path $work 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$env:TS_KB_CONFIG = $configPath
$env:PYTHONPATH = Join-Path $root 'backend'
Set-Location $root
$listening = Get-NetTCPConnection -LocalPort 8088 -State Listen -ErrorAction SilentlyContinue
if ($listening) {
    Add-Content -LiteralPath (Join-Path $logDir 'web-service.log') -Value ('already-running pid=' + ($listening | Select-Object -First 1).OwningProcess + ' ' + (Get-Date -Format s))
    exit 0
}
Add-Content -LiteralPath (Join-Path $logDir 'web-service.log') -Value ('starting ' + (Get-Date -Format s))
Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', (Join-Path $work 'run-api.cmd') -WindowStyle Hidden
exit 0
