# codeintel —— 代码智能工具产物

本目录存放**代码智能工具**在本项目上产生的索引与图谱（同一类工具、不同层次）。
这些文件**可随时删除重建**，不作为源码；已在 `.gitignore` 中忽略，不要提交。

## 落点

```text
codeintel/graphify/<范围>/graphify-out/   Graphify：图谱（AST 节点与边）+ manifest.json + 增量 cache
codeintel/serena/                         Serena：项目配置与符号缓存（LSP）
codeintel/README.md                       本文件
```

`graphify-out/` 是 Graphify 的**规范数据目录**，不可配置：`extract --out <DIR>` 固定写 `<DIR>/graphify-out/`，
读取命令（`god-nodes` / `query` / `explain` / `affected` / `path`）默认取 `graphify-out/graph.json`，
`uninstall --purge` 也只删这一层。所以落点直接认领这一层：**不要**把内层文件手工上移到 `<范围>/` 下——
外层路径 Graphify 自己从不读取，手工上移只会让 graph.json / manifest.json / cache 停在不同时间点。

## 例外（工具不可配置，产物不在本目录）

```text
CodeGraph  索引固定在用户级 C:\Users\<用户>\.codegraph\（graph.db 等）
           该工具的 CLI 没有数据目录选项，且按项目隔离不可配置；
           因此本项目内不会出现它的产物，这是工具限制而非遗漏。
Serena     权威数据目录可理解为 codeintel/serena/；
           仓库根的 .serena 是指向它的目录联接（mklink /J），
           因为 Serena 源码把 .serena 写死在项目根，用于项目发现。
```

## 重建方式

```text
Graphify   graphify.exe extract <源码范围> --code-only --no-cluster --out codeintel/graphify/<范围>
           （产物落在 …/<范围>/graphify-out/，该层由工具固定追加，无需也不应手工搬移）
Serena     serena.exe project index <仓库根>
CodeGraph  codegraph-server.exe --graph-only --workspace <源码范围> --run-tool codegraph_pr_context
```

## 自检（一条命令确认落点）

```text
cd codeintel/graphify/<范围> && graphify god-nodes
  有输出即落点正确（该命令默认解析 graphify-out/graph.json）；
  同时核对 graph.json / manifest.json / cache/ 的修改时间属同一次运行。
```

## 使用经验

项目内的使用结论记录在 `docs/code-intelligence-log.md`。

## 常见错误（会留下散落产物）

```text
错：在源码目录下执行（如 cd frontend/src && graphify extract .）
    → 生成 frontend/src/graphify-out/，落在源码树里，属散落物
对：始终在仓库根执行，并显式给 --out codeintel/graphify/<范围>

自检：仓库根的 `git status --porcelain` 不应出现非 codeintel/ 下的 graphify-out；
     出现即为落点错误，删除该散落目录后按上文重建。
```
