# 路线图

## 已完成

### 转换与沉淀链路

```text
格式路由：PDF / DOCX / PPTX / XLSX → MinerU；TXT → 编码转换；MD → 直复制；其它忽略
Excel 工作表拆分与大表 5000 行分片
输出结构收敛：<文档名>/<文档名>.md + images/
质量门禁：空内容 / 乱码 / 无效 UTF-8 / 过短 / 缺标题
凭据门禁：命中即隔离、标记 blocked_secret、阻断同步
失败可重试：failed_retryable / quality_failed / blocked_secret
可靠性：同工作目录单实例锁、单文件超时、遗留 processing 回收
增量：新增 / 变更 / 输出缺失 / 上次失败的判定与原因统计
状态一致性：源状态与转换状态同步，并支持历史回填
运行记录：每轮 runs.jsonl
来源登记与审查记录：sources / knowledge / reviews JSONL
```

### 共享知识仓

```text
建仓并对接远程、首次推送、拉取与推送（含 rebase 与冲突保护）
敏感信息扫描后脱敏再入库
```

### Agent 与问答

```text
知识库工具：search / read / list / status（FTS 优先 + 中文子串兜底）
系统提示词 v1 + 四个核心技能（渐进式加载）
Agent 循环：工具调用、引用收集、步数上限、检索优先强制与 retrieved 标记
模型接入：OpenAI 兼容 + Anthropic 双 provider，配置与密钥分离
```

### Web 应用

```text
对话界面：Markdown 渲染、检索过程折叠、来源列表、可中断
设置面板：模型 / 扫描 / 共享知识仓三区，弹窗三段式布局
主题：深色（默认）/ 浅色
视觉：设计体系 token 化、宽度阶梯、内部滚动、细滚动条
会话与历史：本机 SQLite 存储、列表分组与搜索、切换回看（含检索引用与工具过程）
```

### 运行与部署

```text
ts-team-kb serve：单端口托管 API 与前端产物
启动前置检查：源目录 / 知识仓 / MinerU / 模型 / 前端产物
计划任务定时唤醒 + 按间隔执行（--if-due）
Web 手动触发扫描、拉取、推送
本地安装与启动文档
```

## 进行中 / 待办

```text
知识库质量巡检：用一批真实问题抽查引用准确率，据此调检索与提示词
多会话与历史记录：接口与存储已完成（会话列表 / 新建 / 历史消息三个接口，本机 SQLite 存储，
  前端已接真实数据并支持切换回看）；剩余：会话重命名与删除、历史全文检索、URL 路由
dev 分支合并到 main 的节奏（当前 main 落后 33+ 提交）
```

## 明确不做（一期）

```text
模型自动提炼知识
部署到云服务
账号与权限体系（权限边界交给 Git 仓库权限）
旧版 Office 格式（.ppt / .doc / .xls）支持
```

## 实施记录

- 后端待办与执行细节：`agent/backend-cli-tasks.md`
- 编码规范：`agent/engineering-rules.md`
- 工作流程：`agent/workflow.md`


## 巡检与评测的执行方式

```text
质量巡检（结构层）  维护机每日 08:30 自动执行，报告写入 governance/<成员>/inspection/
质量评测（内容层）  维护机每周一 09:00 自动执行，静默采集已沉淀数据并评测：
                    ts-team-kb evaluate --mode both --publish --if-due --interval-minutes 10080
                    报告写入 governance/<成员>/evaluation/（保留最近 30 份）
用户侧安装          定时扫描 + 每日巡检 + 本地服务，三个任务；
                    每周评测属于维护需要，不施加到成员机器
                    （维护机用 scripts/install-windows-tasks.ps1 -IncludeMaintenance 启用）
评测集              evaluation/knowledge-questions.json
                    每例含 question / expected_paths / keywords，按索引真实路径维护
```

评测与巡检都按 --if-due 判定到期，机器休眠或关机错过计划时间时，
任务会用 StartWhenAvailable 在恢复后补跑一次，且不会重复执行。
