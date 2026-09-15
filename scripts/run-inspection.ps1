$ErrorActionPreference = 'Continue'

# Daily knowledge-base inspection (hidden launcher: run-inspection-hidden.vbs).
# --if-due: skip when the last inspection is within the configured interval,
# so a machine that was asleep at the scheduled time still runs once after waking.
$root = 'D:\2Work\Private\Projects\ts-team-knowledge-agent'
$work = 'D:\2Work\Knowledge\kb-shared-workspace'
$cli = Join-Path $root '.venv\Scripts\ts-team-kb.exe'
$logDir = Join-Path $work 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$env:PYTHONPATH = Join-Path $root 'backend'
$env:TS_KB_CONFIG = Join-Path $work 'ts-kb.json'
Set-Location $root
& $cli inspect --per-type 6 --if-due *>> (Join-Path $logDir 'inspection-run.log')
exit $LASTEXITCODE
