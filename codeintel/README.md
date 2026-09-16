# codeintel —— 代码智能工具产物

本目录存放**代码智能工具**在本项目上产生的索引与图谱（同一类工具、不同层次）。
这些文件**可随时删除重建**，不作为源码；已在 `.gitignore` 中忽略，不要提交。

## 落点

```text
codeintel/graphify/<范围>/graph.json   Graphify：架构级图谱（AST 节点与边）
codeintel/serena/                      Serena：项目配置与符号缓存（LSP）
codeintel/README.md                    本文件
```

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
           （工具会再套一层 graphify-out/，生成后把内层内容上移一层）
Serena     serena.exe project index <仓库根>
CodeGraph  codegraph-server.exe --graph-only --workspace <源码范围> --run-tool codegraph_pr_context
```

## 使用经验

项目内的使用结论记录在 `docs/code-intelligence-log.md`。
