# 前端技术栈定稿

本文件记录已确定的前端技术选型，避免反复更换。改动本文件等同于一次技术决策。

## 选型

| 层 | 选型 | 说明 |
| --- | --- | --- |
| 构建 | Vite | 开发态用 dev server，正式态用构建产物 |
| 框架 | React 18 + TypeScript | 严格模式；类型检查纳入验证流程 |
| 样式 | 原生 CSS + 设计 token | token 见 `src/tokens.css`（来源见下），应用样式集中在 `src/styles.css` |
| Markdown | react-markdown + remark-gfm | 渲染隔离在 `src/components/MarkdownView.tsx` |
| 路由 | react-router-dom | 多页面（对话 / 设置 / 知识概览）时启用 |
| 数据获取 | 自建 fetch 客户端 | 隔离在 `src/api/agent.ts` |
| 状态 | 自建 Hook | 隔离在 `src/hooks/useAgentChat.ts` |
| 测试 | Vitest + jsdom | 组件渲染与流式事件都有测试覆盖 |

## 隔离边界

更换任何一层实现时，只应改动对应文件：

| 想换的东西 | 只需改动 |
| --- | --- |
| Markdown 渲染器（例如改用 streamdown） | `src/components/MarkdownView.tsx` |
| 接口协议（例如改用 AG-UI 事件格式） | `src/api/agent.ts` |
| 状态管理（例如引入 TanStack Query） | `src/hooks/useAgentChat.ts` |
| 样式方案 | `src/styles.css` |

组件间只依赖自有的 `ChatMessage` / `AgentEvent` 数据结构，不依赖第三方库的类型。

## 暂不引入

- **聊天 UI 组件库（例如 @assistant-ui）**：自带 Runtime 抽象，与自有 Agent 循环重叠；版本仍在 0.x，API 变动频繁。出现消息编辑、分支、附件、线程列表等重度需求时再评估。
- **AG-UI 协议包**：属于对外 Agent 协议决策，不是 UI 依赖；需要与第三方 Agent UI 互操作时再引入。
- **CSS 框架**：当前规模不需要，先保持原生 CSS。

## 依赖纪律

`package.json` 中不得保留未使用的依赖。引入新依赖前需要说明用途，并在本文件登记。

## 设计体系

`src/tokens.css` 来源：从参考项目 `D:\2Work\OpenProjects\chatbot` 抽取的设计体系

```
C:\Users\86795\AppData\Roaming\Open Design\namespaces\release-stable-win\data\design-systems\chatbot
```

约定：

- `tokens.css` 是该设计体系的唯一来源，**不重命名 OD 标准 token**；
- 应用样式只允许引用 token，不硬编码颜色、圆角、间距；
- 需要新视觉值时应先在 `tokens.css` 增加 token，再在 `styles.css` 使用。
