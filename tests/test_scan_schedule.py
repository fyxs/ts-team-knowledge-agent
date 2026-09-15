import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.services.scheduler import is_scan_due, last_run_started_at


def _settings(tmp_path: Path, interval: int) -> Settings:
    settings = Settings("whm", tmp_path / "source", tmp_path / "work", tmp_path / "repo", interval)
    (settings.working_directory / "logs").mkdir(parents=True, exist_ok=True)
    return settings


def _write_run(settings: Settings, started_at: datetime) -> None:
    report = settings.working_directory / "logs" / "runs.jsonl"
    with report.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"started_at": started_at.isoformat(), "scanned": 1}) + "\n")


def test_due_when_no_history(tmp_path):
    settings = _settings(tmp_path, 60)
    assert last_run_started_at(settings.working_directory) is None
    assert is_scan_due(settings) is True


def test_not_due_before_interval(tmp_path):
    settings = _settings(tmp_path, 60)
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    _write_run(settings, now - timedelta(minutes=5))
    assert is_scan_due(settings, now=now) is False


def test_due_after_interval(tmp_path):
    settings = _settings(tmp_path, 60)
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    _write_run(settings, now - timedelta(minutes=90))
    assert is_scan_due(settings, now=now) is True


def test_last_run_uses_latest_entry(tmp_path):
    settings = _settings(tmp_path, 60)
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    _write_run(settings, now - timedelta(minutes=120))
    _write_run(settings, now - timedelta(minutes=30))
    last = last_run_started_at(settings.working_directory)
    assert last is not None
    assert abs((now - last).total_seconds() - 1800) < 5
