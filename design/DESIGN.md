# Chatbot

> 类别：Imported ｜ 载体：Web 应用（Next.js App Router）
> 设计系统 id：`chatbot`
> 来源项目：`D:\2Work\OpenProjects\chatbot`

## 一句话概括

一套**克制的中性灰阶系统**：整个界面只有明度变化，没有品牌色相；视觉重心全部让给对话内容本身，界面外壳（侧边栏、输入区、按钮）保持低对比、低阴影、低存在感。

## 来源与栈

- 来源项目：`D:\2Work\OpenProjects\chatbot`
- 检测到的技术栈：`next`、`react`、`next-auth`、`next-themes`、`@ai-sdk/react`、`framer-motion`、`lucide-react`、`radix-ui`、`react-data-grid`、`streamdown`
- 样式方案：**Tailwind v4（CSS-first）**。没有 `tailwind.config.*`，全部 token 定义在 `app/globals.css` 的 `@theme inline` 与 `:root` / `.dark` 中
- 组件方案：shadcn/ui 风格，Radix 原语 + `class-variance-authority`
- 字体：`next/font/google` 加载 **Geist** 与 **Geist Mono**

## 视觉基调

1. **单色**。`--accent` 是 `oklch(0.965 0 0)`——一个中性表面色，不是色相。产品里唯一带有颜色的地方是图表色阶和代码编辑器的选区蓝。新增界面不要引入品牌色相。
2. **极低阴影**。明面上的层级用 1px 边框表达，阴影只做"接触感"（`--shadow-card` 的总不透明度不到 8%）。
3. **暗色是一等公民**。每个颜色 token 都有配对的暗色值，暗色不是简单反色。
4. **标题紧凑、正文宽松**。标题 `line-height: 1.2` + `letter-spacing: -0.025em`；正文 `line-height: 1.6`。
5. **界面字号偏小**。区块固定用 `text-sm`（14px），密集控件甚至用任意值 `text-[12px]` / `text-[13px]`。

## 色彩

### 语义角色

| 角色 | 亮色 | 暗色 | 来源 |
|---|---|---|---|
| `--bg` 页面底 | `oklch(0.985 0 0)` | `oklch(0.195 0 0)` | `--background` |
| `--surface` 卡片/浮起面 | `oklch(1 0 0)` | `oklch(0.225 0 0)` | `--card` / `--popover` |
| `--surface-warm` 次级填充 | `oklch(0.965 0 0)` | `oklch(0.26 0 0)` | `--secondary` |
| `--fg` 主文本 | `oklch(0.12 0 0)` | `oklch(0.94 0 0)` | `--foreground` |
| `--fg-2` 次级文本 | `oklch(0.38 0 0)` | `oklch(0.75 0 0)` | `--secondary-foreground` / `--sidebar-foreground` |
| `--muted` 静默填充 | `oklch(0.94 0 0)` | `oklch(0.165 0 0)` | `--muted` |
| `--meta` 元信息文本 | `oklch(0.58 0 0)` | `oklch(0.6 0 0)` | `--muted-foreground` |
| `--border` 边框 | `oklch(0.9 0 0)` | `oklch(0.27 0 0)` | `--border` |
| `--border-soft` 内部分隔 | `oklch(0.88 0 0)` | `oklch(0.25 0 0)` | `--sidebar-border` |
| `--accent` 中性强调面 | `oklch(0.965 0 0)` | `oklch(0.26 0 0)` | `--accent` |
| `--accent-on` 强调面上的前景 | `oklch(0.12 0 0)` | `oklch(0.94 0 0)` | `--accent-foreground` |
| `--danger` 危险 | `oklch(0.55 0.15 25)` | `oklch(0.7 0.15 25)` | `--destructive` |

### 暗色参考值

暗色模式由 `.dark` 类切换（`next-themes`），完整对照见来源项目 `app/globals.css:97-141`。要点：

- 页面底 `0.195` → 卡片 `0.225` → 输入/浮层 `0.26`，是**逐级提亮**，不是压暗
- 主按钮在暗色下**反转为亮底深字**（`--primary: oklch(0.94 0 0)`），与亮色模式的深底亮字相反
- 侧边栏另有独立一档：`--sidebar: oklch(0.175 0 0)`，比页面底更沉

### 状态色（注意）

`--success` 与 `--warn` 在来源项目中**不存在**，包内保留的是 schema 默认值（`#16a34a` / `#eab308`）。使用前请确认，不要当成已提取的事实。`--accent-hover` / `--accent-active` 同样是推导值。

### 图表色阶

亮色 `--chart-1..5`：`oklch(0.646 0.222 41.116)`、`oklch(0.6 0.118 184.704)`、`oklch(0.398 0.07 227.392)`、`oklch(0.828 0.189 84.429)`、`oklch(0.769 0.188 70.08)`。暗色下整套替换为另一组（见 `globals.css:116-120`），不是同色缩放。

## 字体

- **正文与标题同一族**：Geist（`--font-geist`）。这是刻意的——产品只需要一套家用字。
- **等宽**：Geist Mono（`--font-geist-mono`），用于代码块、控制台、斜杠命令。
- 代码编辑器（CodeMirror）额外前置一套原生栈：`"SF Mono", "Cascadia Code", "Fira Code", "JetBrains Mono", ui-monospace`。
- `body` 启用了 Geist 的 OpenType 特性：`font-feature-settings: "ss01", "ss02", "cv01"`，并开启抗锯齿与 `text-rendering: optimizeLegibility`。

### 字号

沿用 Tailwind v4 默认刻度（项目未在 `@theme` 覆盖任何 `--text-*`）：`xs 0.75rem` / `sm 0.875rem` / `base 1rem` / `lg 1.125rem` / `xl 1.25rem` / `2xl 1.5rem` / `3xl 1.875rem` / `4xl 2.25rem`。

界面密集处另行使用 `text-[12px]`、`text-[13px]` 两个非标尺档位（控制台、斜杠命令、输入框）。

> **已知接线缺口**：`app/layout.tsx` 通过 `next/font` 声明了 `--font-geist`，但 `globals.css` 的 `@theme` 区块**没有**把 `--font-sans` 指向它。因此 Tailwind 的 `font-sans` 工具类目前回落到系统字体栈，只有 `font-mono` 因为组件里显式使用而走到了 Geist Mono 的兜底栈。若要让 Geist 真正生效，需要在 `@theme inline` 中补一行 `--font-sans: var(--font-geist);`。`tokens.css` 里按**设计意图**记录为 Geist。

## 圆角

全部圆角由单一变量派生（`globals.css:50` + `@theme inline:12-15`）：

```
--radius: 0.625rem        /* 10px —— 卡片与弹窗的基准 */
--radius-sm: 6px          /* calc(var(--radius) - 4px) —— 小控件 */
--radius-md: 8px          /* calc(var(--radius) - 2px) —— 按钮、输入框 */
--radius-lg: 10px         /* var(--radius) —— 卡片 */
--radius-xl: 14px         /* calc(var(--radius) + 4px) —— 浮层容器 */
--radius-pill: 9999px     /* 仅用于头像、徽标、滚动条滑块 */
```

要改整体圆润度，只改 `--radius` 一处。

## 高度与阴影

项目定义了 6 档阴影，包内只映射了其中 3 档到 schema 槽位，其余按原样记录：

| 变量 | 亮色 | 用途 |
|---|---|---|
| `--shadow-card` | `0 1px 3px /5%, 0 1px 1px /3%` | 卡片默认 → 映射为 `--elev-raised` |
| `--shadow-float` | `0 8px 24px -6px /10%, 0 2px 8px -2px /4%` | 悬浮层、弹层 |
| `--shadow-composer` | `0 1px 2px /4%` | 输入区静置 |
| `--shadow-composer-focus` | `0 0 0 1px /6%, 0 2px 8px -2px /6%` | 输入区聚焦 |
| `--shadow-inset` | `inset 0 1px 1px /3%` | 内凹面 |
| `--shadow-glow` | `0 0 20px /8%` | 光晕 |

暗色下 `--shadow-card` / `--shadow-float` / `--shadow-composer*` 全部换成**带内高光**的版本（`inset 0 1px 0 oklch(1 0 0 / 0.04)`），因为纯黑阴影在深色底上不可见。

层级优先级：**边框 > 阴影**。浮起面先靠 1px `--border` 分离，阴影只补接触感。

## 动效

三条缓动曲线，语义不同，不要混用：

| 变量 | 曲线 | 用途 |
|---|---|---|
| `--ease-smooth` | `cubic-bezier(0.4, 0, 0.2, 1)` | **通用**，映射为 `--ease-standard` |
| `--ease-spring` | `cubic-bezier(0.22, 1, 0.36, 1)` | 入场（`fade-up`） |
| `--ease-bounce` | `cubic-bezier(0.34, 1.56, 0.64, 1)` | 微交互的俏皮回弹，**会过冲**，勿作默认 |

关键帧（`globals.css:258-378`）：`fade-up` 0.25s、`fade-in` 0.2s、`message-in` 0.3s `cubic-bezier(0.16, 1, 0.3, 1)`、`dot-pulse` / `thinking-dot` 1.4s（等待指示）、`shimmer` 2s（骨架屏）、`glow-pulse` 2s（输入区呼吸光）。

## 布局

```
┌──────────┬──────────────────────────────────┐
│ Sidebar  │  对话线程（mx-auto, max-w-4xl）    │
│ 可拖拽    │  gap-5 / md:gap-7                 │
│ 默认 356px│  px-2 / md:px-4                   │
│          ├──────────────────────────────────┤
│          │  Composer（固定在底部）             │
└──────────┴──────────────────────────────────┘
```

- 外壳是**全宽 flex 布局**，不是居中容器。`--container-max: 896px` 仅约束消息列（`max-w-4xl`）。
- 侧边栏宽度可拖拽，`w-[356px]` 是常见档位。
- 手机端横向内边距只有 **8px**（`px-2`），刻意压到最窄以最大化消息宽度；`md` 起为 16px。
- `html` / `body` 均设 `overflow-x: hidden`。

> `--section-y-*` 三个 token 在本项目中**不适用**——这是全屏应用外壳，没有滚动式营销分区。包内保留 schema 默认值并标记为 fallback。

## 组件语言

- **输入区（Composer）**：底部固定，圆角 `--radius-lg`，1px 边框 + 极轻阴影；聚焦时切换到 `--shadow-composer-focus` 并叠加 `glow-pulse` 呼吸动画。
- **消息气泡**：用户消息用 `--accent` 底 + `--accent-on` 字，右对齐；助手消息无底色，直接落在 `--bg` 上。整条消息入场用 `message-in`（0.3s，轻微上移 8px + 淡入）。
- **侧边栏行**：静置透明，悬浮用半透明前景叠加（`--sidebar-accent: oklch(0.12 0 0 / 0.06)` / 暗色 `oklch(0.94 0 0 / 0.06)`），选中用实心 `--accent`。不靠变色区分，靠**明度叠加**。
- **按钮**：默认 `--radius-md`；主按钮亮色下是深底亮字（`--primary: oklch(0.12 0 0)`），暗色下反转。
- **滚动条**：4px 宽，滑块 `oklch(0 0 0 / 0.12)`，悬浮加深到 `0.25`；暗色下为 `oklch(1 0 0 / 0.1)` → `0.2`。

## 本次校验修正

导入器首轮产出评级为 `needs-rebuild`（score 32）。逐条对照 `app/globals.css` 与组件源码后修正如下（完整逐条依据见 `source/token-contract.report.json`）：

| 修正项 | 首轮值 | 修正值 | 依据 |
|---|---|---|---|
| `--font-display` / `--font-body` | Inter | Geist | `layout.tsx:20` 加载 + `globals.css:148` 启用 Geist 特性 |
| `--font-mono` | 通用兜底栈 | Geist Mono 起头 | `layout.tsx:26` + `globals.css:385` |
| `--text-xl/2xl/3xl/4xl` | 1.375/1.75/2.25/3 rem | 1.25/1.5/1.875/2.25 rem | Tailwind v4 默认刻度 |
| `--leading-body` / `--leading-tight` | 1.55 / 1.15 | 1.6 / 1.2 | `globals.css:187` / `:182` |
| `--tracking-display` | 0 | -0.025em | `globals.css:183` |
| `--radius-sm/md/lg` | 8px / 0.625rem / 16px | 6px / 8px / 10px | `globals.css:12-14` 的 calc 派生 |
| `--meta` | 别名到 `--muted` | `oklch(0.58 0 0)` | `--muted-foreground` |
| `--border-soft` | 别名到 `--border` | `oklch(0.88 0 0)` | `--sidebar-border` |
| `--ease-standard` | bounce 曲线（会过冲） | `cubic-bezier(0.4,0,0.2,1)` | `--ease-smooth` |
| `--elev-ring` | 绑了 `--ring` 颜色（类型错误） | `0 0 0 1px var(--border)` | 项目以 1px 边框表达细线 |
| `--container-max` / 三档 gutter | 1120 / 32 / 24 / 16 px | 896 / 16 / 16 / 8 px | `components/chat/messages.tsx:81` |
| `--radius-pill` | schema 默认 | `9999px`（确认） | `globals.css:478` |

修正后：**source-backed 49 / 56**，fallback 7（均为来源项目确实没有的语义色与不适用槽位），score 88 / `usable`。

## 已知缺口

1. **Geist 未接线**（见上文"已知接线缺口"）——这是来源项目的一个真实缺陷，不是提取误差。
2. **全局移除了焦点轮廓**：`globals.css:191-197` 对 `button` / `input` / `textarea` / `select` / `[role="button"]` 的 `:focus-visible` 设了 `outline: none`，且没有补替代方案。生成新界面时**必须自行补可见的焦点环**（可用 `--focus-ring`），不要沿用这个行为。
3. **`--success` / `--warn` 无来源依据**，是 schema 默认值。
4. 未复制 logo / 图标资源；图标体系为 `lucide-react`，按需引入。

## 使用方式

1. `tokens.css` 是颜色、圆角、间距、字体的第一手依据。
2. `components.html` 是比例与状态样式的紧凑样例（其中内联 token 块与 `tokens.css` 保持一致）。
3. `preview/*.html` 覆盖 colors / typography / spacing / buttons / inputs / app 六个视角。
4. 当某个 token 是从来源项目直接提取的，**先保留它的语义角色**，再考虑是否引入新值。
