# TS Knowledge Agent：V1 应用架构

## 定位

`ts-team-knowledge-agent` 是本地运行的知识生产与搜索应用，不是 `ts-team-knowledge-base` 的替代品，也不是通用执行型 Agent。

## 分层

```text
React Web UI（@assistant-ui/react）
        ↓ AG-UI 事件协议
本地 FastAPI API / 服务层
        ├── 扫描器：每小时扫描本地知识源
        ├── 转换器：内置运行环境中的 MinerU
        ├── 提炼器：沿用 Harness 工作模型
        ├── 索引器：SQLite + FTS5
        ├── Git 适配器：固定 ts-team-knowledge-base
        └── 调度器：处理、索引、同步
```

## AG-UI 边界

AG-UI 是客户端与 Agent 之间的事件语义协议，不等同于 SSE 或 WebSocket。第一期确定默认采用 AG-UI over SSE；WebSocket 仅作为未来明确需要双向实时控制时的传输适配器。

一期先实现知识收集、转换、沉淀和搜索闭环；外部 Agent（Claude Code、Hermes 等）的 MCP/HTTP/子 Agent 接入后置。

## 成员空间

每个成员初始化时配置个人空间。成员空间表示写入归属与维护责任，不是可见性隔离；已进入固定知识仓的内容默认团队共享、可被本地 Agent 搜索。

## 数据边界

- 原始文件只读，不移动、重命名、覆盖、归档或删除。
- 原始文件不上传 Git。
- SQLite、运行日志和本地配置不上传 Git。
- Git 只保存成员空间中的处理结果、知识、来源和必要元数据。
