$ErrorActionPreference = 'Continue'

# Daily knowledge-base inspection.
# Invoked by scheduled task TSKnowledgeAgentInspection (hidden, via wscript).
$root = 'D:\2Work\Private\Projects\ts-team-knowledge-agent'
$work = 'D:\2Work\Knowledge\kb-shared-workspace'
$cli = Join-Path $root '.venv\Scripts\ts-team-kb.exe'
$logDir = Join-Path $work 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$env:PYTHONPATH = Join-Path $root 'backend'
$env:TS_KB_CONFIG = Join-Path $work 'ts-kb.json'
Set-Location $root
& $cli inspect --per-type 6 *>> (Join-Path $logDir 'inspection-run.log')
exit $LASTEXITCODE
