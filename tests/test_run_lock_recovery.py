import json
import os
import socket
import time
from pathlib import Path

import pytest

from ts_knowledge_agent.services.run_lock import RunLock


def _work(tmp_path: Path) -> Path:
    work = tmp_path / "work"
    (work / "runtime").mkdir(parents=True, exist_ok=True)
    return work


def test_acquire_writes_holder_and_releases(tmp_path: Path) -> None:
    work = _work(tmp_path)
    lock_path = work / "runtime" / "run.lock"
    with RunLock(work):
        holder = json.loads(lock_path.read_text(encoding="utf-8"))
        assert holder["pid"] == os.getpid()
        assert holder["host"] == socket.gethostname()
    assert not lock_path.exists()


def test_live_process_blocks(tmp_path: Path) -> None:
    work = _work(tmp_path)
    (work / "runtime" / "run.lock").write_text(
        json.dumps({"pid": os.getpid(), "host": socket.gethostname(), "created_at": time.time()}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError):
        with RunLock(work):
            pass


def test_dead_process_is_taken_over_and_logged(tmp_path: Path) -> None:
    work = _work(tmp_path)
    (work / "runtime" / "run.lock").write_text(
        json.dumps({"pid": 999999, "host": socket.gethostname(), "created_at": time.time()}),
        encoding="utf-8",
    )
    with RunLock(work):
        pass
    recoveries = work / "logs" / "lock-recoveries.jsonl"
    assert recoveries.is_file()
    record = json.loads(recoveries.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert "is gone" in record["reason"]
    assert record["holder_pid"] == 999999


def test_other_host_falls_back_to_age(tmp_path: Path) -> None:
    work = _work(tmp_path)
    (work / "runtime" / "run.lock").write_text(
        json.dumps({"pid": 999999, "host": "another-host", "created_at": time.time()}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError):
        with RunLock(work):
            pass


def test_lock_older_than_threshold_is_taken_over(tmp_path: Path) -> None:
    work = _work(tmp_path)
    (work / "runtime" / "run.lock").write_text(
        json.dumps({"pid": os.getpid(), "host": socket.gethostname(), "created_at": time.time() - 7201}),
        encoding="utf-8",
    )
    with RunLock(work):
        pass
    assert not (work / "runtime" / "run.lock").exists()

def test_lock_stale_threshold_follows_mineru_timeout(tmp_path, monkeypatch):
    """锁过期阈值必须大于单文件超时：否则长转换跑到一半锁被判过期，出现两个转换同时跑。"""
    import importlib
    from ts_knowledge_agent.config import Settings
    from ts_knowledge_agent.services import pipeline
    from ts_knowledge_agent.services import run_lock as run_lock_module

    captured = {}

    class FakeLock:
        def __init__(self, working_directory, name=None, stale_seconds=None):
            captured["name"] = name
            captured["stale_seconds"] = stale_seconds

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(pipeline, "RunLock", FakeLock)
    settings = Settings(
        personal_workspace="tester",
        shared_source_directory=tmp_path / "source",
        working_directory=tmp_path,
        shared_knowledge_repository_directory=tmp_path / "kb",
        mineru_timeout_seconds=14400,
    )
    try:
        pipeline.run_once(settings, lane="heavy")
    except Exception:
        pass  # 后续步骤失败无所谓，只看锁参数
    assert captured["stale_seconds"] >= 14400 + 600
    assert captured["name"] == pipeline.LANE_LOCK_NAMES["heavy"]
