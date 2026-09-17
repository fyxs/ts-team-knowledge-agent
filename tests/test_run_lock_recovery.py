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
