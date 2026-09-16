# Claude 入口

## 代码智能三件套（改代码前默认动作）

动手改代码前，按 `agent/workflow.md` 的「代码智能三件套」执行：CodeGraph 划影响范围 →
Serena 查符号与引用 → 改 → 按边界回归。工具与经验沉淀见共享技能 `code-intelligence-tooling`。

本文件是 Claude Code 在本项目中的最小入口，不承载独立的项目规则。

开始任务前必须阅读：

1. `AGENT.md`
2. `agent/README.md`
3. `agent/engineering-rules.md`
4. `agent/workflow.md`
5. 与当前任务相关的 `docs/` 文档
6. 涉及界面、样式或交互时，必须先读 `design/README.md`

Claude Code 与其他 Agent 遵守同一套项目规范。需要修改通用约定时，只更新 `agent/` 目录中的权威文件，不在本文件复制规则。
