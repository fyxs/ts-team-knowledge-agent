from pathlib import Path

from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.services import scheduler as scheduler_module
from ts_knowledge_agent.services.pipeline import RunSummary


def _settings(tmp_path: Path, sync_on_schedule: bool = True) -> Settings:
    settings = Settings(
        "whm", tmp_path / "source", tmp_path / "work", tmp_path / "repo",
        scan_interval_minutes=5, sync_on_schedule=sync_on_schedule,
    )
    settings.working_directory.mkdir(parents=True, exist_ok=True)
    return settings


def test_scheduler_default_run_pushes_to_shared_repository(tmp_path, monkeypatch):
    captured = {}

    def fake_run_once(settings, sync=False, batch_size=25, **kwargs):
        captured["sync"] = sync
        return RunSummary(1, queued=0, batches=0, converted=0, skipped=1)

    monkeypatch.setattr(scheduler_module, "run_once", fake_run_once)

    scheduler_module.run_scheduler(_settings(tmp_path), sleep=lambda seconds: None, max_runs=1)

    assert captured["sync"] is True


def test_scheduler_respects_disabled_sync(tmp_path, monkeypatch):
    captured = {}

    def fake_run_once(settings, sync=False, batch_size=25, **kwargs):
        captured["sync"] = sync
        return RunSummary(1, queued=0, batches=0, converted=0, skipped=1)

    monkeypatch.setattr(scheduler_module, "run_once", fake_run_once)

    scheduler_module.run_scheduler(
        _settings(tmp_path, sync_on_schedule=False), sleep=lambda seconds: None, max_runs=1
    )

    assert captured["sync"] is False


def test_config_roundtrips_sync_and_interval(tmp_path):
    path = tmp_path / "ts-kb.json"
    _settings(tmp_path, sync_on_schedule=False).write_file(path)

    loaded = Settings.from_file(path)

    assert loaded.scan_interval_minutes == 5
    assert loaded.sync_on_schedule is False
