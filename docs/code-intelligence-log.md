# 代码智能工具使用记录（本项目）

记录在本仓库使用 Graphify / CodeGraph / Serena 的结果与结论。
使用规程见 `agent/workflow.md` 的「改代码前：代码智能三件套」。

格式：

```text
日期 | 工具与版本 | 扫描范围与排除项 | 文件/节点/边 | 结论或坑
```

## 记录

## 2026-09-16 | 首次只读试用（本项目）

工具版本：Graphify 0.9.49 · CodeGraph 0.20.1 · Serena 1.7.1.dev0
扫描范围：`backend/ts_knowledge_agent`（47 个 py / 217 KB）· `frontend/src`（19 个 ts|tsx / 91 KB）
排除项：`__pycache__` · `.venv` · `node_modules` · `dist` · `graphify-out`
产物位置：`codeintel/graphify/backend/`、`codeintel/graphify/frontend-src/`（Graphify 图谱）· `codeintel/serena/`（Serena 配置与符号缓存，仓库根 `.serena` 是指向它的目录联接）
（三者均已被 .gitignore 忽略；CodeGraph 索引固定写用户级 `~\.codegraph\`，不在仓库内）
仓库对照：试用前后 `git status` 均为 clean（未改动任何业务文件）

### 结果

| 工具 | 范围 | 耗时 | 结果 |
| --- | --- | --- | --- |
| Graphify | backend | 5.2 s | 496 节点 / 1344 边（纯 AST，`--code-only`） |
| Graphify | frontend/src | 1.5 s | 94 节点 / 193 边 |
| CodeGraph | backend | 23.5 s | 47 文件解析（47 成功 / 0 跳过）· 580 节点 · 1133 边 · 16 条路由 |
| Serena | 仓库根 | 15.6 s | python + typescript 语言服务器，索引 python=110 / typescript=21 个文件 |

### 有价值的输出示例

Graphify 中心节点（`god-nodes`）：

```text
Settings 77 · main() 59 · SessionStore 33 · _run_once_locked() 25 · StateStore 23
run_agent() 19 · load_settings() 19 · SearchStore 17 · RunSummary 14 · knowledge_search() 13
```

与 `docs/architecture-v1.md` 的手工描述互相印证：`Settings` 是全局配置入口（几乎所有模块依赖它）、
`main()` 是 CLI 枢纽、三个存储类（Session/State/Search）是核心、`_run_once_locked()` 是扫描流水线汇聚点。

CodeGraph `pr_context`（dev 相对 main）：29 文件变更（+1830/−218）、风险评级 low；
函数级变更为 0 —— 它按函数 diff 统计，跨多提交的改动会被折叠。

### 踩到的点（下次直接用）

1. Graphify 会把 `frontend/src/tokens.css` 判为「疑似敏感文件」跳过，`styles.css` 因无支持扩展名分类跳过
   → 前端图谱实际只覆盖 ts/tsx，样式文件不在图内。
2. Graphify `affected <名字>` 需要**唯一节点名**：写 `pipeline` 会返回 `No unique node match`；
   应改用完整符号名（如 `run_once`），或先用 `god-nodes` / `query` 拿到准确名字。
3. CodeGraph `--graph-only` 只做结构索引、不生成 embedding（语义搜索需额外模型与内存）；
   索引会持久化成 `graph.db`（namespace 由项目名 + 哈希生成），后续会话可复用。
4. Serena 的符号级查询在 CLI 上没有直接命令，需通过 MCP / LSP 会话使用；
   CLI 负责的能力是：建项目、索引、健康检查、memories。

## 2026-09-16 | 引用来源阅读改动（Graphify + CodeGraph 复核）

改动范围：后端 `agent/runtime.py`、`api/main.py`、`services/knowledge_tools.py`＋新增 `services/markdown.py`；
前端 `components/SourceReader.tsx`（新增）、`AnswerArticle.tsx`、`MarkdownView.tsx`、`App.tsx`、`api/agent.ts`。

| 工具 | 范围 | 结果 | 与上次对照 |
| --- | --- | --- | --- |
| Graphify | backend | 552 节点 / 1464 边 | 上次 496 / 1344（+56 / +120，对应新增模块与函数） |
| Graphify | frontend/src | 124 节点 / 265 边 | 上次 94 / 193（+30 / +72，对应新增组件与测试） |
| CodeGraph | backend | 48 文件解析 · 1198 节点 · 2504 边 · 34 条路由 | 上次 47 文件 · 580 节点 · 1133 边 · 16 路由 |

回归边界（由读全量调用方 + 全量测试确认，未依赖工具结论）：

```text
citations 的消费方   cli/main.py（ask 输出、评测）、api/main.py（响应与会话落库）、前端 api/agent.ts
                     → 因此 sources 走「追加」而不是改形，三处消费方零改动
run_agent 的调用方   api/main.py、cli/main.py、services/evaluation.py、tests/
MarkdownView 的宿主  AnswerArticle（新增可选 basePath，其余调用点不传即行为不变）
AnswerArticle 的宿主 MessageList、FocusView（新增 onOpenSource，不传则引用退回不可点）
```

### 本轮踩到的点（下次直接用）

1. `codegraph_get_callers` 不接受符号名：必须给 `nodeId` 或 `uri+line`；直接传 `{"symbol": "..."}`
   返回 `Could not find starting node`。`codegraph_symbol_search` 给的是模糊匹配（查 `run_agent`
   会先返回 `_run`），要拿 nodeId 得自己按 `symbol.name` 过滤。本轮未继续追符号级调用方，
   影响范围由读调用方 + 全量测试确认。
2. Graphify 的产物会**嵌套一层 `graphify-out/`**，这是工具的规范数据目录：`extract --out <DIR>` 固定写
   `<DIR>/graphify-out/`，读取命令默认取 `graphify-out/graph.json`，`uninstall --purge` 也只删这一层。
   落点已按该原生长度登记为 `codeintel/graphify/<范围>/graphify-out/`，不再手工上移（见下条记录）。
3. 每次 CodeGraph 运行会重新索引（本轮约 70 s，其中 memory 初始化占大头），一次会话里不要反复跑。

## 2026-09-16 | 产物落点校正（Graphify 0.9.49）

背景：`codeintel/graphify/<范围>/` 下曾同时存在外层副本与内层 `graphify-out/`；手工「把内层内容上移一层」
只搬了 `graph.json`，外层的 `manifest.json` 与 `cache/` 停在上一次运行 —— 落点会静默变旧，且没有任何提示。

| 项 | 内容 |
| --- | --- |
| 动作 | 落点统一为 `codeintel/graphify/<范围>/graphify-out/`（`agent/engineering-rules.md`、`codeintel/README.md`）；删除旧外层副本（`graph.json` / `manifest.json` / `cache/` / `.graphify_root`）；`codeintel/README.md` 增「自检」段 |
| 依据 | `graphify --help`：`extract --out DIR` 固定写 `<DIR>/graphify-out/`（无关闭选项）；`god-nodes` / `query` / `explain` / `affected` / `path` 默认取 `graphify-out/graph.json`；`uninstall --purge` 只删这一层 |
| 核验 | 在 `<范围>` 目录下直接跑 `graphify god-nodes` 命中内层图：backend → Settings 89 / main() 59 / SessionStore 33；frontend-src → SettingsPanel() 9 / AnswerSource 8 / SourceReader() 6（含本轮新增组件） |
| 结论 | 命令跑完即完整，`graph.json` / `manifest.json` / `cache/` 天然同版本；读取命令无需 `--graph` |
