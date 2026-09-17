import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ts_knowledge_agent.services.retention import apply_prune, build_prune_plan, is_protected


def _workspace(tmp_path: Path) -> Path:
    (tmp_path / "logs" / "usage").mkdir(parents=True)
    (tmp_path / "data").mkdir(parents=True)
    (tmp_path / "data" / "sessions.sqlite3").write_bytes(b"x" * 128)
    (tmp_path / "logs" / "usage" / "2026-09-15.jsonl").write_text('{"question":"x"}\n', encoding="utf-8")
    return tmp_path


def _report(directory: Path, prefix: str, stamp: str, size: int = 32) -> Path:
    path = directory / f"{prefix}-{stamp}.json"
    path.write_text("x" * size, encoding="utf-8")
    return path


def test_plan_keeps_newest_reports_and_marks_oldest(tmp_path):
    work = _workspace(tmp_path)
    logs = work / "logs"
    for stamp in ("20260901T010000Z", "20260902T010000Z", "20260903T010000Z"):
        _report(logs, "inspection", stamp)
    (logs / "inspection-latest.json").write_text("latest", encoding="utf-8")

    plan = build_prune_plan(work, keep_inspection=2, keep_evaluation=0)

    assert [path.name for path in plan.delete] == ["inspection-20260901T010000Z.json"]
    assert plan.kept["inspection"] == 2
    assert plan.kept["evaluation"] == 0


def test_apply_deletes_oldest_and_writes_audit(tmp_path):
    work = _workspace(tmp_path)
    logs = work / "logs"
    old = _report(logs, "evaluation", "20260901T010000Z")
    _report(logs, "evaluation", "20260902T010000Z")

    record = apply_prune(work, build_prune_plan(work, keep_evaluation=1))

    assert record["deleted"] == [old.name]
    assert not old.exists()
    audit = (logs / "prune-runs.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(audit) == 1
    assert json.loads(audit[0])["deleted"] == [old.name]


def test_never_touches_sessions_and_usage(tmp_path):
    work = _workspace(tmp_path)
    plan = build_prune_plan(work, keep_inspection=0, keep_evaluation=0)

    assert all("sessions.sqlite3" not in str(path) for path in plan.delete)
    assert all("usage" not in path.parts for path in plan.delete)
    assert is_protected(work / "data" / "sessions.sqlite3", work)
    assert is_protected(work / "logs" / "usage" / "2026-09-15.jsonl", work)


def test_rotates_oversized_logs(tmp_path):
    work = _workspace(tmp_path)
    logs = work / "logs"
    big = logs / "api.log"
    big.write_text("x" * 2048, encoding="utf-8")

    plan = build_prune_plan(work, log_max_bytes=1024, log_keep=2)
    assert [path.name for path in plan.rotate] == ["api.log"]
    apply_prune(work, plan, log_keep=2)
    assert (logs / "api.log.1").exists() and not big.exists()

    big.write_text("y" * 2048, encoding="utf-8")
    apply_prune(work, build_prune_plan(work, log_max_bytes=1024, log_keep=2), log_keep=2)
    assert (logs / "api.log.2").exists()


def test_archives_old_runs_and_keeps_recent(tmp_path):
    work = _workspace(tmp_path)
    logs = work / "logs"
    now = datetime.now(timezone.utc)
    lines = [
        json.dumps({"started_at": (now - timedelta(days=400)).isoformat(), "scanned": 1}),
        json.dumps({"started_at": now.isoformat(), "scanned": 2}),
    ]
    (logs / "runs.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    plan = build_prune_plan(work, runs_days=365)
    assert plan.archive_months
    apply_prune(work, plan)

    remaining = (logs / "runs.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(remaining) == 1 and json.loads(remaining[0])["scanned"] == 2
    assert len(list((logs / "archive").glob("*.gz"))) == 1
