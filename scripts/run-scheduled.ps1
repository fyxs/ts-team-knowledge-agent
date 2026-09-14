$ErrorActionPreference = 'Continue'

# 单轮扫描转换：由 Windows 计划任务按固定频率调用。
# 是否真正执行由配置的扫描间隔（scan_interval_minutes）决定：--if-due 未到期时静默跳过。
$root = 'D:\2Work\Private\Projects\ts-team-knowledge-agent'
$work = 'D:\2Work\Knowledge\kb-shared-workspace'
$python = Join-Path $root '.venv\Scripts\python.exe'
$logDir = Join-Path $work 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$env:PYTHONPATH = Join-Path $root 'backend'
$env:TS_KB_CONFIG = Join-Path $work 'ts-kb.json'
Set-Location $root
$code = "from ts_knowledge_agent.cli.main import main; raise SystemExit(main(['run-once','--sync','--if-due','--batch-size','25']))"
& $python -c $code *>> (Join-Path $logDir 'scheduled-run.log')
exit $LASTEXITCODE
