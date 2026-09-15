from datetime import datetime, timedelta, timezone
from pathlib import Path

from ts_knowledge_agent.services.inspection import (
    append_inspection_run,
    is_inspection_due,
    last_inspection_started_at,
)


class _Report:
    sampled = 25
    clean = 25
    blocking = 0
    issue_counts = {}


def test_no_history_means_due(tmp_path):
    assert is_inspection_due(tmp_path) is True


def test_recent_run_is_not_due(tmp_path):
    append_inspection_run(tmp_path, _Report(), datetime.now(timezone.utc).isoformat())
    assert is_inspection_due(tmp_path, interval_minutes=1440) is False


def test_old_run_is_due_again(tmp_path):
    old = datetime.now(timezone.utc) - timedelta(hours=30)
    append_inspection_run(tmp_path, _Report(), old.isoformat())
    assert is_inspection_due(tmp_path, interval_minutes=1440) is True


def test_interval_zero_always_due(tmp_path):
    append_inspection_run(tmp_path, _Report(), datetime.now(timezone.utc).isoformat())
    assert is_inspection_due(tmp_path, interval_minutes=0) is True


def test_last_started_at_reads_latest_line(tmp_path):
    first = datetime.now(timezone.utc) - timedelta(hours=5)
    second = datetime.now(timezone.utc) - timedelta(hours=1)
    append_inspection_run(tmp_path, _Report(), first.isoformat())
    append_inspection_run(tmp_path, _Report(), second.isoformat())
    assert last_inspection_started_at(tmp_path) == second


def test_broken_line_is_skipped(tmp_path):
    path = tmp_path / "logs" / "inspection-runs.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json}\n" + '{"started_at": "2026-09-15T00:00:00+00:00"}\n', encoding="utf-8")
    assert last_inspection_started_at(tmp_path) == datetime(2026, 9, 15, tzinfo=timezone.utc)
