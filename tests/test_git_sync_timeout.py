"""git 子命令必须有超时：网络差时不能无限等待拖死整轮。"""

import subprocess
from pathlib import Path

import pytest

from ts_knowledge_agent.adapters import git_sync


def test_git_passes_timeout(monkeypatch, tmp_path):
    seen = {}

    def fake_run(args, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(args, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert git_sync._git(tmp_path, "status", "--porcelain") == "ok"
    assert seen.get("timeout") == git_sync.GIT_TIMEOUT_SECONDS


def test_git_timeout_becomes_clear_error(monkeypatch, tmp_path):
    def fake_run(args, **kwargs):
        raise subprocess.TimeoutExpired(args, kwargs.get("timeout"))

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(git_sync.GitSyncError) as excinfo:
        git_sync._git(tmp_path, "fetch", "origin")
    assert "超过" in str(excinfo.value) and "s" in str(excinfo.value)


def test_prepare_repository_degrades_on_timeout(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)

    def fake_git(repo_path, *args):
        if args and args[0] == "status":
            return ""
        raise git_sync.GitSyncError("git fetch origin 超过 180s 未返回（网络问题？）")

    monkeypatch.setattr(git_sync, "_git", fake_git)
    result = git_sync.prepare_repository(repo)
    assert result.status == "blocked_timeout"
