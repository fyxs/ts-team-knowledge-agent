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
        ├── 会话存储      会话与历史消息（本机 SQLite，不进共享知识仓）
        ├── 质量巡检      分层抽样 + 结构校验，产出巡检报告
        ├── 检索评测      评测集自动生成 + hit@k / MRR / 引用质量
        ├── 使用埋点      每轮问答落检索链路 trace（无关闭开关），按日汇总
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

## 会话与历史

```text
存储      <工作目录>/data/sessions.sqlite3（本机；不进共享知识仓）
表结构    sessions(id, title, created_at, updated_at)
          messages(id, session_id, kind, payload, created_at)
消息类型  user（提问）/ process（工具过程）/ answer（回答，含引用与步数）/ error
标题      首条提问自动成为标题，上限 20 字；可重命名，超长按上限截断
```

接口：

```text
GET    /api/v1/sessions                  会话列表（id、title、updatedAt 毫秒时间戳）
POST   /api/v1/sessions                  新建会话
GET    /api/v1/sessions/{id}/messages    历史消息（含引用与工具过程，可直接回放）
PATCH  /api/v1/sessions/{id}             重命名（空标题 400，超长截断）
DELETE /api/v1/sessions/{id}             删除会话及其全部消息
GET    /api/v1/sessions/search?q=&limit= 历史内容检索（返回命中片段与会话信息）
POST   /api/v1/chat、/api/v1/chat/stream  接受 session_id，落库用户消息、工具过程与回答
```

历史全文检索：

```text
索引      messages_fts（与 messages 同库；删除会话时同步清理；索引为空时按历史消息自动补建）
中文      索引侧与查询侧**对称**做二元片段展开——只做单侧会导致两字关键词召不回
片段      在原始文本上以命中词为中心截取，不把索引用的二元尾巴带进摘要
范围      用户提问与回答正文；工具过程（steps）不入索引
```

地址栏路由：

```text
参数      ?session=<会话 id>
切换/新建   pushState（浏览器后退可在会话之间回退）
程序性纠正  replaceState（分享链接指向已删除会话时回落到最近一条并改写地址栏）
```

## 引用来源阅读

回答里的引用默认是**路径字符串**（`citations: string[]`），点开看原文需要另外两条出口：

```text
GET /api/v1/knowledge/document?path=&offset=&limit=
    → { path, title, content, offset, returned_lines, total_lines, truncated }
    边界：members/ 之内、必须是 .md、只读；越界或非 md 400，文件不存在 404

GET /api/v1/knowledge/asset?path=
    → 文档内相对资源（实测是文档同级 images/ 下的图片）
    与正文同一套边界，另加后缀白名单 jpg/jpeg/png/gif/webp/svg
```

结构化引用：`/api/v1/chat`、`/api/v1/chat/stream` 的 answer 事件与会话消息 payload 在
`citations` 之外**追加** `sources`，原字段不动（CLI 与评测按字符串数组消费）：

```text
sources: [{ path, title, hits: [{ line, snippet }] }]
```

命中行号由 `locate_sources` 在**规范化之后**的全文上定位（提问分词后逐行计分，按分数取前 3 处、
再按行号升序）。没有检索词（模型只 `knowledge_read` 过）时 `hits` 为空，界面显示「已引用」，
不编造命中。

三处必须一起看约定，否则引用会跳到别的地方：

```text
坐标一致   命中行号按规范化后的全文算；document 接口也是「先整篇读、再按行切窗口」，
           不能先切窗口再规范化——含多行 HTML 表格的文档行数会变
表格        MinerU 原始 <table> 在 document 接口规范化为 GFM 管道表（实测 10/104 篇），
           索引内容与 agent 读到的内容保持原样，两边的行为可分别回归
图片        文档内相对图片重写为 asset 路由；作者本机路径（Typora 导出）与站外 http 图片
           取不到也不热链，如实标成「图片不可用」或给出外部链接
```

## 治理与自检

三类治理产物都落在共享知识仓 `governance/<成员>/` 下，随既有同步推送：

```text
巡检   ts-team-kb inspect       分层抽样 + 结构校验；区分阻断级与提示级
评测   ts-team-kb evaluate      评测集自动生成，输出 hit@k / MRR / 引用质量
埋点   logs/usage/<日期>.jsonl  每轮问答的检索链路 trace；按日汇总为 <年月>.jsonl
```

计划任务（每台成员机各跑自己的一份）：

```text
TSKnowledgeAgentScheduler    每 5 分钟敲门，应用层按 scan_interval_minutes 判断是否真跑
TSKnowledgeAgentInspection   每天 08:30，错过唤醒补跑
TSKnowledgeAgentEvaluation   每周一 09:00（安装时需带 -IncludeMaintenance）
TSKnowledgeAgentWebService   用户登录时自启（幂等守护：端口已在监听则直接退出）
```

## 成员空间

成员空间（`members/<成员标识>/`）表示**写入归属与维护责任**，不是可见性隔离。进入共享知识仓的内容默认团队共享，检索默认覆盖全部成员空间。

## 数据边界

```text
源目录        只读
本机          配置、SQLite、运行期锁目录 runtime/、日志、反馈（状态库 / 会话库）、日志、反馈、埋点、密钥、隔离产物
Git 知识仓     知识 Markdown、图片、登记文件、治理报告（governance/<成员>/）
```

原始文件、SQLite、日志、本机配置和模型密钥不进入代码仓库或共享知识仓。

## 状态库与索引

```text
位置      <知识仓>/data/state.sqlite3（在知识仓目录内，但不入 Git、不随同步上传）
表        sources       源文件登记与状态（含 quality_warned 告警态）
          conversions   转换记录（转换器标签、warning_message / error_message）
          documents     知识条目索引（标题、字节数、图片数、来源 SHA-256）
          documents_fts 全文索引（AND 优先 + OR 补齐 + bm25 排序）
会话库    <工作目录>/data/sessions.sqlite3（见「会话与历史」，本机使用痕迹）
```

## 依赖边界

MinerU 运行在**独立环境**中，通过配置项 `mineru_python` 指定解释器；它不作为应用自身的依赖安装，避免把 PyTorch 等重型依赖带进普通运行环境。

## 答案来源展示规则

来源数量由**证据强度**决定，不由「模型搜了几次」决定（此前一次提问可能带出 10 条以上来源）。

```text
证据强度 = 3×被 knowledge_read 打开过 + 2×关键词(FTS)命中 + min(命中次数, 3)
只展示强度 ≥ 最高强度 × sources_relevance_ratio 的来源，再按 sources_max_display 截断
citations 与 sources 使用同一份筛选结果（前端「来源（N）」读的是 citations）
```

配置项（写入工作目录 `ts-kb.json`）：`sources_max_display`（默认 8）、`sources_relevance_ratio`（默认 0.5）。
纯函数 `rank_sources()` 位于 `backend/ts_knowledge_agent/agent/runtime.py`，单测见 `tests/test_source_ranking.py`。
