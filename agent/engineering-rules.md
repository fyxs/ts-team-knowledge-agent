# Agent 工程规则

## 项目边界

- 本仓库是 CLI + 本地 Web 应用源码仓库。
- 团队共享知识内容属于 `ts-team-knowledge-base`，不复制进本仓库。
- 原始工作素材、SQLite、运行日志、本机配置、Token、密码和 Cookie 不提交 Git。

## 结构约束

```text
frontend/   React + TypeScript + Vite 前端
backend/    Python 后端；唯一包为 backend/ts_knowledge_agent/
docs/       设计、协议和决策文档
scripts/    开发、验证和运维脚本
tests/      自动化测试
agent/      Agent 项目规范
```

后端分层保持：

```text
api / cli / workers → services → adapters / repositories
```

CLI、Web 和调度器不得各自实现扫描、转换、索引或 Git 同步逻辑。

## 技术边界

- 前端统一使用 React，不引入 Vue。
- UI 组件优先使用 `@assistant-ui/react` 系列；AG-UI 是客户端与 Agent 的协议边界。
- 后端使用 FastAPI；本地状态和全文索引使用 SQLite/FTS5。
- MinerU、Harness 和 Git 通过适配器接入。
- Git 远端知识仓固定为 `git@github.com:fyxs/ts-team-knowledge-base.git`，不在普通初始化流程开放切换。
- 单公司模式；成员个人空间在初始化时配置，成员知识写入隔离、读取共享。

## 编码规则

- 先读取相关设计文档，再修改代码。
- 新功能优先完成一个垂直切片，不提前搭建无用抽象。
- 一个模块只承担单一职责；接口层不承载业务流程。
- 配置集中读取，避免各模块自行解析环境变量。
- 错误必须可诊断；不要吞异常或用成功状态掩盖失败。
- 代码、配置和 Markdown 统一 UTF-8。

## 安全边界

- Agent 默认只访问配置的源目录、应用数据目录和本地知识仓工作副本。
- 不读取无关目录，不把凭据放进日志、知识或异常信息。
- 不移动、重命名、覆盖、归档或删除用户原始文件。
- Git push、删除共享知识、修改关键规则前必须有明确任务授权。
