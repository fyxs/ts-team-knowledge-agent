# 本地安装与启动

本文档说明团队成员如何在**自己机器上**安装并使用知识 Agent。本项目是本地优先的 CLI 工具，不部署到云服务。

## 前置条件

```text
Python 3.11+
Git（用于共享知识仓）
Node.js + pnpm（仅构建前端产物时需要，一次性）
MinerU 独立环境（可选；缺少时 PDF / Office 转换不可用，Markdown 仍可复制）
共享知识仓的读取权限（写入还需仓库推送权限）
```

## 安装

```bash
git clone <应用仓地址> ts-team-knowledge-agent
cd ts-team-knowledge-agent

# 后端：只装本包，不拉取 MinerU 等重依赖
.venv\Scripts\python.exe -m pip install -e . --no-deps

# 前端：构建一次静态产物（需要 Node）
cd frontend && pnpm install && pnpm build && cd ..
```

构建产物位于 `frontend/dist`，由后端直接托管，日常使用无需再启动前端进程。

## 初始化

```bash
# 生成配置、克隆共享知识仓，并按提示完成模型配置（供应商 / 请求地址 / 密钥 / 模型名）
ts-team-kb init --working-directory <工作目录> --personal-workspace <成员标识> --shared-source-directory <源目录>
```

引导会依次询问：供应商名称 → 供应商请求地址 → API Key（不回显）→ 模型名称。

## 启动

```bash
# 默认只监听本机：最安全，适合自己用
ts-team-kb serve

# 需要让同事访问时才对外开放（会提示风险）
ts-team-kb serve --host 0.0.0.0 --port 8088
```

启动前会做前置检查并逐项报告：

| 检查项 | 阻塞级别 |
| --- | --- |
| 源目录存在 | 错误（中止启动） |
| 共享知识仓是 Git 仓库 | 错误（中止启动） |
| MinerU 解释器路径有效 | 错误（中止启动） |
| 模型配置完整 | 警告（问答不可用） |
| 前端产物存在 | 警告（仅 API 可用） |

有阻塞项时会提示修正方式；确需强启可用 `--skip-preflight`。

## 同步与扫描

```bash
ts-team-kb run-once --sync        # 跑一轮：扫描 → 转换 → 门禁 → 索引 → 推送
ts-team-kb run-once --sync --if-due   # 只有距上次运行达到扫描间隔时才执行

ts-team-kb search "关键词"        # 检索
ts-team-kb read <path>            # 读取文档
ts-team-kb list                   # 列出文档
ts-team-kb status                 # 转换状态与失败清单
ts-team-kb ask "问题"             # 命令行问答（同样检索 + 引用）

ts-team-kb config show            # 查看配置（密钥仅显示末四位）
ts-team-kb config set-key         # 交互式设置密钥，不回显
```

Web 界面提供等价的运维入口：扫描间隔、立即扫描、共享知识仓拉取 / 推送。

## 定时扫描

由本地计划任务按**固定频率唤醒**，是否真正执行由配置的扫描间隔决定：

```text
配置项：scan_interval_minutes，默认 60，下限 5
未到期时 run-once --if-due 会静默跳过
```

Windows 上由计划任务调用 `scripts/` 下的运行脚本（经 wscript 隐藏启动，不弹窗、不占桌面）：

| 计划任务 | 触发 | 运行脚本 | 说明 |
| --- | --- | --- | --- |
| `TSKnowledgeAgentScheduler` | 每 5 分钟 | `run-scheduled.ps1` | 敲门；未到 `scan_interval_minutes` 则静默跳过 |
| `TSKnowledgeAgentInspection` | 每天 08:30 | `run-inspection.ps1` | 错过时唤醒补跑 |
| `TSKnowledgeAgentEvaluation` | 每周一 09:00 | `run-evaluation.ps1` | 安装时需带 `-IncludeMaintenance` |
| `TSKnowledgeAgentWebService` | 用户登录时 | `run-web-service.ps1` | 幂等守护：8088 已在监听则直接退出 |

任务由 `scripts/install-windows-tasks.ps1` 注册，可反复执行（幂等）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <项目>\scripts\install-windows-tasks.ps1 `
  -Workspace <工作目录> [-ScanEveryMinutes 5] [-InspectionDailyAt 08:30] `
  [-EvaluationWeeklyAt 09:00] [-WebPort 8088] [-IncludeMaintenance]
```

它会做三件事：写 `.ts-kb-workspace` 指针文件（让任务无需环境变量即可找到工作目录）、
在工作目录生成 `run-api.cmd` 与 `run-*-hidden.vbs` 启动器、注册（或刷新）上述计划任务。
所有任务都带 `StartWhenAvailable`（错过触发后尽快补跑），并允许电池供电时运行。

## 新机接入清单

在一台新的 Windows 机器上从零接入（按顺序执行）：

```text
1. 前置      Python 3.11+ / Git（写入共享知识仓需要仓库权限）/ Node.js + pnpm（仅构建前端产物时用）
2. 取代码    git clone <应用仓> ts-team-knowledge-agent && cd ts-team-knowledge-agent
3. 装后端    .venv\Scripts\python.exe -m pip install -e . --no-deps     （不拉 MinerU 等重依赖）
4. 建前端    cd frontend && pnpm install && pnpm build && cd ..          （产物 frontend/dist 由后端托管）
5. 初始化    ts-team-kb init --working-directory <工作目录> --personal-workspace <成员标识>
             --shared-source-directory <源目录>                          （按提示配模型：供应商 / 地址 / Key / 模型名）
6. 配 MinerU 可选：把 mineru_python 指向已装好的 MinerU 解释器（缺省时 PDF / Office 转换不可用，Markdown 仍可复制）
7. 注册任务  scripts\install-windows-tasks.ps1 -Workspace <工作目录> [-IncludeMaintenance]
8. 起服务    scripts\run-web-service.ps1                                   （或等下次登录自启）
9. 验证      浏览器打开 http://127.0.0.1:8088 能问答；ts-team-kb status 能看到源文件状态
```

第 9 步是**必须**的：任务注册成功只说明计划任务存在，不代表服务在跑、更不代表能问答。

工作目录里除了当前生效的 `run-api.cmd` 与 `run-*-hidden.vbs`，历史上可能残留 `run_serve.cmd`、
`run_webui.cmd` 之类的旧启动器；判断"哪个在生效"看计划任务的参数指向，不要凭文件名猜。

## 开机自启与运维命令

```powershell
# 查看状态（是否在监听、任务上次结果）
Get-NetTCPConnection -LocalPort 8088 -State Listen
Get-ScheduledTask -TaskName 'TSKnowledgeAgent*' | Get-ScheduledTaskInfo | Select TaskName,LastRunTime,LastTaskResult

# 停止 Web 服务（不影响计划任务）
Get-NetTCPConnection -LocalPort 8088 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }

# 重启 / 拉起（幂等：已在监听则什么都不做）
powershell -NoProfile -ExecutionPolicy Bypass -File <项目>\scripts\run-web-service.ps1
Start-ScheduledTask -TaskName 'TSKnowledgeAgentWebService'

# 临时停掉自动任务（排查时用，记得恢复）
Disable-ScheduledTask -TaskName 'TSKnowledgeAgentScheduler'
Enable-ScheduledTask  -TaskName 'TSKnowledgeAgentScheduler'
```

运行日志：工作目录 `logs/web-service.log`（自启与幂等记录）、`logs/api.log`（服务输出）、
`logs/runner-errors.log`（运行脚本自身的失败留痕）。

## 权限与安全边界

```text
能推送到共享知识仓 ≠ 任何人：推送依赖本机 Git 凭据与仓库权限
默认只监听 127.0.0.1，不产生任何网络暴露
对外开放（--host 0.0.0.0）时，界面会成为本机 Git 凭据的代理，需确认网络范围可信
API Key 存放在 <工作目录>\secrets\model.key，不在任何 Git 仓库内
```

## 常见问题

```text
启动即中止：看前置检查报告里标 [error] 的项，按提示修正
问答不可用：检查模型配置（ts-team-kb config show）
PDF 转换失败：检查 MinerU 解释器是否配置且路径有效
Web 界面打不开：确认 frontend/dist/index.html 存在（需先构建）
回答未检索知识库：界面会给出提示，说明该轮模型跳过了检索
换台机器后打不开：先按上面「新机接入清单」跑一遍，第 9 步验证不过就先看前置检查报告
服务已启动但没有反应：看 logs/web-service.log 是否有 already-running、logs/api.log 是否报端口占用
计划任务显示成功但没干活：任务返回码恒为 0（wscript 特性），要看工作目录下的业务日志判断
```
