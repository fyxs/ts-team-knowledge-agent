"""知识库质量巡检：检索召回与引用准确率评测。

评测集是版本化数据（question + 期望文档路径 + 关键词），评测结果写入运行日志，
并可随治理记录发布到共享仓。
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from ts_knowledge_agent.agent.runtime import run_agent
from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.services.knowledge_tools import knowledge_search

NUMBER = re.compile(r"\d+(?:\.\d+)?")
CJK_RUN = re.compile(r"[\u4e00-\u9fff]{2,}")


@dataclass(frozen=True)
class QuestionCase:
    case_id: str
    question: str
    expected_paths: tuple[str, ...]
    keywords: tuple[str, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class RetrievalOutcome:
    case_id: str
    question: str
    rank: int | None
    matched_by: str | None
    top_paths: tuple[str, ...]


def load_cases(path: Path) -> list[QuestionCase]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cases: list[QuestionCase] = []
    for item in payload.get("cases", []):
        cases.append(QuestionCase(
            case_id=str(item["id"]),
            question=str(item["question"]),
            expected_paths=tuple(item.get("expected_paths", ())),
            keywords=tuple(item.get("keywords", ())),
            note=str(item.get("note", "")),
        ))
    if not cases:
        raise ValueError(f"question set is empty: {path}")
    return cases


def _rank_of(question: str, expected: tuple[str, ...], settings: Settings, limit: int) -> tuple[int | None, str | None, tuple[str, ...]]:
    hits = knowledge_search(settings, question, limit=limit)
    paths = tuple(hit.path for hit in hits)
    for index, hit in enumerate(hits, 1):
        if any(hit.path == candidate for candidate in expected):
            return index, hit.matched_by, paths
    return None, None, paths


def evaluate_retrieval(settings: Settings, cases: list[QuestionCase], limit: int = 10) -> dict:
    """评测检索召回：命中排名、命中方式，以及关键词查询的对照结果。"""

    outcomes: list[RetrievalOutcome] = []
    keyword_outcomes: list[RetrievalOutcome] = []
    for case in cases:
        rank, source, paths = _rank_of(case.question, case.expected_paths, settings, limit)
        outcomes.append(RetrievalOutcome(case.case_id, case.question, rank, source, paths))
        if case.keywords:
            query = " ".join(case.keywords)
            kw_rank, kw_source, kw_paths = _rank_of(query, case.expected_paths, settings, limit)
            keyword_outcomes.append(RetrievalOutcome(case.case_id, query, kw_rank, kw_source, kw_paths))

    def summarize(items: list[RetrievalOutcome]) -> dict:
        ranks = [item.rank for item in items]
        hits = [rank for rank in ranks if rank]
        return {
            "cases": len(items),
            "hit_at_1": sum(1 for rank in ranks if rank == 1),
            "hit_at_3": sum(1 for rank in ranks if rank and rank <= 3),
            "hit_at_5": sum(1 for rank in ranks if rank and rank <= 5),
            "hit_at_10": sum(1 for rank in ranks if rank and rank <= 10),
            "miss": sum(1 for rank in ranks if rank is None),
            "mrr": round(sum(1.0 / rank for rank in hits) / len(items), 3) if items else 0.0,
        }

    return {
        "limit": limit,
        "natural_language": summarize(outcomes),
        "keywords": summarize(keyword_outcomes) if keyword_outcomes else None,
        "cases": [asdict(item) for item in outcomes],
        "keyword_cases": [asdict(item) for item in keyword_outcomes],
    }


PATH_PATTERN = re.compile(r"members/[^\s\"'<>()\[\]]+\.md")


def _distinctive_terms(text: str, minimum: int = 4) -> set[str]:
    terms = {token for token in NUMBER.findall(text)}
    terms |= {run for run in CJK_RUN.findall(text) if len(run) >= minimum}
    return terms


def _index_paths(settings: Settings) -> set[str]:
    database = Path(settings.shared_knowledge_repository_directory) / "data" / "state.sqlite3"
    connection = sqlite3.connect(database)
    try:
        return {row[0] for row in connection.execute("SELECT path FROM documents")}
    finally:
        connection.close()


def _document_text(settings: Settings, path: str) -> str:
    target = Path(settings.shared_knowledge_repository_directory) / path
    if not target.is_file():
        return ""
    return target.read_text(encoding="utf-8", errors="replace")


def _retrieved_paths(transcript: list[dict] | None) -> set[str]:
    """从 Agent 会话记录里取出它实际检索到的文档路径。

    引用是否"来自检索"必须对照 Agent 自己看到的结果，而不是评测侧另发的查询。
    """

    paths: set[str] = set()
    for message in transcript or []:
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            paths.update(PATH_PATTERN.findall(content.replace("\\/", "/").replace("\\\\", "/")))
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    blob = json.dumps(item, ensure_ascii=False).replace("\\/", "/").replace("\\\\", "/")
                    paths.update(PATH_PATTERN.findall(blob))
    return paths


def evaluate_citations(settings: Settings, cases: list[QuestionCase], provider, max_steps: int = 8) -> dict:
    """评测引用准确率：是否给出引用、引用是否真实存在、是否来自检索、是否有原文支撑。"""

    indexed = _index_paths(settings)
    results = []
    for case in cases:
        result = run_agent(settings, case.question, provider, max_steps=max_steps)
        citations = list(dict.fromkeys(result.citations))
        retrieved_paths = _retrieved_paths(getattr(result, "transcript", None))
        answer_terms = _distinctive_terms(result.answer or "")

        per_citation = []
        for path in citations:
            document = _document_text(settings, path)
            supported = bool(answer_terms & _distinctive_terms(document)) if document else False
            per_citation.append({
                "path": path,
                "exists": path in indexed,
                "from_retrieval": path in retrieved_paths,
                "term_support": supported,
            })

        expected_hit = any(path in case.expected_paths for path in citations)
        results.append({
            "case_id": case.case_id,
            "question": case.question,
            "steps": result.steps,
            "error": result.error,
            "answered": bool((result.answer or "").strip()),
            "citations": per_citation,
            "citation_count": len(citations),
            "expected_in_citations": expected_hit,
            "expected_paths": list(case.expected_paths),
        })

    total = len(results)
    with_citation = sum(1 for item in results if item["citation_count"] > 0)
    flat = [citation for item in results for citation in item["citations"]]
    return {
        "cases": total,
        "answered": sum(1 for item in results if item["answered"]),
        "with_citation": with_citation,
        "citation_total": len(flat),
        "citation_missing_in_index": sum(1 for citation in flat if not citation["exists"]),
        "citation_not_from_retrieval": sum(1 for citation in flat if not citation["from_retrieval"]),
        "citation_without_term_support": sum(1 for citation in flat if not citation["term_support"]),
        "expected_in_citations": sum(1 for item in results if item["expected_in_citations"]),
        "results": results,
    }


def write_evaluation_report(working_directory: Path, payload: dict) -> Path:
    directory = Path(working_directory) / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    stamped = directory / f"evaluation-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    stamped.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (directory / "evaluation-latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return stamped

EVALUATION_RUNS_FILE = "evaluation-runs.jsonl"
DEFAULT_EVALUATION_INTERVAL_MINUTES = 10080


def _evaluation_runs_path(working_directory: Path) -> Path:
    return Path(working_directory) / "logs" / EVALUATION_RUNS_FILE


def append_evaluation_run(working_directory: Path, payload: dict) -> Path:
    """记录一次评测的摘要，供到期判定与趋势查看。"""

    path = _evaluation_runs_path(working_directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "mode": payload.get("mode"),
        "question_set": payload.get("question_set"),
        "retrieval": (payload.get("retrieval") or {}).get("natural_language"),
        "citations": {key: value for key, value in (payload.get("citations") or {}).items() if key != "results"},
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def last_evaluation_started_at(working_directory: Path) -> datetime | None:
    path = _evaluation_runs_path(working_directory)
    if not path.is_file():
        return None
    for line in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line).get("started_at")
        except json.JSONDecodeError:
            continue
        if not raw:
            continue
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            continue
    return None


def is_evaluation_due(working_directory: Path, interval_minutes: int = DEFAULT_EVALUATION_INTERVAL_MINUTES) -> bool:
    """距上次评测达到间隔才算到期；没有历史记录视为到期。"""

    last = last_evaluation_started_at(working_directory)
    if last is None:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - last).total_seconds() / 60.0
    return elapsed >= float(interval_minutes)

