$ErrorActionPreference = 'Continue'

# 单轮扫描转换：由 Windows 计划任务按间隔调用。
# 使用项目 .venv、显式配置文件和 CLI 函数入口；同一工作目录由 RunLock 保证不并发。

$root = 'D:\2Work\Private\Projects\ts-team-knowledge-agent'
$work = 'D:\2Work\Knowledge\kb-shared-workspace'
$python = Join-Path $root '.venv\Scripts\python.exe'
$config = Join-Path $work 'ts-kb.json'
$logDir = Join-Path $work 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$env:PYTHONPATH = Join-Path $root 'backend'
$env:TS_KB_CONFIG = $config
Set-Location $root

& $python -c "from ts_knowledge_agent.cli.main import main; raise SystemExit(main(['run-once','--sync','--batch-size','25']))" *>> (Join-Path $logDir 'scheduled-run.log')
exit $LASTEXITCODE
