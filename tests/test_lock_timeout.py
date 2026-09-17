import json
import os
import socket
import time
from pathlib import Path
import pytest
from ts_knowledge_agent.adapters.mineru_adapter import MinerUConverter

def test_mineru_timeout_is_configurable(tmp_path):
    python=tmp_path/"python.exe"; python.write_bytes(b"stub")
    c=MinerUConverter(python, timeout_seconds=12)
    assert c.timeout_seconds == 12

def test_run_lock_rejects_active_lock(tmp_path):
    from ts_knowledge_agent.services.run_lock import RunLock
    runtime=tmp_path/"runtime"; runtime.mkdir()
    (runtime/"run.lock").write_text(
        json.dumps({"pid": os.getpid(), "host": socket.gethostname(), "created_at": time.time()}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError):
        with RunLock(tmp_path): pass
