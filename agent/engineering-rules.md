# Agent 工程规则

## 项目边界

- 本仓库是 CLI + 本地 Web 应用源码仓库。
- 团队共享知识内容属于 `ts-team-knowledge-base`，不复制进本仓库。
- 原始工作素材、SQLite、运行日志、本机配置、Token、密码和 Cookie 不提交 Git。

## 结构约束

```text
frontend/   React + TypeScript + Vite 前端（构建产物 frontend/dist）
backend/    Python 后端；唯一包为 backend/ts_knowledge_agent/
docs/       设计、协议、决策和运行文档
scripts/    开发、验证和运维辅助脚本
tests/      自动化测试
agent/      Agent 项目规范
```

后端分层保持：

```text
api / cli → services → adapters / repositories
```

CLI、Web 和调度器不得各自实现扫描、转换、索引或 Git 同步逻辑。

## 技术边界

- 前端统一使用 React 18 + TypeScript + Vite；不引入 Vue、Next.js 或其它框架。
- **不引入聊天 UI 组件库**。当前对话界面是自建组件（`frontend/src/components/`），
  不要重新引入 `@assistant-ui/*` 或 `@ag-ui/*`（历史上声明过但从未使用，已移除）。
- 设计体系：`design/README.md` 是视觉唯一来源，改动界面前必读；标准 token 定义在 `design/tokens.css`
- 样式只使用设计体系 token（`frontend/src/tokens.css`）；应用样式不得硬编码颜色、间距、圆角。
  需要新视觉值时，先在 tokens.css 增加 token，再在组件里引用。
- Markdown 渲染统一走 `components/MarkdownView.tsx`，不要在别处另起渲染实现。
- 后端使用 FastAPI；本地状态与全文索引使用 SQLite/FTS5。
- MinerU 运行在**独立环境**，通过配置项 `mineru_python` 指定解释器；
  不要把 PyTorch / MinerU 装进应用运行环境。
- 模型接入支持 OpenAI 兼容与 Anthropic 两种 provider，由配置选择；
  密钥只存本机 `secrets/model.key`，不写入配置、日志或仓库。
- Git 远端知识仓固定为 `git@github.com:fyxs/ts-team-knowledge-base.git`（当前不做多仓切换）。

## 前端规则（改动前必读）

```text
技术栈定稿与依赖纪律    docs/frontend-stack.md
设计体系来源            OpenDesign 从参考项目提取的 tokens（已落入 src/tokens.css）
```

- 分层固定为：`api/`（接口客户端）→ `hooks/`（状态机）→ `components/`（展示）→ `App.tsx`（组装）。
  新功能优先新增模块，不要把逻辑堆进 `main.tsx` 或既有组件。
- 新增依赖必须登记到 `docs/frontend-stack.md` 并说明用途；不得保留未使用依赖。
- 路由：`react-router-dom` 已声明为路由方案，仅在确实需要多页面时启用。
- 每次前端改动必须执行：

```bash
cd frontend && pnpm typecheck && pnpm test && pnpm build
```

- 组件要有对应测试（`src/app.test.tsx` 或同目录 `*.test.tsx`），
  测试用 vitest + jsdom，不要依赖真实网络与真实模型。

## 配置边界

- 运行配置集中在 `<工作目录>/ts-kb.json`，由 `Settings` 读写；新增配置项必须同时更新
   `from_file` / `write_file` 与测试。
- 现有配置项语义：`excluded_source_paths`（排除的源相对路径，命中则标记 ignored 不转换）、
  `scan_interval_minutes`（扫描间隔，下限 5）、`sync_on_schedule`（定时轮次是否推送）。
- 配置项要在 CLI（`ts-team-kb config`）或 API (`/api/v1/config`) 中可达，不要只藏在代码里。

## 环境注意事项（本机 DLP）

本机装有 E-SafeNet 透明加解密：

- `git`、`python`、`node` 读写得到明文；PowerShell 的 .NET 文件 API 可能读到密文。
- 用 PowerShell 读字节会把正常文件误判为「损坏」；用 PowerShell 写文件可能被回滚。
- 需要读取或修改仓库内文本文件时，用 `git show` 或 Python/Node 读写，并回读校验内容。
- 若某文件被 DLP 独占锁定（读 "Permission denied"、`git` 报 `unable to unlink`），
  先确认是否被编辑器打开；不要强行删除或覆盖。

## 验证与提交

- 改代码后至少执行：后端 `pytest`、`compileall`；前端 `typecheck` / `test` / `build`；
  `git diff --check`。
- 验证失败必须如实报告，不得以部分成功替代完整成功。
- 分支：`main` 为稳定分支；日常改动在 `dev`，验证通过后再合并。
- 未经明确授权不执行 push；执行 push 后回读远程分支 SHA。

## MinerU 环境制备（setup-mineru）

- **引导解释器优先用系统解释器（`py -3`），其次 uv**：实测某些机器的 uv 托管 Python 目录
  （`%APPDATA%\uv\python\...`）会被安全软件改成不可访问的重解析点，`uv venv` 直接失败
  （WinError 448）；系统解释器不依赖下载，最稳。
- **用 uv 时把托管 Python 重定位**：`UV_PYTHON_INSTALL_DIR` 指向我们自己的目录，
  不要用默认落点，否则同样的重解析点问题会在成员机上复现。
- **报错要可读**：把每个失败命令与关键 stderr 一起抛出，并提示「若提示重解析点/不可访问，
  说明解释器目录被安全软件接管，请用 --python 指向可用解释器」。
- 复用已有环境用 `--python <解释器>`；`--dry-run` 先看计划再执行。

## 免安装包（exe）打包

- **必须显式指定源码路径**：PyInstaller 的 spec 里 `pathex` 与 `datas` 要指向当前源码树
  （构建脚本注入 `TS_KB_BUILD_BACKEND` / `TS_KB_BUILD_WEB`）。默认行为会从构建环境的
  site-packages 取「已安装的旧包」，导致发布件里是陈旧代码——曾因此让 exe 缺少新命令，
  而源码与测试都是好的，极易漏判。
- **打包后必须验证发布件本身**：跑 `ts-team-kb.exe --help`，确认命令清单包含本次新增的命令；
  再确认包内 `_internal/ts_knowledge_agent/web/` 有 index.html 与 assets。
  只看「构建成功」不算通过。
- **构建脚本要能一键复现**：`scripts/build-release.py --exe --build-python <含 PyInstaller 的解释器>`
  产出 wheel 与免安装 zip；发布用 `scripts/publish-release.py`（默认 dry-run，上传后回读校验）。

## 工具产物目录约定

代码智能等开发工具会在仓库内产生索引与图谱。产物**必须放在仓库根目录下的固定位置**，
便于人工一眼分辨与审查，不得散落到临时目录或用户目录：

```text
graphify-out/<范围>/      Graphify 图谱（graph.json 及其中间文件），按扫描范围分子目录
.serena/                  Serena 项目配置与符号缓存（工具自带 .gitignore，本仓库 .gitignore 亦覆盖）
.codegraph/               CodeGraph 索引（当前版本固定写用户级 ~\.codegraph\，项目内暂不产生）
```

规则：

- 以上目录全部写入 `.gitignore`，不得提交；仓库只提交配置、脚本与文档。
- 扫描或索引时必须排除这些目录，避免把工具产物当源码重复吃进去。
- 产物可随时删除重建，删除不影响仓库内容。
- 新引入工具时，先确定并登记产物落点，再运行。
