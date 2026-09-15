# TS 团队知识 Agent（ts-team-knowledge-agent）

本地运行的团队知识生产与问答应用：扫描成员本机的源目录，把材料转成 Markdown 沉淀进共享知识仓，并基于这些知识回答问题、给出可追溯来源。

本仓只放**应用代码**，不放团队知识内容（知识在 `ts-team-knowledge-base`）。

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

```bash
# 1. 安装（后端只装本包，不拉取 MinerU 等重依赖）
git clone <应用仓地址> ts-team-knowledge-agent && cd ts-team-knowledge-agent
.venv\Scripts\python.exe -m pip install -e . --no-deps

# 2. 构建前端产物（一次性，需要 Node）
cd frontend && pnpm install && pnpm build && cd ..

# 3. 初始化：生成配置、克隆共享知识仓，并引导配置模型
ts-team-kb init --working-directory <工作目录> --personal-workspace <成员标识> --shared-source-directory <源目录>

# 4. 启动（默认只监听本机）
ts-team-kb serve
```

详细步骤、前置检查与常见问题见 [docs/local-install-and-serve.md](docs/local-install-and-serve.md)。

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
```

## 工作区与数据边界

```text
源目录            只读；应用不移动、不覆盖、不删除源文件
工作目录          配置、运行日志、反馈、密钥、隔离产物
共享知识仓        Git 仓库，知识内容与登记文件
```

关键约定：

```text
知识输出结构      <文档名>/<文档名>.md + images/（Excel 另有 sheets/）
登记文件          members/<成员>/sources.jsonl、knowledge.jsonl、reviews.jsonl
索引与状态        SQLite 只在本机，永不进入 Git
密钥              <工作目录>/secrets/model.key，不在任何 Git 仓库内
```

## 质量与安全门禁

```text
质量门禁    空内容 / 乱码 / 无效 UTF-8 / 过短 / 缺标题 → 不入库，可重试
凭据门禁    命中 sk- 密钥、真实 Bearer、apiKey 字段、私钥等 → 隔离输出并阻断同步
来源登记    每条知识记录来源文件、SHA-256、转换器版本
审查记录    问题以结构化记录留痕（members/<成员>/reviews.jsonl）
```

## 运行方式

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
```

## 已知环境注意事项

```text
公司 DLP（E-SafeNet）会对部分文件做透明加解密：
  · git、node、python 读取得到明文
  · PowerShell 的 .NET 文件 API 可能读到密文
排查文件内容时优先用 git show 或 Python/Node 读取，不要用 PowerShell 直接读字节，
否则会把正常文件误判为"损坏"。
```

### 典型报错

```text
PermissionError: [Errno 13] Permission denied             读取被拒
error: unable to unlink old '<file>': Invalid argument     git 无法替换该文件
文件开头出现 E-SafeNet / LOCK 的二进制内容                 读到的是密文而不是内容
```

### 文件被锁住时

```text
1. 关掉可能打开该文件的程序（编辑器、预览工具）——多数情况即时释放
2. 仍锁定：注销再登录
3. 仍锁定：重启机器
4. 都无效：找 IT。不要自行卸载或禁用，这是公司合规管控
```

### Git 侧临时手段

某个被锁文件阻塞提交时，可临时跳过它的本地变更（仓库内已提交的内容仍是正确明文）：

```bash
git update-index --skip-worktree <path>     # 临时跳过本地变更
git update-index --no-skip-worktree <path>  # 恢复正常跟踪
git checkout -- <path>                      # 用仓库版本覆盖本地
```

`git ls-files -v <path>` 输出以 `S` 开头即表示当前处于跳过状态。
