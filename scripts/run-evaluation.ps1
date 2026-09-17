# Daily knowledge-base inspection; called by scheduled task TSKnowledgeAgentInspection.
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
$log = Join-Path $logDir 'evaluation-run.log'
& cmd.exe /c ('"' + $cli + '" evaluate --mode both --publish --if-due --interval-minutes 10080 >> "' + $log + '" 2>&1')
exit $LASTEXITCODE
