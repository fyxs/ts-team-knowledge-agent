"""MinerU 超时必须终止整棵进程树。

只杀直接子进程会留下孤儿 worker（实测残留 3~6 小时），它们会让后续每一轮转换一直等待，
最终把整条流水线锁死（锁一直被占，scan/点击/手动运行全部无效）。
"""

import subprocess
from pathlib import Path

import pytest

from ts_knowledge_agent.adapters import mineru_adapter


class FakeProcess:
    def __init__(self, pid: int = 4242) -> None:
        self.pid = pid
        self.returncode = None
        self.args = ["python", "run.py"]

    def poll(self):
        return self.returncode

    def kill(self):
        self.returncode = -9
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def communicate(self, timeout=None):
        raise subprocess.TimeoutExpired(self.args, timeout)


def test_terminate_tree_prefers_tree_kill(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(list(args))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(mineru_adapter.os, "name", "nt")
    monkeypatch.setattr(mineru_adapter.subprocess, "run", fake_run)
    mineru_adapter.terminate_process_tree(FakeProcess())

    assert calls, "超时必须调用终止命令"
    assert calls[0][0] == "taskkill"
    assert "/T" in calls[0] and "/F" in calls[0]


def test_terminate_tree_noop_when_finished():
    process = FakeProcess()
    process.returncode = 0
    mineru_adapter.terminate_process_tree(process)
    assert process.poll() == 0


def test_timeout_terminates_tree(monkeypatch, tmp_path):
    killed = []

    monkeypatch.setattr(mineru_adapter.subprocess, "Popen", lambda *a, **k: FakeProcess())
    monkeypatch.setattr(mineru_adapter, "terminate_process_tree", lambda process: killed.append(process.pid))

    converter = mineru_adapter.MinerUConverter.__new__(mineru_adapter.MinerUConverter)
    converter.python = Path("python.exe")
    converter.timeout_seconds = 1
    converter.chunk_pages = 0  # 分片关闭：本用例只关心超时终止行为
    work = tmp_path / "work"
    work.mkdir()

    with pytest.raises(TimeoutError):
        converter._run(tmp_path / "a.pdf", work)
    assert killed == [4242]
