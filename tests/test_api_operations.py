import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from ts_knowledge_agent.adapters.git_sync import SyncResult
from ts_knowledge_agent.api import main as api_main
from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.services.pipeline import RunSummary


def _config_file(tmp_path: Path) -> Path:
    settings = Settings("whm", tmp_path / "source", tmp_path / "work", tmp_path / "repo", 60)
    (settings.working_directory / "logs").mkdir(parents=True, exist_ok=True)
    settings.working_directory.mkdir(parents=True, exist_ok=True)
    path = settings.working_directory / "ts-kb.json"
    settings.write_file(path)
    return path


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    config = _config_file(tmp_path)
    monkeypatch.setenv("TS_KB_CONFIG", str(config))
    return TestClient(api_main.app)


def test_config_exposes_and_updates_scan_interval(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    body = client.get("/api/v1/config").json()
    assert body["scan_interval_minutes"] == 60

    updated = client.put("/api/v1/config", json={"scan_interval_minutes": 15}).json()
    assert updated["scan_interval_minutes"] == 15
    assert Settings.from_file(Path(os.environ["TS_KB_CONFIG"])).scan_interval_minutes == 15


def test_config_rejects_invalid_scan_interval(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.put("/api/v1/config", json={"scan_interval_minutes": 0})
    assert response.status_code == 400


def test_repository_pull_and_push_report_status(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(api_main, "pull_repository", lambda repo: SyncResult("pulled", commit="abc123"))
    monkeypatch.setattr(api_main, "push_repository", lambda repo: SyncResult("pushed", commit="def456"))

    assert client.post("/api/v1/repository/pull").json() == {"status": "pulled", "commit": "abc123", "message": None}
    assert client.post("/api/v1/repository/push").json() == {"status": "pushed", "commit": "def456", "message": None}


def test_repository_pull_reports_conflict(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(api_main, "pull_repository", lambda repo: SyncResult("blocked_conflict", message="rebase failed"))
    body = client.post("/api/v1/repository/pull").json()
    assert body["status"] == "blocked_conflict"
    assert body["message"] == "rebase failed"


def test_trigger_run_records_summary_and_reports_running(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    captured: dict = {}

    def fake_run(settings, sync=False, batch_size=25):
        captured["sync"] = sync
        captured["batch_size"] = batch_size
        return RunSummary(3, 2, 1, 2, 1, 0, 0, 2, sync_status="pushed", reason_counts={"new_source": 2})

    monkeypatch.setattr(api_main, "run_once_with_report", fake_run)

    started = client.post("/api/v1/run", json={"sync": True, "batch_size": 5}).json()
    assert started["status"] in {"started", "busy"}

    for _ in range(50):
        state = client.get("/api/v1/run").json()
        if not state["running"] and state["last"]:
            break
        import time

        time.sleep(0.05)

    assert captured["sync"] is True
    assert captured["batch_size"] == 5
    state = client.get("/api/v1/run").json()
    assert state["last"]["converted"] == 2
    assert state["last"]["sync_status"] == "pushed"


def test_run_status_reads_latest_report(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    settings = Settings.from_file(Path(os.environ["TS_KB_CONFIG"]))
    report = settings.working_directory / "logs" / "runs.jsonl"
    report.write_text(json.dumps({"started_at": "2026-09-14T00:00:00+00:00", "converted": 7}) + "\n", encoding="utf-8")

    state = client.get("/api/v1/run").json()
    assert state["running"] is False
    assert state["report"]["converted"] == 7
