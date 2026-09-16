# 日志与运行记录

## 结论

需要记录，但不需要独立日志平台。所有轮次、失败与同步都必须可追踪。

## 三种记录分工

| 载体 | 内容 | 是否入 Git |
| --- | --- | --- |
| `logs/runs.jsonl`（工作目录） | 每轮运行的摘要记录 | 否 |
| `state.sqlite3` | 源文件状态、转换状态与原因、索引 | 否 |
| Git 历史 | 知识内容、来源登记、审查记录 | 是 |

## 每轮运行记录

每次 `run-once` 追加一行 JSON：

```json
{"started_at": "…", "finished_at": "…", "duration_seconds": 760.6,
 "scanned": 94, "queued": 0, "batches": 0, "converted": 0, "warned": 0, "skipped": 94,
 "failed": 0, "missing": 0, "indexed": 100, "sync_status": "pushed",
 "reason_counts": {"unchanged": 85, "unsupported": 8, "excluded": 1},
 "error": null}
```

关键字段含义：

```text
reason_counts   本轮每类决策的数量：
                new_source / source_changed / output_missing / previous_failed /
                unchanged / unsupported / stale_processing_recovered
sync_status     disabled / clean / pushed / push_failed / blocked_conflict /
                blocked_secret / not_initialized
error           异常摘要（正常为 null）
```

## 状态与原因

`state.sqlite3` 中每个源文件记录：相对路径、大小、修改时间、SHA-256、状态；每次转换记录转换器与版本、输出路径、状态、错误信息与原因。

```text
源状态     discovered / converted / quality_failed / trusted?（不使用）/
           failed_retryable / blocked_secret / ignored / source_missing
           quality_warned（源侧自身质量问题：入库可用但标记告警，不计失败）
判断依据   源哈希变化 → source_changed；输出缺失 → output_missing；
           上次失败 → previous_failed；未变化 → unchanged
```

## 同步保护

以下情况不推送并留痕：远端有新提交且 rebase 冲突、命中凭据、质量门禁拦截。

## 安全

不记录文件正文、模型密钥、Token、密码、Cookie、完整提示词与响应。日志与数据库不进入团队知识仓。

## 使用埋点（usage）

每轮问答落一条 trace，用于改进检索质量。**无关闭开关**（产品决定：静悄悄采集必要数据）。

```text
位置      <工作目录>/logs/usage/<日期>.jsonl（本机，每次问答一行）
汇总      按日汇总为 <年月>.jsonl，写入共享知识仓 governance/<成员>/usage/，随既有同步推送
字段      用户提问原文 / 模型实际发出的检索词（含 mode）/ 命中路径与 rank、score /
          最终引用 / retrieved_but_unused / cited_not_retrieved / 耗时 / 错误
```

边界：记录**提问原文与检索链路**，不记录文件正文、模型密钥、Token、密码，也不保存发给模型的完整上下文与模型原始响应。
它属于使用数据，不是运行日志：运行日志回答「流程是否正常」，埋点回答「检索是否好用」。

## 巡检与评测报告

```text
巡检   logs/inspection-<时间戳>.json + inspection-latest.json（阻断级 / 提示级分开计数）
       logs/inspection-runs.jsonl 记录每次真实巡检，用于 --if-due 到期判定
评测   logs/evaluation-<时间戳>.json + evaluation-latest.json
       （retrieval 自然语言 / 关键词两套指标、citations 引用质量）
上推   两份报告同步到 governance/<成员>/{inspection,evaluation}/
```

报告是**产物**，日志是**过程**：报告进共享仓供团队查看，运行日志留在本机。

## 锁恢复记录

转换运行同一工作目录只允许一次（`runtime/run.lock`）。锁文件带 pid、主机名与创建时间，
接管规则：**持有进程已不存在 → 立即接管**；锁龄超过 2 小时 → 接管兜底；两者都不满足才阻止本次运行。
每次接管写一条 `logs/lock-recoveries.jsonl`（时间、原因、原持有者 pid、接管者 pid），便于事后核对。

## 运行日志编码

运行日志统一 UTF-8。PowerShell 5.1 的 `*>>` 重定向会写成 UTF-16（人和其他工具读成乱码），
因此 `scripts/run-*.ps1` 一律用 `cmd.exe /c` 原始字节追加重定向。

## 运行健康（巡检可见）

运行失败过去只有记录、没有对外信号（计划任务返回码恒 0、巡检不看运行）。现在两处都补上：

- 运行记录新增 `result` 字段：`ok` / `locked`（被其它运行占用）/ `failed`
- 锁冲突由 CLI 以**独立退出码 3** 结束（输出 `skipped=locked ...`），计划任务历史直接可见
- 巡检报告新增 `run_health` 段：最近 N 轮的 ok/locked/failed 计数、连续失败数、
  最近结果与错误摘要、锁接管次数；**连续失败 ≥ 3 轮计为阻断级**（巡检退出码非 0）
- `scripts/run-*.ps1` 一律以 CLI 的退出码结束，不再恒为 0

## 不做

一期不接入 ELK、Loki 或云日志平台；不把运行日志提交到知识仓，也不以日志替代来源登记、审查记录和 Git 历史。

## 留存规则

以实测增长为准（2026-09-15），分两类：系统产物超限即清理，用户数据不自动删。

```text
对象                        现状实测                  一年估算   规则
data/sessions.sqlite3       100KB / 2 会话 6 消息     约 300MB   **不自动清理**（用户数据）
                            （单轮正文约 3.9KB）
logs/usage/<日期>.jsonl     10 条 / 38KB（2.6KB/条）  约 95MB    **长期保留**
logs/evaluation-*.json      18 份 / 642KB             约 1.8MB   本机保留最近 30 份，超出删最旧
logs/inspection-*.json      8 份 / 90KB               约 4MB     本机保留最近 30 份，超出删最旧
logs/runs.jsonl             71 行 / 26KB              约 7MB     保留 12 个月，之后按月归档
logs/*.log                  api 37KB · scheduled 37KB 线性增长   单文件超 10MB 轮转、保留 2 份
知识仓 .git                 12.57MB / 63 提交         —          定期 gc，不做历史压缩
知识仓 governance/          巡检 8 份 · 评测 4 份     —          代码已裁剪（评测 keep=30），无需额外规则
```

四条原则：

```text
1. 系统产物（报告、日志、runs）超限即清理，**一律删最旧的**（用户 2026-09-15 确认）
2. 用户数据（会话历史）**不纳入自动清理**（用户 2026-09-15 明确）：由用户自行决定，已提供单条删除入口；清理命令不得触碰 sessions.sqlite3
3. 使用埋点长期保留（用户 2026-09-15 明确）：它是检索优化唯一的原料；体积过大时压缩，不删除
4. 清理必须可审计：每次清理写 logs/prune-runs.jsonl（删了什么、依据哪个上限、释放多少字节）
5. 执行入口：`ts-team-kb prune`（默认只出计划，`--apply` 才真正删除；上限参数 --keep-inspection / --keep-evaluation / --runs-days / --log-max-mb / --log-keep）
```

治理目录的保留上限已由代码保证：`publish_inspection_report` 走 `prune_inspection_reports`，
`publish_evaluation_report` 默认 `keep=30`，因此共享仓不会无限增长。
