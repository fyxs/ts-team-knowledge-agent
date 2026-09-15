# 后端与 CLI 待办路线图

> 记录后端与 CLI 的实施顺序。完成一项后同步更新状态、测试证据与相关设计文档。

## 已完成

### 基础

- [x] 项目独立 Python 运行环境（`.venv`）
- [x] CLI 包结构（命令名 `ts-team-kb`）
- [x] 配置读写（`ts-kb.json`，含模型 / 扫描 / 排除清单等配置项）
- [x] 源目录递归扫描与 SHA-256 登记
- [x] SQLite `sources` / `conversions` 状态记录

### 转换闭环

- [x] 格式路由：PDF / DOCX / PPTX / XLSX → MinerU；TXT → 编码转换；MD → 原字节复制
- [x] Excel 工作表拆分与大表 5000 行分片
- [x] 输出结构收敛：`<文档名>/<文档名>.md + images/`
- [x] 增量判断：新增 / 变更 / 输出缺失 / 上次失败，并记录 `reason`
- [x] 单文件失败记录并继续；遗留 `processing` 超时回收为可重试
- [x] 同一工作目录单实例锁（`run_lock`）
- [x] MinerU 单文件超时

### 质量与安全

- [x] Markdown 质量门禁（空内容 / 乱码 / 无效 UTF-8 / 过短 / 缺标题）
- [x] 凭据扫描门禁（命中即隔离、标记 `blocked_secret`、阻断同步）
- [x] 来源登记 / 知识条目 / 审查记录（JSONL）导出
- [x] 源状态与转换状态同步，并支持历史回填

### 搜索与 Agent

- [x] SQLite FTS5 索引（FTS 优先 + 中文子串兜底）
- [x] 知识库工具：search / read / list / status
- [x] 系统提示词 v1 + 四个核心技能（渐进式加载）
- [x] Agent 循环：工具调用、引用收集、步数上限、检索优先提醒
- [x] 双 provider（OpenAI 兼容 / Anthropic）与密钥分离存储

### 运行与运维

- [x] `run-once` / `--sync` / `--if-due`（按扫描间隔判断是否执行）
- [x] 每轮运行报告 `logs/runs.jsonl`
- [x] Git 同步：提交、拉取、rebase、推送、冲突与凭据阻断
- [x] `serve`：单端口托管 API 与前端产物 + 启动前置检查
- [x] API：聊天（含 SSE 流式）、配置读写、手动扫描、拉取 / 推送

## 待办

- [ ] 排除清单在设置面板可视化编辑
- [ ] 知识库质量巡检：批量真实问题的引用准确率抽查
- [ ] 多会话与历史记录（引入路由，前端为主）
- [ ] 语义检索评估（当前为 FTS + 子串）

## 相关文档

- 架构与事件协议：`docs/architecture-v1.md`
- 一期设计要点：`docs/design-v1.md`
- 前端技术栈：`docs/frontend-stack.md`
- 本地安装与启动：`docs/local-install-and-serve.md`
- 运行记录语义：`docs/logging-v1.md`
