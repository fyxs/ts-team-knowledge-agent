import json
import subprocess
from pathlib import Path

import pytest

from ts_knowledge_agent.services import mineru_setup
from ts_knowledge_agent.services.mineru_setup import (
    default_mineru_env_path,
    environment_python,
    setup_mineru,
    verify_mineru,
)


def test_environment_python_prefers_windows_layout(tmp_path):
    env = tmp_path / "env"
    (env / "Scripts").mkdir(parents=True)
    (env / "Scripts" / "python.exe").write_bytes(b"x")
    assert environment_python(env).name == "python.exe"

    posix = tmp_path / "posix"
    (posix / "bin").mkdir(parents=True)
    (posix / "bin" / "python").write_bytes(b"x")
    assert environment_python(posix).name == "python"


def test_default_env_path_is_under_user_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert default_mineru_env_path() == tmp_path / "ts-team-kb" / "mineru-env"


def test_setup_reuses_existing_interpreter_and_verifies(tmp_path, monkeypatch):
    python = tmp_path / "python.exe"
    python.write_bytes(b"x")
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "3.4.5 2.14.0", "")

    monkeypatch.setattr(mineru_setup.subprocess, "run", fake_run)
    result = setup_mineru(python=python)

    assert result.ok and result.version == "3.4.5 2.14.0"
    assert calls and calls[0][0] == str(python)


def test_setup_reports_missing_interpreter(tmp_path):
    result = setup_mineru(python=tmp_path / "nope.exe")
    assert not result.ok and "解释器不存在" in (result.error or "")


def test_setup_without_bootstrap_explains_what_to_do(monkeypatch, tmp_path):
    monkeypatch.delenv("TS_KB_BOOTSTRAP_PYTHON", raising=False)
    monkeypatch.setattr(mineru_setup, "resolve_bootstrap", lambda: None)
    result = setup_mineru(env_dir=tmp_path / "env")
    assert not result.ok
    assert "uv.exe" in (result.error or "")


def test_dry_run_lists_steps_without_touching_disk(monkeypatch, tmp_path):
    monkeypatch.setattr(mineru_setup, "resolve_bootstrap", lambda: ["uv"])
    env = tmp_path / "env"
    result = setup_mineru(env_dir=env, dry_run=True)
    assert result.ok and not env.exists()
    assert any("uv venv" in step for step in result.steps)
    assert any("MinerU[pipeline]" in step for step in result.steps)


def test_verify_failure_is_reported(tmp_path, monkeypatch):
    python = tmp_path / "python.exe"
    python.write_bytes(b"x")

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, "", "ModuleNotFoundError: torch")

    monkeypatch.setattr(mineru_setup.subprocess, "run", fake_run)
    ok, detail = verify_mineru(python)
    assert not ok and "torch" in (detail or "")
