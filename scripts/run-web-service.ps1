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
# 端口探测：Get-NetTCPConnection 在本机会长时间阻塞（实测把守护脚本卡死、任务停在 Running），
# 改用 .NET TcpClient 直接连一次，1 秒超时，快速且不依赖 CIM。
function Test-PortListening {
    param([int]$Port)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $task = $client.ConnectAsync('127.0.0.1', $Port)
        if (-not $task.Wait(1000)) { return $false }
        return $client.Connected
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}
if (Test-PortListening -Port 8088) {
    Add-Content -LiteralPath (Join-Path $logDir 'web-service.log') -Value ('already-running ' + (Get-Date -Format s))
    exit 0
}
Add-Content -LiteralPath (Join-Path $logDir 'web-service.log') -Value ('starting ' + (Get-Date -Format s))
Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', (Join-Path $work 'run-api.cmd') -WindowStyle Hidden
exit 0
