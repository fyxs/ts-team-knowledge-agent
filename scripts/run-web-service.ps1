$ErrorActionPreference = 'Continue'

# Start the local web service (API + built frontend) on port 8088 if not already running.
# Invoked by scheduled task TSKnowledgeAgentWebService at logon; safe to run repeatedly.
$root = 'D:\2Work\Private\Projects\ts-team-knowledge-agent'
$work = 'D:\2Work\Knowledge\kb-shared-workspace'
$launcher = Join-Path $work 'run-api.cmd'
$logDir = Join-Path $work 'logs'
$log = Join-Path $logDir 'web-service.log'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$listening = Get-NetTCPConnection -LocalPort 8088 -State Listen -ErrorAction SilentlyContinue
if ($listening) {
    $pid8088 = ($listening | Select-Object -First 1).OwningProcess
    Add-Content -LiteralPath $log -Value ('already-running pid=' + $pid8088 + ' ' + (Get-Date -Format s))
    exit 0
}

Add-Content -LiteralPath $log -Value ('starting ' + (Get-Date -Format s))
Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', $launcher -WindowStyle Hidden
exit 0
