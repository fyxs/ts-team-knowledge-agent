"""使用埋点与汇总：记录问答链路，用于改进检索与提示词。

设计要点：
- 每次问答落一条 trace（本地 logs/usage/<日期>.jsonl），记录
  用户原话、模型实际发出的检索词、命中路径、最终引用与错误。
- 每日滚动成一条汇总，写入治理目录 governance/<成员>/usage/<年月>.jsonl，
  随既有同步推送到共享仓；不提供关闭开关。
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ts_knowledge_agent.services.member_space import member_governance_directory

USAGE_DIRECTORY = "usage"
LOCAL_USAGE_DIRECTORY = "usage"
KEEP_MONTHS = 12


def _local_dir(working_directory: Path) -> Path:
    return Path(working_directory) / "logs" / LOCAL_USAGE_DIRECTORY


def _usage_path(working_directory: Path, moment: datetime | None = None) -> Path:
    stamp = (moment or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    return _local_dir(working_directory) / f"{stamp}.jsonl"


@dataclass
class TraceCollector:
    """作为 on_event 回调收集一条完整问答链路。"""

    question: str = ""
    prompt_version: str = ""
    steps: list[dict] | None = None
    answer: str = ""
    citations: list[str] | None = None
    error: str | None = None
    retrieved: bool = False

    def __post_init__(self) -> None:
        if self.steps is None:
            self.steps = []
        if self.citations is None:
            self.citations = []

    def __call__(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "start":
            self.question = event.get("question") or self.question
        elif kind == "tool_call":
            self.steps.append({
                "step": event.get("step"),
                "tool": event.get("name"),
                "arguments": event.get("arguments") or {},
                "paths": [],
            })
        elif kind == "tool_result":
            paths = list(event.get("paths") or [])
            for entry in reversed(self.steps):
                if entry.get("tool") == event.get("name") and not entry.get("paths"):
                    entry["paths"] = paths
                    break
        elif kind == "answer":
            self.answer = event.get("content") or ""
            self.citations = list(event.get("citations") or [])
            self.retrieved = bool(event.get("retrieved"))
            self.prompt_version = event.get("prompt_version") or self.prompt_version
        elif kind == "error":
            self.error = event.get("error")

    def to_record(self, member: str, surface: str) -> dict:
        retrieved_paths: list[str] = []
        zero_hit: list[dict] = []
        for entry in self.steps:
            tool = str(entry.get("tool") or "")
            if not tool.endswith("search"):
                continue
            paths = entry.get("paths") or []
            if not paths:
                zero_hit.append({"query": entry.get("arguments", {}).get("query", ""), "step": entry.get("step")})
            for path in paths:
                if path not in retrieved_paths:
                    retrieved_paths.append(path)
        citations = list(dict.fromkeys(self.citations or []))
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "member": member,
            "surface": surface,
            "prompt_version": self.prompt_version,
            "question": self.question,
            "steps": self.steps,
            "retrieved_paths": retrieved_paths,
            "citations": citations,
            "answer_chars": len(self.answer or ""),
            "no_hit_answer": bool(self.answer) and not citations,
            "error": self.error,
            "signals": {
                "zero_hit_queries": zero_hit,
                "cited_not_retrieved": [path for path in citations if path not in retrieved_paths],
                "retrieved_but_unused": [path for path in retrieved_paths if path not in citations][:10],
            },
        }


def append_trace(working_directory: Path, record: dict, moment: datetime | None = None) -> Path:
    path = _usage_path(working_directory, moment)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def read_traces(working_directory: Path, *, days: int | None = None) -> list[dict]:
    directory = _local_dir(working_directory)
    if not directory.is_dir():
        return []
    files = sorted(directory.glob("*.jsonl"))
    if days is not None:
        files = files[-days:]
    records: list[dict] = []
    for path in files:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def summarize(records: list[dict]) -> dict:
    total = len(records)
    if not total:
        return {"traces": 0}
    zero_hit = sum(1 for record in records if record.get("signals", {}).get("zero_hit_queries"))
    with_citation = sum(1 for record in records if record.get("citations"))
    cited_not_retrieved = sum(len(record.get("signals", {}).get("cited_not_retrieved") or []) for record in records)
    steps = [len(record.get("steps") or []) for record in records]
    queries = Counter(
        entry["query"]
        for record in records
        for entry in (record.get("signals", {}).get("zero_hit_queries") or [])
        if entry.get("query")
    )
    return {
        "traces": total,
        "zero_hit_traces": zero_hit,
        "zero_hit_rate": round(zero_hit / total, 4),
        "citation_rate": round(with_citation / total, 4),
        "cited_not_retrieved": cited_not_retrieved,
        "avg_steps": round(sum(steps) / total, 2) if steps else 0.0,
        "top_zero_hit_queries": [{"query": query, "count": count} for query, count in queries.most_common(10)],
    }

def rollup_usage(working_directory: Path, repository_root: Path, member: str, *, keep_months: int = KEEP_MONTHS) -> Path | None:
    """把本地 trace 按天汇总写入治理目录；同一天重复执行结果一致。"""

    records = read_traces(working_directory)
    if not records:
        return None
    by_day: dict[str, list[dict]] = {}
    for record in records:
        day = str(record.get("ts") or "")[:10]
        if day:
            by_day.setdefault(day, []).append(record)
    months: dict[str, list[dict]] = {}
    for day in sorted(by_day):
        items = by_day[day]
        months.setdefault(day[:7], []).append({
            "day": day,
            "member": member,
            "traces": len(items),
            "metrics": summarize(items),
            "questions": [item.get("question") for item in items if item.get("question")][:20],
        })
    directory = member_governance_directory(Path(repository_root), member) / USAGE_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    written: Path | None = None
    for month in sorted(months):
        target = directory / f"{month}.jsonl"
        target.write_text("".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in months[month]), encoding="utf-8")
        written = target
    if keep_months > 0:
        for stale in sorted(directory.glob("*.jsonl"))[:-keep_months]:
            stale.unlink(missing_ok=True)
    return written


def question_candidates(working_directory: Path, *, limit: int = 20) -> list[dict]:
    """从零命中与无引用回答里挑出评测题候选。"""

    candidates: list[dict] = []
    seen: set[str] = set()
    for record in read_traces(working_directory):
        question = str(record.get("question") or "").strip()
        if not question or question in seen:
            continue
        signals = record.get("signals") or {}
        reasons = []
        if signals.get("zero_hit_queries"):
            reasons.append("zero_hit")
        if record.get("no_hit_answer"):
            reasons.append("answer_without_citation")
        if not reasons:
            continue
        seen.add(question)
        candidates.append({
            "question": question,
            "reasons": reasons,
            "zero_hit_queries": [entry.get("query") for entry in signals.get("zero_hit_queries") or []],
            "ts": record.get("ts"),
        })
        if len(candidates) >= limit:
            break
    return candidates

