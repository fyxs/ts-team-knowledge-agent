# ts-knowledge-agent 工程结构规范

## 目标

保持项目边界清晰、目录职责单一、依赖方向稳定，避免随着功能增加形成难以维护的大杂烩。

## 顶层目录职责

```text
frontend/   React 前端应用
backend/    Python 后端和应用核心
scripts/    开发、验证和运维辅助脚本
config/     示例配置和非敏感默认配置（如需要）
docs/       设计、协议、决策和运行说明
tests/      自动化测试
```

不在本项目存放：

- 团队知识内容；
- 原始工作素材；
- SQLite 数据库、运行日志和本地缓存；
- 模型密钥、Git 凭据和本机私有配置；
- `ts-knowledge-base` 的副本。

## 后端分层

```text
api/            HTTP/AG-UI 接口层，只做协议适配
cli/            CLI 表现层，只做参数解析和输出
services/       应用用例和业务流程
adapters/       MinerU、Harness、Git 等外部依赖适配
repositories/   SQLite、索引和本地状态访问
workers/        定时任务和后台执行
models/         数据模型和 Schema
```

依赖方向：

```text
api / cli / workers
        ↓
services
        ↓
adapters / repositories
```

API、CLI 和 Worker 不得各自实现一套扫描、转换、索引或同步逻辑。

## 前端分层

```text
src/app/         应用入口、路由和全局配置
src/features/    按业务能力组织页面和状态
src/components/  跨功能复用的 UI 组件
src/api/         后端 API/AG-UI 客户端
src/lib/         无业务含义的通用工具
```

前端采用纯 React + TypeScript + Vite；不引入 Vue，不把业务逻辑放入通用组件。

## 功能增长规则

新增功能先判断属于已有层还是新边界：

1. 优先扩展已有模块；
2. 只有出现稳定、独立职责时才新建目录；
3. 不为尚未实现的功能预建大量空目录；
4. 一个文件不同时承担 API、业务流程、外部调用和持久化；
5. 先用一个垂直切片验证，再抽象公共模块；
6. 每次结构变更同步更新本文件和架构文档。

## 当前 V1 模块边界

```text
scanner       本地源目录扫描和变化检测
converter     MinerU 转换
extraction    模型驱动的知识提炼
indexer       SQLite/FTS5 索引
sync          固定 Git 知识仓同步
scheduler     每小时任务调度
search        本地知识搜索
```

这些模块属于 `ts-knowledge-agent`；知识内容属于 `ts-knowledge-base`。

## 配置边界

固定项由应用内置：

```text
Git 远程仓库：git@github.com:fyxs/ts-knowledge-base.git
单公司模式
```

成员本地配置项：

```text
personal_personal-workspace
个人知识空间
本地知识源目录
本地服务端口等运行参数
```

模型沿用当前 Harness 工作模型，不在知识仓中保存模型密钥。

## 变更检查

目录或技术选型变化后至少检查：

- 是否越过项目边界；
- 是否产生重复业务逻辑；
- 是否引入新的运行时依赖；
- 是否影响固定 Git 仓和个人知识仓库中的知识空间模型；
- 是否需要更新 docs、测试和 README；
- 是否能通过最小编译/类型/单元验证。
