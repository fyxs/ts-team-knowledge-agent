# Agent 项目规范

本目录集中维护所有约束 Agent 参与本项目开发的规范、流程和检查清单。

## 文件职责

- `engineering-rules.md`：工程结构、依赖边界、技术边界、前端规则、环境注意事项的权威来源。
- `workflow.md`：任务开始、实现、验证、提交与分支约定。
- `backend-cli-tasks.md`：后端与 CLI 的实施进度与待办。

## 相关文档

新建或修改功能前，除本目录外还应阅读与任务相关的 `docs/`、`design/`：

```text
docs/architecture-v1.md        应用架构与事件协议
docs/design-v1.md              一期设计要点与固定约束
docs/project-structure.md      工程结构规范
docs/frontend-stack.md         前端技术栈定稿（做前端必读）
docs/local-install-and-serve.md 本地安装与启动
docs/logging-v1.md             日志与运行记录
docs/code-intelligence-log.md  代码智能工具使用记录
docs/roadmap.md                阶段进展与后续计划
```

## 工程基线

本项目的工程结构、Agent 入口规范、工作流与工程规约来自团队工程基线工程
（`git@github.com:fyxs/engineering-baseline.git`）。本目录的 `engineering-rules.md`
与 `workflow.md` 是该基线在**本项目技术栈**上的落地版本：

```text
基线标准（跨项目）    engineering-baseline/standards/
本项目落地（含栈细节） agent/engineering-rules.md · agent/workflow.md
```

新增或修改通用约定前，先确认基线是否已有规定；如有，先在基线工程修订，
再同步到本项目，避免各项目各写一套。

## 维护原则

`AGENT.md` 和 `CLAUDE.md` 只做入口索引；通用约束只在本目录维护，避免多份规则漂移。新增规则前先判断是否已有文件可以承载；规则与代码结构变化必须同步更新。
