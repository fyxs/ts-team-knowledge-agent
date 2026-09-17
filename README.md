# TS 团队知识 Agent（ts-team-knowledge-agent）

本地运行的团队知识生产与问答应用：扫描成员本机的源目录，把材料转成 Markdown 沉淀进共享知识仓，并基于这些知识回答问题、给出可追溯来源。

本仓只放**应用代码**，不放团队知识内容（知识在 `ts-team-knowledge-base`）。

![界面演示：悬浮会话行展开更多菜单、重命名、删除确认，以及答案块的全屏集中阅读](docs/images/session-demo.gif)

> 演示使用示例数据，不是真实知识内容。

## 它能做什么

```text
扫描本地源目录 → 按格式路由转换 → 质量与凭据门禁 → 写入个人知识空间
→ 建立全文索引 → 可选同步到共享 Git 仓
→ Web / CLI 基于知识库问答，回答附带来源
```

## 架构总览

![TS Team Knowledge Agent V1 架构总览：本地源目录 → 扫描器 → 转换适配器 → 质量门禁 → 密钥门禁 → 共享知识仓，右侧为全文索引、Agent 运行时与本地 Web](docs/images/architecture-v1.png)

采集与转换在本地完成，产物写入共享知识仓后再建立索引；问答由 Agent 运行时结合检索结果与模型服务给出，回答附带来源。分层与边界说明见 [docs/architecture-v1.md](docs/architecture-v1.md)。

## 技术栈

| 层 | 选型 |
| --- | --- |
| 前端 | React 18 + TypeScript + Vite（原生 CSS + 设计 token） |
| Markdown 渲染 | react-markdown + remark-gfm |
| 后端 | Python 3.11 + FastAPI |
| 索引 | SQLite + FTS5（FTS 优先 + 子串兜底） |
| 转换 | MinerU（独立环境，仅 PDF / Office）、Text / Markdown 直接处理 |
| 模型 | OpenAI 兼容或 Anthropic，二者可配 |
| 流程编排 | 自建 CLI + 本地计划任务 |

详见 [docs/frontend-stack.md](docs/frontend-stack.md)。

## 支持的格式

```text
.pdf / .docx / .pptx / .xlsx  → MinerU 转换
.txt                          → 编码检测后转 UTF-8 Markdown
.md                           → 原字节复制
其它扩展名                     → 扫描登记后忽略，不转换、不入库
```

Excel 额外按工作表拆分，大表按 5000 行分片。

## 快速开始

两条路径，按场景选：

**A. 免安装包（推荐给同事，无需源码和 Python）**

```text
1. 从 Releases 下载 ts-team-kb-<版本>-win-x64.zip
2. 解压到任意目录（例如 D:\apps\ts-team-kb）
3. 双击目录内《使用说明.txt》按四步走：初始化工作目录 → 制备 MinerU → 启动服务 → 打开 http://<内网IP>:8088/
（包里自带 uv.exe，没有 Python 的机器也能一步制备 MinerU）
```

**B. 源码（开发用）**

```bash
git clone <应用仓地址> ts-team-knowledge-agent && cd ts-team-knowledge-agent
python -m venv .venv
# MinerU 体积大（约 1 GB），不写进依赖安装；它由 setup-mineru 单独制备、进程外调用
.venv\\Scripts\\python.exe -m pip install -e . --no-deps
.venv\\Scripts\\python.exe -m pip install fastapi "uvicorn[standard]" pydantic openpyxl pydantic-settings
cd frontend && npm ci && npm run build && cd ..     # 前端产物，一次性
.venv\\Scripts\\ts-team-kb.exe init               # 生成工作目录（ts-kb.json / data / logs / knowledge-base）
.venv\\Scripts\\ts-team-kb.exe serve --host 0.0.0.0 --port 8088
```

构建与发布见 `docs/local-install-and-serve.md` 的「构建与发布（维护者）」。

## 在新机器上部署（Windows）

```text
1. 取程序    免安装包（解压即用）或 git clone 源码后按「快速开始 B」安装依赖
2. 初始化     ts-team-kb init            → 生成工作目录：ts-kb.json / data / logs / runtime / knowledge-base
3. 制备转换器 ts-team-kb setup-mineru    → 首次约 1 GB（离线环境可稍后再做，PDF/Word/PPT 转换需要它）
4. 装计划任务 $env:TS_KB_CONFIG="<工作目录>\ts-kb.json"; .\scripts\install-windows-tasks.ps1
              注册：Scheduler（周期扫描）/ Inspection（每日巡检）/ Evaluation（每周评测）/ WebService（登录时启动）
              ★ 只写 .ts-kb-workspace 指针与任务，不写任何机器绝对路径（换机器可重复执行）
5. 放行端口   ★ 必须做：内网访问 8088 依赖入站放行，网络类型为「公用」时尤其如此（实测踩过）
              New-NetFirewallRule -DisplayName 'ts-team-kb 8088 (inbound)' -Direction Inbound `
                  -Action Allow -Protocol TCP -LocalPort 8088 -Profile Any
6. 启动服务   登录时由任务自动拉起；也可手动 `ts-team-kb service start`（或双击工作目录 run_webui.cmd）
7. 验证       ts-team-kb service status  → 浏览器打开 http://<本机内网IP>:8088/
              提问一次，确认答案带来源；来源数量默认最多 8 条（sources_max_display 可调）
```

排查入口：

```text
服务不通    先看 8088 是否在监听（Get-NetTCPConnection -LocalPort 8088 -State Listen）；
            再看 logs\api.log（服务自身输出）与 logs\web-service.log（启动器记录）
扫描不跑    logs\scheduled-run.log（每 5 分钟敲门；扫描间隔由 ts-kb.json 的 scan_interval_minutes 决定，下限 5 分钟）
任务异常    logs\runs.jsonl 的 result 字段（ok / locked / failed）；任务计划程序的历史不可作为业务成败依据
问答报错    先确认模型服务可用（settings 里的 provider/base_url），HTTP 403/空流属于服务侧问题
```

维护者可选：`scripts\install-windows-tasks.ps1 -IncludeMaintenance` 额外注册数据层维护任务。

## 常用命令

```text
ts-team-kb serve          启动 Web 界面与 API（默认 127.0.0.1:8088）
ts-team-kb run-once       跑一轮：扫描 → 转换 → 门禁 → 索引 →（--sync）推送
ts-team-kb run-once --if-due   只在达到扫描间隔时执行
ts-team-kb search <关键词>      检索知识
ts-team-kb read <path>          读取文档（分页）
ts-team-kb list                 列出已索引文档
ts-team-kb status               转换状态与失败清单
ts-team-kb ask "<问题>"         命令行问答（检索 + 引用）
ts-team-kb config show|set|set-key   查看 / 修改模型配置与密钥
ts-team-kb schemas --output <dir>    导出知识条目 / 来源登记 / 审查记录格式
ts-team-kb inspect [--per-type N] [--if-due]    结构巡检并发布治理记录
ts-team-kb evaluate --mode retrieval|citations   检索与引用评测（citations 调模型）
ts-team-kb prune            清理本机系统产物（默认 dry-run，删最旧；不动会话库与埋点）
ts-team-kb setup-mineru    制备 MinerU 转换环境（建环境 + 安装 + 自检 + 写配置）
ts-team-kb usage [--days N] [--suggest]          埋点指标与评测题候选
ts-team-kb service start|stop|restart|status     本地 Web 服务启停与状态
```

## 工作区与数据边界

```text
源目录            只读；应用不移动、不覆盖、不删除源文件
工作目录          配置、运行日志、反馈、密钥、隔离产物
共享知识仓        Git 仓库，知识内容与登记文件
会话与历史        本机 SQLite：<工作目录>/data/sessions.sqlite3，属个人使用痕迹，不进共享仓
```

关键约定：

```text
知识输出结构      <文档名>/<文档名>.md + images/（Excel 另有 sheets/）
登记文件          registries/<成员>/sources.jsonl、knowledge.jsonl、reviews.jsonl
索引与状态        SQLite 只在本机，永不进入 Git
会话消息结构      user / process / answer / error 四类；answer 保留检索引用与工具过程
密钥              <工作目录>/secrets/model.key，不在任何 Git 仓库内
```

## 质量与安全门禁

```text
质量门禁    空内容 / 乱码 / 无效 UTF-8 / 过短 / 缺标题 → 不入库，可重试
凭据门禁    命中 sk- 密钥、真实 Bearer、apiKey 字段、私钥等 → 隔离输出并阻断同步
来源登记    每条知识记录来源文件、SHA-256、转换器版本
审查记录    问题以结构化记录留痕（registries/<成员>/reviews.jsonl）
```

## 运行方式

- 登录自启：计划任务 `TSKnowledgeAgentWebService` 在用户登录后拉起本地 Web 服务
  （`run-web-service-hidden.vbs` → 工作目录下的 `run-api.cmd`，端口已占用时直接跳过，可重复执行）。
- 定时任务错过后唤醒补跑：`TSKnowledgeAgentScheduler` 与 `TSKnowledgeAgentInspection` 均启用
  `StartWhenAvailable`，并各自按 `--if-due` 判断是否真正执行。

```text
自动    本地计划任务定时唤醒，按 scan_interval_minutes（默认 60，下限 5）决定是否执行
手动    Web 设置面板：立即扫描、拉取 / 推送共享知识仓、调整扫描间隔
Web     深色（默认）/ 浅色主题可切换；回答渲染为 Markdown 并列出来源
```

## 目录结构

详见 [docs/project-structure.md](docs/project-structure.md)。

## 相关文档

```text
docs/architecture-v1.md        应用架构与分层
docs/design-v1.md              一期设计要点与固定约束
docs/project-structure.md      工程结构规范
docs/roadmap.md                阶段进展与后续计划
docs/logging-v1.md             日志与运行记录
docs/frontend-stack.md         前端技术栈定稿
docs/local-install-and-serve.md 本地安装与启动
agent/                         给编码 Agent 的规范（入口 AGENT.md / CLAUDE.md）
```

## 开发约定

```text
分支      main 为稳定分支；日常开发在 dev，验证通过后再合并
验证      改代码后跑后端 pytest 与前端 typecheck / vitest / build
提交      不提交密钥、日志、数据库、临时产物；提交前检查 diff
```

## 治理记录边界

个人知识空间只存放该成员共享的知识；巡检与治理留痕单独存放，两者不交叉。

- 知识：`members/<成员>/`，参与检索与登记表生成
- 治理：`governance/<成员>/`（巡检报告与运行健康度），不参与检索与登记表生成
- 本机运行日志（`logs/`、`feedback/`）留在工作目录，不进入共享仓

动手巡检并写入共享仓：

```bash
ts-team-kb inspect --per-type 6        # 抽样巡检并发布治理记录
ts-team-kb inspect --no-publish        # 只写本机报告
```

初始化时同时建好个人知识目录与治理目录；每日 08:30 由计划任务
`TSKnowledgeAgentInspection` 自动巡检一次，报告随下一轮同步推给团队。

## 使用埋点与质量改进

每次问答（Web 对话与 CLI `ask`）都会静默记录一条链路，用于改进检索与提示词：

```text
记录内容    用户原话 → 模型实际发出的检索词（可能多次）→ 每次命中的文档
            → 最终引用 → 零命中的查询 → 步数 / 答案长度 / 错误
本地明细    <工作目录>/logs/usage/<日期>.jsonl
共享汇总    governance/<成员>/usage/<年月>.jsonl（按天一条，随知识仓同步推送）
开关        无：静默记录，不对外提供关闭入口，成员无需任何操作
```

用途：

```bash
ts-team-kb usage --days 7            # 零命中率 / 引用率 / 平均步数
ts-team-kb usage --suggest           # 由零命中与坏例生成评测题候选
ts-team-kb evaluate --mode retrieval  # 纯检索评测（不调模型）
ts-team-kb evaluate --mode citations  # 端到端引用评测（调模型）
```

改进闭环：真实提问 → 埋点 → 每周评测 → 零命中查询沉淀为评测题 → 调检索/提示词
→ 同一题集回归对比，达标才提交。评测报告写入 `governance/<成员>/evaluation/`。

## 巡检与评测的任务归属

```text
用户侧（成员机器）  ts-team-kb init 会安装三个计划任务：定时扫描、每日巡检、本地服务（登录自启），
                    这是日常使用所需
维护侧（维护机）    每周评测不安装到成员机器；维护机用
                    scripts\install-windows-tasks.ps1 -IncludeMaintenance 启用
                    · 每周评测（内容层，调模型，汇总真实提问与引用质量）
                    · 保留每周评测的报告发布到自己的治理目录
```

两部分都按 `--if-due` 判定到期，并通过 `StartWhenAvailable` 在关机/休眠后补跑一次。

## 发布与分发

```text
构建发布产物   python scripts/build-release.py --exe --build-python <含 PyInstaller 的解释器>（本项目已装在 .venv，可省略此参数）
               → dist-release/<wheel>（pip/pipx 分发）与 ts-team-kb-<版本>-win-x64.zip（免安装包）
发布到 Release python scripts/publish-release.py --tag v<版本> --prerelease --apply
               （默认 dry-run；上传后回读资产校验大小与 state）
产物特性       免安装包内含 Python 运行时 + 应用 + 前端产物，成员机不需要装 Python 或 Node；
               不含 MinerU（torch 约 1.1GB，转换走独立解释器），需单独制备，见 docs/local-install-and-serve.md
```
