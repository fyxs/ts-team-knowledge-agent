# TS Knowledge Agent：V1 工程结构

## 技术基线

- 前端：React + TypeScript + Vite + `@assistant-ui/react`
- 后端：FastAPI + Python
- 本地状态和索引：SQLite + FTS5
- 材料转换：MinerU（由应用运行环境管理）
- 模型：沿用当前 Harness 工作模型
- Agent 事件协议：AG-UI；默认 SSE，WebSocket 后置
- 共享知识：固定 Git 仓 `git@github.com:fyxs/ts-knowledge-base.git`

## 目录

```text
ts-knowledge-agent/
├── frontend/       React 前端
├── backend/        Python 后端和应用核心
├── scripts/        开发、验证和运维辅助脚本
├── config/         示例和默认配置（不含密钥）
├── docs/           设计、协议、决策和运行说明
└── tests/          自动化测试
```

## 运行边界

每台成员机器本地运行 CLI、后台任务、SQLite 和 Web 应用。应用扫描成员配置的本地源目录，处理结果写入固定 Git 仓的个人知识仓库中的知识空间；团队知识通过 Git 同步。

原始文件、SQLite、日志、本机配置和模型密钥不进入代码仓库或团队知识仓。

## 代码组织原则

CLI、Web API 和定时 Worker 共享同一套 application services；不得各自实现扫描、转换、提炼、索引和 Git 同步逻辑。

先完成垂直切片，再抽象公共模块；不为尚未实现的能力提前建立复杂目录和依赖。

详细规则见 `docs/project-structure.md`。
