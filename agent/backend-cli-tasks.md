# 后端与 CLI 待办路线图

> 本文记录 `ts-knowledge-agent` 后端与 CLI 的实施顺序。每完成一项，应同步更新状态、测试证据和相关设计文档。

## 当前状态

- [x] 项目独立 Python 运行环境（`.venv`）
- [x] 项目依赖声明 MinerU
- [x] CLI 包结构
- [x] 配置基础读取
- [x] 本地源目录递归扫描
- [x] SHA-256 文件登记
- [x] SQLite `sources` 状态记录
- [x] MinerU 单文件转换
- [x] `ts-kb scan` 基础命令
- [x] `ts-kb convert` 基础命令
- [x] `ts-kb status` 基础命令
- [x] 最小转换端到端验证

## 第一阶段：转换闭环

- [ ] 增加转换状态表，记录源文件哈希、输出路径、转换器版本、状态、错误和时间。
- [x] 扫描新增或变更文件时只处理必要文件。
- [x] 扫描完成后先建立完整处理文件清单，再按批次执行转换。
- [x] 支持 `--batch-size` 控制单批处理数量。
- [ ] 同一源文件、同一 SHA-256 时跳过重复转换。
- [ ] 源文件变化后生成新的转换结果，不覆盖源文件。
- [ ] 单个文件转换失败时记录失败并继续处理其他文件。
- [ ] `status` 展示扫描和转换状态。

## 第二阶段：SQLite FTS5 搜索

- [ ] 建立文档元数据表。
- [ ] 建立 SQLite FTS5 全文索引。
- [ ] 转换结果写入索引，支持增量更新。
- [ ] 源文件或转换结果缺失时更新索引状态。
- [ ] 实现 `ts-kb search "关键词"`。
- [ ] 返回路径、标题、摘要、个人知识仓库中的知识空间和来源引用。
- [ ] 为中文、路径、空查询和无结果补充测试。

## 第三阶段：CLI 初始化与本地运行目录

- [x] 实现 `ts-kb init`，强制指定 working_directory、personal_workspace 和 shared_source_directory。
- [ ] 配置 `personal_personal-workspace` 和本地源目录。
- [x] 创建 working_directory 下的配置、data、logs、runtime 和共享知识仓目录。
- [x] 根据 shared_knowledge_repository_url 拉取共享知识仓到 working_directory；拉取失败则初始化失败。
- [x] 检查 Python、MinerU、Git 和 SQLite 运行条件。
- [ ] 不把本地配置、SQLite、日志和原始素材写入 Git。

## 第四阶段：知识候选沉淀

- [ ] 将转换材料写入 `members/<personal_personal-workspace>/`。
- [ ] 生成带 YAML frontmatter 的候选知识 Markdown。
- [ ] 写入 `members/<personal_personal-workspace>/knowledge/candidate/`。
- [ ] 建立知识与源文件、转换结果的可追溯关系。
- [ ] 明确 `candidate`、`verified`、`contested`、`deprecated` 状态。
- [ ] 第一版不把转换结果直接视为已验证知识。
- [ ] 后续再接入模型进行摘要、主题和知识类型提取。

## 第五阶段：Git 同步

- [ ] 实现 Git 适配器和 `ts-kb sync`。
- [ ] 检查工作区、拉取远程更新并处理 fast-forward。
- [ ] 只写入当前个人知识仓库中的知识空间。
- [ ] 提交前检查凭据、日志、数据库和临时文件。
- [ ] 处理冲突、push 失败和远程变化。
- [ ] 推送后回读远程 SHA。
- [ ] 异常时暂停自动推送，不强行覆盖或删除知识。

## 第六阶段：源文件变化与删除检测

- [x] 识别 unchanged、changed、source_missing 和 failed 状态。
- [ ] 用户删除源文件后保留登记并标记 `source_missing`。
- [ ] 不自动删除已确认知识或其他成员内容。
- [ ] 明确缺失源文件对检索和引用状态的影响。

## 第七阶段：一次性任务与每小时调度

- [x] 实现 `ts-kb run-once`，串联扫描、转换、索引和同步。
- [ ] 为每个阶段提供清晰的成功、失败和跳过统计。
- [x] 接入 Windows 任务计划程序。
- [x] 默认每小时执行一次，并支持精确到分钟的配置。
- [ ] 失败、冲突或异常变更时暂停推送并保留诊断信息。

## 第八阶段：FastAPI 知识服务

- [ ] 保持 API 层只做协议适配，不复制业务逻辑。
- [ ] 增加 sources、documents、search 和 status 只读接口。
- [ ] API 与 CLI 共用 services、repositories 和 adapters。
- [ ] 接入 Web UI 前先完成服务层测试。
- [ ] 后续再实现 AG-UI SSE 和问答窗口。

## 工程约束

- 依赖方向固定为：`api / cli / workers → services → adapters / repositories`。
- 原始文件只读，Agent 不移动、重命名、覆盖或删除源文件。
- `ts-knowledge-base` 只存共享知识，不放应用代码、SQLite 或运行日志。
- 先完成垂直切片，再抽象公共模块；不提前创建无实现的复杂目录。
- 每项任务必须有测试或可复现验证证据。
- 完成任务后更新本文和 `docs/roadmap.md`。