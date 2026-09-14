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
 "scanned": 93, "queued": 4, "batches": 1, "converted": 3, "skipped": 89,
 "failed": 1, "missing": 0, "indexed": 100, "sync_status": "pushed",
 "reason_counts": {"unchanged": 81, "unsupported": 8, "previous_failed": 1},
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
判断依据   源哈希变化 → source_changed；输出缺失 → output_missing；
           上次失败 → previous_failed；未变化 → unchanged
```

## 同步保护

以下情况不推送并留痕：远端有新提交且 rebase 冲突、命中凭据、质量门禁拦截。

## 安全

不记录文件正文、模型密钥、Token、密码、Cookie、完整提示词与响应。日志与数据库不进入团队知识仓。

## 不做

一期不接入 ELK、Loki 或云日志平台；不把运行日志提交到知识仓，也不以日志替代来源登记、审查记录和 Git 历史。
