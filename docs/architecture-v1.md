# TS Knowledge Agent：应用架构

## 定位

`ts-team-knowledge-agent` 是**本地运行**的知识生产与问答应用。它不是 `ts-team-knowledge-base` 的替代品（知识内容在那边），也不是通用执行型 Agent。

每台成员机器本地运行 CLI、后台任务、SQLite 与 Web 应用；团队知识通过 Git 共享。

## 分层

```text
React Web UI（Vite 构建产物，由后端托管）
        │  自建 SSE 事件协议
本地 FastAPI API / 服务
        ├── 扫描器        比对源目录与状态，判断新增 / 变更 / 缺失
        ├── 转换器        MinerU（独立环境）/ TXT 编码转换 / Markdown 直复制
        ├── Excel 适配器   按工作表拆分、大表分片
        ├── 质量门禁      空内容、乱码、无效 UTF-8、过短、缺标题
        ├── 凭据门禁      sk- 密钥、真实 Bearer、apiKey 字段、私钥
        ├── 索引器        SQLite + FTS5（FTS 优先，中文子串兜底）
        ├── Git 适配器    提交、拉取、rebase、推送、冲突保护
        ├── 登记器        来源登记 / 知识条目 / 审查记录（JSONL）
        └── 调度器        计划任务唤醒 + 按间隔判断是否执行
        │
Agent 运行时（提示词 + 技能 + 知识库工具 + 模型 provider）
```

## 事件协议

Web 与后端之间使用**自建 SSE 事件流**，事件类型：

```text
start        本轮开始
tool_call    模型请求调用工具（名称 + 参数）
tool_result  工具返回摘要
notice       流程提示（例如模型未检索即作答，已要求其先检索）
answer       最终回答（含引用列表与 retrieved 标记）
error        错误
```

一期不引入 AG-UI 等外部协议；若将来需要接第三方 Agent UI，在 `frontend/src/api/agent.ts` 这一层做适配即可。

## Agent 运行时

```text
系统提示词 v1   先检索再回答、必须给来源、不许编造、区分事实与推断
技能            knowledge-search / source-grounding / cross-document-analysis / document-comparison
                （渐进式加载：提示词只列名称与用途，模型按需 load_skill）
知识库工具      knowledge_search / knowledge_read / knowledge_list / knowledge_status
检索优先保障    模型未检索即作答时自动提醒一次；仍未检索则标记 retrieved=false 并提示用户
步数上限        model_max_steps（默认 8），超出返回 max_steps_exceeded
```

## 成员空间

成员空间（`members/<成员标识>/`）表示**写入归属与维护责任**，不是可见性隔离。进入共享知识仓的内容默认团队共享，检索默认覆盖全部成员空间。

## 数据边界

```text
源目录        只读
本机            配置、SQLite、日志、反馈、密钥、隔离产物
Git 知识仓      知识 Markdown、图片、登记文件
```

原始文件、SQLite、日志、本机配置和模型密钥不进入代码仓库或共享知识仓。

## 依赖边界

MinerU 运行在**独立环境**中，通过配置项 `mineru_python` 指定解释器；它不作为应用自身的依赖安装，避免把 PyTorch 等重型依赖带进普通运行环境。
