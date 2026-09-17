# 设计体系（Design System）

本目录是本项目的**视觉与交互设计唯一来源**。任何涉及界面样式、色彩、字号、间距、圆角、阴影、动效的改动，都必须先读这里，并只使用这里定义的 token。

## 来源

本设计体系由 OpenDesign 从参考项目 `chatbot`（Vercel 系 Next.js AI Chatbot，Apache-2.0）提取并人工校准：

```text
提取产物：C:\Users\86795\AppData\Roaming\Open Design\namespaces\release-stable-win\data\design-systems\chatbot
已复制：DESIGN.md、USAGE.md、tokens.css、design-tokens.json、tailwind-v4.css、
        components.manifest.json、components.html、manifest.json、preview/
未复制：source/（参考项目源码片段，避免第三方代码进入本仓库）、revisions/（提取历史快照）
```

## 阅读顺序

```text
1. DESIGN.md                  产品语境、视觉原则、token 语义与取值依据（最先读）
2. tokens.css                 标准 token 定义（本目录是定义源）
3. preview/*.html             颜色、字体、间距、按钮、输入框的视觉预览
4. components.manifest.json   可参考的组件模式清单
5. design-tokens.json         结构化 token（机器可读，供工具使用）
```

## 与前端的关系

```text
design/tokens.css             标准 token 定义源（来自设计体系，命名不得改动）
frontend/src/tokens.css       运行时副本 = 标准 token + 本项目扩展 token
frontend/src/styles.css       应用样式，只允许引用 token
```

- 标准 token 的**名称属于契约**，不得重命名。
- 需要新的视觉值时：先在 `frontend/src/tokens.css` 的「应用扩展 token」区块新增并注明用途，
  再登记到 `docs/frontend-stack.md` 的扩展表。
- `tests/test_design_tokens.py` 会校验标准 token 没有被漏掉或改名。

## 硬规则（对 Agent）

```text
1. 不硬编码颜色、圆角、间距、字号——一律用 var(--token)。
2. 不改标准 token 名称；扩展 token 必须标注「应用扩展」并登记。
3. 调色板是刻意单色的（oklch chroma = 0）：不要引入品牌色、渐变或高饱和强调色。
4. 层级靠边框与留白表达，阴影只用 --elev-* 三档，不要自定义阴影。
5. 焦点态统一用 --focus-ring；不要另造高亮样式。
6. 动效只用 --motion-fast / --motion-base 与 --ease-standard，不引入动画库。
7. 主题写法：浅色是基线（写在裸 :root，design/tokens.css 即此形态），深色由 :root[data-theme="dark"] 覆盖
   （在 frontend/src/tokens.css）；缺省深色由 frontend/index.html 引导脚本与 useTheme 写入 data-theme 得到。
8. 新增界面结构前，先看 components.manifest.json 与 preview/，沿用既有模式而不是另起一套。
9. 不引入聊天 UI 组件库或 CSS 框架；样式方案见 docs/frontend-stack.md。
10. 不把第三方源码片段直接粘贴进仓库的样式或组件。
```

## 改动自检

```text
[ ] 是否只使用了 token，没有硬编码视觉值
[ ] 新增 token 是否登记到 docs/frontend-stack.md
[ ] 深色与浅色下是否都正常
[ ] 是否跑过前端验证：pnpm typecheck && pnpm test && pnpm build
```
