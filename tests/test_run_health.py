import json
from pathlib import Path

from ts_knowledge_agent.services.inspection import (
    CONSECUTIVE_FAILURE_BLOCKING,
    InspectionReport,
    RunHealth,
    collect_run_health,
)


def _write(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")


def test_counts_results(tmp_path: Path) -> None:
    work = tmp_path / "work"
    _write(work / "logs" / "runs.jsonl", [
        {"started_at": "t1", "result": "ok"},
        {"started_at": "t2", "result": "locked", "error": "RuntimeError: another conversion run is already active"},
        {"started_at": "t3", "result": "failed", "error": "RuntimeError: boom"},
    ])
    health = collect_run_health(work)
    assert (health.window, health.ok, health.locked, health.failed) == (3, 1, 1, 1)
    assert health.last_result == "failed"
    assert health.consecutive_failures == 2
    assert health.blocking == 0


def test_consecutive_failures_become_blocking(tmp_path: Path) -> None:
    work = tmp_path / "work"
    _write(work / "logs" / "runs.jsonl", [{"result": "failed", "error": "boom"}] * CONSECUTIVE_FAILURE_BLOCKING)
    health = collect_run_health(work)
    assert health.consecutive_failures == CONSECUTIVE_FAILURE_BLOCKING
    assert health.blocking == 1


def test_ok_run_resets_consecutive_failures(tmp_path: Path) -> None:
    work = tmp_path / "work"
    _write(work / "logs" / "runs.jsonl", [{"result": "failed"}, {"result": "ok"}])
    assert collect_run_health(work).consecutive_failures == 0


def test_legacy_records_without_result_are_derived(tmp_path: Path) -> None:
    work = tmp_path / "work"
    _write(work / "logs" / "runs.jsonl", [
        {"started_at": "t1", "error": None},
        {"started_at": "t2", "error": "RuntimeError: x"},
    ])
    health = collect_run_health(work)
    assert (health.ok, health.failed) == (1, 1)


def test_lock_recoveries_are_counted(tmp_path: Path) -> None:
    work = tmp_path / "work"
    _write(work / "logs" / "lock-recoveries.jsonl", [{"reason": "holder pid 1 is gone"}])
    assert collect_run_health(work).lock_recoveries == 1


def test_report_blocking_includes_run_health() -> None:
    report = InspectionReport(sampled=0, clean=0, issue_counts={}, by_file_type={}, checks=(),
                              run_health=RunHealth(window=3, consecutive_failures=3))
    assert report.blocking == 1
