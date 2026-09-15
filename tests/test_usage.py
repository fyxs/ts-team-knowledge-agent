import json
from pathlib import Path

from ts_knowledge_agent.services.usage import (
    TraceCollector,
    append_trace,
    question_candidates,
    read_traces,
    rollup_usage,
    summarize,
)

SEARCH_EVENTS = [
    {"type": "start", "question": "空调群控第一阶段的范围是什么"},
    {"type": "tool_call", "name": "knowledge_search", "arguments": {"query": "空调群控 第一阶段"}, "step": 1},
    {"type": "tool_result", "name": "knowledge_search",
     "paths": ["members/whm/a.md", "members/whm/b.md"], "step": 1},
    {"type": "tool_call", "name": "knowledge_read", "arguments": {"path": "members/whm/a.md"}, "step": 2},
    {"type": "tool_result", "name": "knowledge_read", "paths": ["members/whm/a.md"], "step": 2},
    {"type": "answer", "content": "答案内容", "citations": ["members/whm/a.md"], "retrieved": True},
]


def _collect(events):
    collector = TraceCollector()
    for event in events:
        collector(event)
    return collector


def test_collector_captures_retrieval_chain():
    record = _collect(SEARCH_EVENTS).to_record("whm", "web")
    assert record["question"] == "空调群控第一阶段的范围是什么"
    assert record["surface"] == "web"
    assert record["retrieved_paths"] == ["members/whm/a.md", "members/whm/b.md"]
    assert record["citations"] == ["members/whm/a.md"]
    assert record["signals"]["cited_not_retrieved"] == []
    assert record["signals"]["retrieved_but_unused"] == ["members/whm/b.md"]
    assert record["signals"]["zero_hit_queries"] == []


def test_zero_hit_query_becomes_candidate(tmp_path):
    events = [
        {"type": "start", "question": "完全不存在的主题"},
        {"type": "tool_call", "name": "knowledge_search", "arguments": {"query": "不存在 的词"}, "step": 1},
        {"type": "tool_result", "name": "knowledge_search", "paths": [], "step": 1},
        {"type": "answer", "content": "知识库中没有找到", "citations": [], "retrieved": False},
    ]
    record = _collect(events).to_record("whm", "cli")
    assert record["signals"]["zero_hit_queries"][0]["query"] == "不存在 的词"
    assert record["no_hit_answer"] is True

    append_trace(tmp_path, record)
    summary = summarize(read_traces(tmp_path))
    assert summary["zero_hit_traces"] == 1
    assert summary["citation_rate"] == 0.0

    candidates = question_candidates(tmp_path)
    assert candidates and candidates[0]["question"] == "完全不存在的主题"
    assert "zero_hit" in candidates[0]["reasons"]


def test_rollup_is_idempotent_and_writes_month_file(tmp_path):
    working = tmp_path / "work"
    repository = tmp_path / "repo"
    append_trace(working, _collect(SEARCH_EVENTS).to_record("whm", "cli"))

    first = rollup_usage(working, repository, "whm")
    second = rollup_usage(working, repository, "whm")
    assert first == second

    lines = first.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["traces"] == 1
    assert entry["member"] == "whm"
    assert entry["metrics"]["citation_rate"] == 1.0
    assert entry["questions"] == ["空调群控第一阶段的范围是什么"]
    assert first.parent.name == "usage" and first.parent.parent.name == "whm"


def test_rollup_without_traces_returns_none(tmp_path):
    assert rollup_usage(tmp_path / "work", tmp_path / "repo", "whm") is None
