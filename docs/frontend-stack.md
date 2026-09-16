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

视觉与交互的**唯一来源是仓库内的 `design/`**，入口是 `design/README.md`：

| 位置 | 角色 |
| --- | --- |
| `design/tokens.css` | 标准 token 定义源（来自设计体系，命名不得改动） |
| `design/DESIGN.md`、`design/preview/` | 设计说明与颜色/字体/间距/组件预览 |
| `frontend/src/tokens.css` | 运行时副本 = 标准 token + 本项目扩展 token |
| `frontend/src/styles.css` | 应用样式，只允许引用 token |

改动界面前先读 `design/README.md`，其中列出硬规则与改动自检清单。

提取来源（参考项目 `D:\2Work\OpenProjects\chatbot`）：

```
C:\Users\86795\AppData\Roaming\Open Design\namespaces\release-stable-win\data\design-systems\chatbot
```

约定：

- **不重命名标准 token**；标准 token 集合由 `tests/test_design_tokens.py` 校验，漏改或改名会失败；
- 应用样式只允许引用 token，不硬编码颜色、圆角、间距（同一测试拦截 `#hex` / `rgb()` / `hsl()`）；
- 需要新视觉值时，先在 `frontend/src/tokens.css` 的应用扩展区块新增，再登记到本文件的扩展表。

应用扩展 token（源设计体系未定义，已在 `tokens.css` 中单独标注）：

| token | 用途 |
| --- | --- |
| `--overlay` | 弹窗遮罩，随主题变化 |
| `--content-max` | 主区域内容宽度阶梯：默认 896px（设计体系 `container-max`），≥1600px 为 1080px，≥1920px 为 1200px |
| `--session-panel-w` | 历史会话列宽度（264px） |
| `--content-max-sessions` | 含会话列时的主区域上限（1180px）。宽屏下与 `--content-max` 取较大值，使消息列维持接近原来的阅读宽度 |
| `--dialog-w` | 确认框宽度（400px）。删除等二次确认只有标题、一段说明和两个按钮，用不着配置弹窗那档 560px |
| `--elev-float` | 浮层阴影：会话列抽屉、弹窗等脱离文档流的表面 |
| `--mark-bg` | 正文里命中片段的底色（浅色 `oklch(0.72 0 0)` / 深色 `oklch(0.5 0 0)`）。不复用 `--accent-active`：那个值要给按钮悬浮态用，必须含蓄；命中要被一眼看见，需要与卡片底色拉开 2.5–3:1。文字仍是 `--fg` |
