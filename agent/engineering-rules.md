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

本机装有 E-SafeNet 透明加解密。**同一个仓库里存在两类文件**，处置方式不同。

### 加密外壳文件

判定特征（命中其一即按此类处理）：

- 原始字节头为 `62 14 23 65`（`b\x14#e`，E-SafeNet 外壳），文件内含 `E-SafeNet` / `LOCK` 标记；
- Python 读取报 `PermissionError [Errno 13]`，Node 报 `EPERM`（不是 ACL 问题：可访问文件的 ACL 与它完全一致）；
- 该文件往往同时带 git `skip-worktree` / `assume-unchanged` 标记（`git ls-files -v <path>` 首字母小写）。

处置规则（硬规则）：

1. **Agent 侧只读**：不要用 PowerShell、Node 或任何其它进程变通写入。
   PowerShell 的 .NET 文件 API 读到的是**密文**，按文本解码后回写，等于用乱码覆盖原文。
2. 需要内容时用 `git show HEAD:<path>`（走对象库，拿到的是明文）；不要读工作区文件指望拿到明文。
3. **严禁"读到什么就回写什么"**。写入前必须能证明读到的是明文（例如能解析出预期标题/结构）；
   写入后除哈希比对外还必须校验明文特征。只比对哈希会得出「一致」的错误结论——
   两边可能是同一份密文。
4. 判断是否被改动，用对象比对而不是 `git status`：
   `git hash-object <path>` 与 `git rev-parse HEAD:<path>` 不一致，即工作区文件已被改动。
   （skip-worktree 文件在 `git status` 里永远是干净的，改动不会显示。）
5. 需要修改这类文件时，交给**交互式白名单工具**（编辑器、资源管理器），或由用户在本地执行。
6. 若已误写：仓库版本完好，用 `git show HEAD:<path>` 取出原文，交用户用编辑器覆盖保存。

### 确需更新 skip-worktree 文件时的正确步骤

这类文件常因 DLP 加壳而被排除在正常跟踪之外（`git ls-files -v` 显示 `S`）。
确实需要更新它的内容时：

1. 先确认文件**当前可以正常读写**（DLP 锁已解除）。若仍被加壳，只能交交互式白名单工具处理，
   不要用脚本变通写入。
2. `git update-index --no-skip-worktree <path>` —— 先摘掉标记，否则 git 看不到任何改动
   （摘掉后 `git status` 会立刻显示 `M`）。
3. 正常 `git add` 与 `git commit`。
4. 提交完成后**把标记按原样放回**：`git update-index --skip-worktree <path>`
   —— 保持环境原有的处置，不要顺手取消。
5. 复核：`git hash-object <path>` 与 `git rev-parse HEAD:<path>` 应一致，`git ls-files -v` 应回到 `S`。

不要把 `--no-skip-worktree` 长期放着：标记的存在有环境原因，取消后 git 每次都会去读被加壳的文件。

### 普通文件

- `git show`、Python、Node 读写得到明文，正常处理，读写后回读校验。
- 不要用 PowerShell 文本管道往返读写（会把中文与编码搞坏）。
- 编写 PowerShell 脚本只用 ASCII：中文注释会让 5.1 按 ANSI 解析，行为异常。
- 若文件被独占锁定（`git` 报 `unable to unlink`），先确认是否被编辑器打开，不要强行删除或覆盖。

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

代码智能等开发工具会在仓库内产生索引与图谱。产物**统一收在一个目录下**，便于人工一眼分辨与审查：

```text
codeintel/graphify/<范围>/graphify-out/   Graphify 图谱与增量缓存
codeintel/serena/                         Serena 项目配置与符号缓存
codeintel/README.md                       落点说明与重建方式
```

规则：

- `codeintel/` 整体写入 `.gitignore`，**不得提交**；仓库只提交配置、脚本与文档。
- 扫描/索引时必须排除 `codeintel/`，避免把工具产物当源码重复吃进去。
- 产物可随时删除重建；删除不影响仓库内容。
- 新引入工具时先确定落点并登记在本节，再运行。
- Graphify 的 `graphify-out/` 是工具固定追加的规范数据目录（`extract --out <DIR>` 写 `<DIR>/graphify-out/`，
  读取命令默认取 `graphify-out/graph.json`）：落点含这一层，不要手工上移。
- **例外（工具限制，需登记而非忽略）**：
  - CodeGraph 索引固定在用户级 `~\.codegraph\`，无数据目录选项，项目内不会出现其产物。
  - Serena 把 `.serena/` 写死在项目根用于项目发现；本项目用目录联接
    （`mklink /J .serena codeintel\serena`）让权威数据落在 `codeintel/serena/`。
    重建 Serena 项目后需重新建立该联接。
- Serena 项目路径必须传**仓库根**（`serena project create <repo>`）：传子目录会让 `.serena/` 嵌进子目录。

## Windows 计划任务：不要用 VBS 等待模式

失败教训（2026-09-16）：为让任务历史能看到业务退出码，把 `run-*-hidden.vbs` 里的
`shell.Run "<cmd>", 0, False` 改成 `... , 0, True`（等待并回传）。结果**下一次敲门就挂死**：
wscript 常驻、无子进程、无日志，任务停在 Running，后续触发全被跳过 —— 调度静默停摆。

规则：
- 作业类任务（scheduler / inspection / evaluation）注册 **wscript.exe + VBS 隐藏启动器**（`... , 0, False` 不等待）；
  脚本末尾仍以 CLI 退出码结束（`exit $LASTEXITCODE`），但退出码不作为唯一信号。
  直连 powershell.exe 在 Interactive 登录类型下**每次触发都会闪一个控制台窗口**（实测每 5 分钟一次），不可接受。
- VBS 包装器只用于**常驻**进程（Web 服务）且保持 `False`（不等待）。
- 常驻/长任务禁止依赖"任务历史里的退出码"作为唯一信号；业务结果要落到**运行记录与报告**里。
- 实测结论：本机任务为 Interactive 登录类型时，`LastTaskResult` **不反映动作退出码**
  （三个显式 `exit 3` 的探针任务均报 0），Task Scheduler 事件日志亦为关闭状态。
  因此"系统视角"不可靠，可见性以业务记录（`logs/runs.jsonl` 的 `result` 字段、
  巡检报告的 `run_health` 段）为准。

## 优化必须整体性（2026-09-17 用户要求）

**不要顾此失彼**：修一个问题的同时不得让别处退化，改完必须给出整体证据。

```text
1. 先取基线        改动前跑一次现有评测（如 ts-team-kb evaluate），记录指标
2. 再改            一次只改一个变量，改动范围写清楚
3. 全量对比        改动后重跑同一评测：任一指标下降即视为未完成，退回或调整
4. 补回归用例      把这次暴露的具体例子加进评测集（如按文档名提问的变体），防止改回去
5. 检查副作用      除了主指标，还要看副指标（如引用的词支撑、来源数量、片段是否为空）
6. 留证据          前后指标、回归用例、副作用检查结果一并写进提交信息
```

典型反面例子：为提升召回把"路径命中"提前，结果召回的条目没有片段、引用失去词支撑 ——
主指标变好、副指标变坏，属于未完成。

## 已知环境注意事项

```text
公司 DLP（E-SafeNet）会对部分文件做透明加解密：
  · git、node、python 读取得到明文
  · PowerShell 的 .NET 文件 API 可能读到密文
排查文件内容时优先用 git show 或 Python/Node 读取，不要用 PowerShell 直接读字节，
否则会把正常文件误判为"损坏"。
```

### 典型报错

```text
PermissionError: [Errno 13] Permission denied             读取被拒
error: unable to unlink old '<file>': Invalid argument     git 无法替换该文件
文件开头出现 E-SafeNet / LOCK 的二进制内容                 读到的是密文而不是内容
```

### 文件被锁住时

```text
1. 关掉可能打开该文件的程序（编辑器、预览工具）——多数情况即时释放
2. 仍锁定：注销再登录
3. 仍锁定：重启机器
4. 都无效：找 IT。不要自行卸载或禁用，这是公司合规管控
```

### Git 侧临时手段

某个被锁文件阻塞提交时，可临时跳过它的本地变更（仓库内已提交的内容仍是正确明文）：

```bash
git update-index --skip-worktree <path>     # 临时跳过本地变更
git update-index --no-skip-worktree <path>  # 恢复正常跟踪
git checkout -- <path>                      # 用仓库版本覆盖本地
```

`git ls-files -v <path>` 输出以 `S` 开头即表示当前处于跳过状态。

## Windows 控制台编码：输出必须能容忍不可表示字符（2026-09-17 实测）

同一天踩了两次，都是"代码逻辑正确、跑起来直接崩"：

```text
① 脚本侧：看门狗脚本打印 ⚠️ 前缀 → UnicodeEncodeError: 'gbk' codec can't encode '\u26a0'
② CLI 侧：包内 exe 跑 search → UnicodeEncodeError: 'gbk' codec can't encode '\u274c'
   （--help / status 正常，因为它们不打印该字符 → 极易漏测）
```

规则：

```text
1. 面向 Windows 控制台的输出（CLI、计划任务脚本、管道子进程）先把错误策略降级：
     sys.stdout.reconfigure(errors="replace")   # 保持编码不动
   不要把编码改成 UTF-8 —— 那会让 GBK 控制台里的中文变乱码。
2. 少用 emoji 做状态标记；用 [!] / [ok] 这类 ASCII 标记，跨编码都安全。
3. 验证要覆盖"会打印特殊字符的那条路径"：只测 --help 会漏掉真正的崩溃点。
4. 子进程互相读取输出时按本机编码解码（GBK 优先），否则中文比对必然失败 ——
   这类"看似功能坏、其实是自己解码错"的假故障，今天也踩过一次。
```
