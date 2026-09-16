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
产物位置：`C:\tmp\trial-codeintel\`（Graphify 图谱）· `backend/.serena/`（Serena 缓存，已 gitignore）
仓库对照：试用前后 `git status` 均为 clean（未改动任何业务文件）

### 结果

| 工具 | 范围 | 耗时 | 结果 |
| --- | --- | --- | --- |
| Graphify | backend | 5.2 s | 496 节点 / 1344 边（纯 AST，`--code-only`） |
| Graphify | frontend/src | 1.5 s | 94 节点 / 193 边 |
| CodeGraph | backend | 23.5 s | 47 文件解析（47 成功 / 0 跳过）· 580 节点 · 1133 边 · 16 条路由 |
| Serena | backend | 25.0 s | python 语言服务器，索引 47 个文件 |

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
