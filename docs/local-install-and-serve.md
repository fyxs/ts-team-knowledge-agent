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
| `TSKnowledgeAgentWebService` | 用户登录时 | `run-web-service-hidden.vbs` | 幂等守护：8088 已在监听则直接退出 |

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
8. 起服务    scripts\run-web-service-hidden.vbs                                   （或等下次登录自启）
9. 验证      浏览器打开 http://127.0.0.1:8088 能问答；ts-team-kb status 能看到源文件状态
```

第 9 步是**必须**的：任务注册成功只说明计划任务存在，不代表服务在跑、更不代表能问答。

工作目录里的启动器分三类：**生效的**是计划任务指向的 `run-api.cmd` 与 `run-*-hidden.vbs`（由安装脚本生成）；**手工可用的**是 `run-api-hidden.vbs`（隐藏启动 Web 服务）、`run_serve.cmd`（前台直接跑 `serve`，8088 端口，便于看报错）、`run_webui.cmd`（前端开发热更新，需要 Node）；名字相近的历史遗留文件已清理。判断"哪个在生效"看计划任务的参数指向，不要凭文件名猜。

## 开机自启与运维命令

```powershell
# 查看状态（是否在监听、任务上次结果）
Get-NetTCPConnection -LocalPort 8088 -State Listen
Get-ScheduledTask -TaskName 'TSKnowledgeAgent*' | Get-ScheduledTaskInfo | Select TaskName,LastRunTime,LastTaskResult

# 停止 Web 服务（不影响计划任务）
Get-NetTCPConnection -LocalPort 8088 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }

# 重启 / 拉起（幂等：已在监听则什么都不做）
（服务启动：运行工作目录下的 run-web-service-hidden.vbs，它内部隐藏调用 run-api.cmd；也可直接运行 run-api.cmd）
Start-ScheduledTask -TaskName 'TSKnowledgeAgentWebService'

# 临时停掉自动任务（排查时用，记得恢复）
Disable-ScheduledTask -TaskName 'TSKnowledgeAgentScheduler'
Enable-ScheduledTask  -TaskName 'TSKnowledgeAgentScheduler'
```

运行日志：工作目录 `logs/web-service.log`（自启与幂等记录）、`logs/api.log`（服务输出）、
`logs/runner-errors.log`（运行脚本自身的失败留痕）。

## 免安装包（exe）安装

面向不想装 Python / Node 的成员机。

```text
1. 下载   应用仓 Release 里的 ts-team-kb-<版本>-win-x64.zip（私有仓，需登录 GitHub）
2. 解压   到任意目录，例如 D:\2Work\ts-team-kb（免安装，删除即卸载）
3. 初始化 ts-team-kb\ts-team-kb.exe init --working-directory <工作目录> ^
             --personal-workspace <成员标识> --shared-source-directory <源目录>
4. 注册   ts-team-kb\ts-team-kb.exe service install
5. 启动   登录后由计划任务自动拉起；也可手动 ts-team-kb.exe serve --host 0.0.0.0 --port 8088
```

**包内含什么**：Python 运行时 + 应用 + 前端产物（357 KB）+ `tools/uv.exe`（41.5 MB）——因此**不需要预装 Python、Node 或 uv**；缺 Python 时 uv 会自己准备。免安装包合计约 72 MB，zip 约 34 MB。

**包内不含什么**：MinerU 及其重依赖（torch / transformers，约 1.1 GB）。原因：转换走独立解释器进程，
打包进 exe 既不可行也不稳定。因此 exe 模式下 PDF / DOCX / PPTX 转换需要额外制备 MinerU 环境：

```text
一步制备：ts-team-kb\ts-team-kb.exe setup-mineru
    · 建专用环境（默认 %LOCALAPPDATA%\ts-team-kb\mineru-env，可用 --path 指定）
    · 安装 MinerU[pipeline]（含 torch，约 1.1 GB）
    · 自检（导入 mineru 与 torch 并回报版本）
    · 把解释器路径写进 ts-kb.json 的 mineru_python

可选：--python <已有解释器> 复用现成环境（不新建、不下载）；
      --dry-run 只打印将执行的步骤；--no-verify 跳过自检。
引导解释器的选择顺序：显式 --python → 系统解释器（py -3 / python）→ **包内自带的 uv**（tools/uv.exe）
→ PATH 上的 uv。因此目标机器上**什么都不用预装**：包内已含 uv，缺少 Python 时由 uv 自动准备。
（实测：清空 PATH 后仍能自动选中包内 uv 并给出正确的建环境与安装命令。）
```

> 注：exe 与 pipx 两条路线的差异仅在此处——exe 拿不到进程外的大依赖，pip 装则天然带全。


**验收记录（2026-09-15，干净目录演练，只用 release zip）**

```text
解压         99 个文件，含 ts-team-kb.exe
setup-mineru 复用已备环境；深自检通过：torch 2.14.0+cpu pipeline-ok
真实转换     PDF 40,343B → Markdown 16,175B / 6,410 字符，正文含中文标题与内容，另抽出 2 张图
界面         首页 200（777 字符，来自包内前端产物）· /health 200
关键点       全程不碰源码目录；在 C:\tmp 下完成
```

已知依赖缺口（已由 setup-mineru 自动补齐）：MinerU 3.4.5 的 OCR 链路 `import six`，
但它没有把 six 声明为依赖；不补会在第一次真实转换时才崩。因此：

```text
· setup-mineru 安装时会一并装上 six（见 EXTRA_REQUIREMENTS，可扩展）
· 自检不只看 import mineru / torch，还会导入 mineru.backend.pipeline.pipeline_analyze
  这条真实转换链路 —— 只做浅自检会漏掉这类未声明依赖
```

## 工作目录结构

`ts-team-kb init` 会初始化工作目录，并在其中生成一份 `README.md` 自解释。结构如下：

```text
ts-kb.json          本机运行配置（源目录、工作区、模型、扫描间隔）
data/               本机 SQLite（会话历史等）
logs/               运行日志、巡检与评测报告、使用埋点明细
runtime/            运行期锁与临时状态（run.lock，正常结束后消失）
feedback/           本机反馈闭环记录（导出到共享仓 registries/）
secrets/            本机密钥（model.key），不进任何 Git 仓库
knowledge-base/     共享知识仓的本地克隆（唯一有版本控制的目录）
run-*.cmd / *.vbs   启动器（由 scripts/install-windows-tasks.ps1 生成）
```

工作目录由所有并发工作区（含 worktree）共享，不要在 worktree 内另建一套。

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

## 构建与发布（维护者）

构建依赖装在**项目自己的 `.venv`** 里，不需要单独的构建环境：

```powershell
# 一次性：装打包依赖（PyInstaller）
.venv\Scripts\python.exe -m pip install pyinstaller

# 构建 wheel + 免安装包（zip 内含 tools/uv.exe 与《使用说明.txt》）
.venv\Scripts\python.exe scripts\build-release.py --exe

# 发布（默认 dry-run，看清 tag 与资产后加 --apply）
.venv\Scripts\python.exe scripts\publish-release.py --tag vX.Y.Z-previewN --prerelease `
    --asset dist-release\ts-team-kb-X.Y.Z-win-x64.zip `
    --asset dist-release\ts_team_knowledge_agent-X.Y.Z-py3-none-any.whl --apply
```

注意：

- `build-release.py` 需要**含 PyInstaller 的解释器**；缺了会直接提示 `pip install -e .[build]`。
  本项目把依赖装在 `.venv`，不要另建临时构建环境（放 `C:\tmp` 之类的目录会被清理掉）。
- 本机安装 PyInstaller 时 pip 可能报 `WinError 448 不受信任的装入点`（DLP 环境已知问题），
  但包实际已装好 —— 用 `python -c "import PyInstaller; print(PyInstaller.__version__)"` 复核，
  不要只看 pip 退出码。
- 发布后必须**回读 Release**：资产名、字节数、`state=uploaded` 三者一致才算完成。
