# 工程结构规范

## 目标

保持项目边界清晰、目录职责单一、依赖方向稳定，避免随功能增加形成难以维护的大杂烩。

## 顶层目录职责

```text
frontend/   React 前端应用（Vite，构建产物 frontend/dist）
backend/    Python 后端与应用核心
scripts/    开发、验证与运维辅助脚本
design/     设计体系（token 定义源、设计说明与预览页）
docs/       设计、协议、决策与运行说明
tests/      自动化测试
agent/      给编码 Agent 的规范（入口 AGENT.md / CLAUDE.md）
```

不在本项目存放：

```text
团队知识内容（在 ts-team-knowledge-base）
原始工作素材
SQLite 数据库、运行日志与本地缓存
模型密钥、Git 凭据与本机私有配置
```

## 后端分层

```text
api/            HTTP 接口层，只做协议适配（含前端产物托管）
cli/            CLI 表现层，只做参数解析与输出
agent/          Agent 运行时：提示词、技能、工具 schema、provider
services/       应用用例与业务流程
adapters/       外部依赖适配（MinerU、Excel、Git）
repositories/   SQLite 状态与索引访问
```

依赖方向：

```text
api / cli
    ↓
services
    ↓
adapters / repositories
```

## 关键模块

```text
services/pipeline.py        单轮流程主链路
services/scanner.py         源目录扫描与哈希
services/converter.py       格式路由
services/quality.py         Markdown 质量门禁
services/secret_scan.py     凭据扫描与隔离
services/registries.py      来源登记 / 知识条目 / 审查记录导出
services/scheduler.py       运行报告与按需执行判断
services/preflight.py       启动前置检查
services/run_lock.py        同工作目录单实例锁
agent/runtime.py            Agent 循环与 provider
agent/tools.py              工具 schema 与调度
agent/prompts、skills       系统提示词与技能
```

## 前端结构

```text
src/api/agent.ts            接口客户端（SSE 解析、配置读写）
src/api/sessions.ts         会话列表数据（静态种子；接口就绪后替换为 fetch）
src/hooks/useAgentChat.ts   对话状态机（消息按会话分开存放）
src/hooks/useSessions.ts    会话列表状态（选中、搜索、新建、分组、折叠）
src/hooks/useTheme.ts       主题切换
src/components/             展示组件（消息、过程块、会话面板、弹窗、设置面板等）
src/tokens.css              设计体系 token（唯一视觉来源）
src/styles.css              应用样式（只引用 token）
```

新增能力时优先新增模块，不要把它们堆进 `main.tsx` 或 `pipeline.py`。
