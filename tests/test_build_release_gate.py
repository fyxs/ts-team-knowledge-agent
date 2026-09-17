"""出包门禁：前端产物不得落后于源码（dist 不进 Git，只能靠这道校验拦）。"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build-release.py"


def load_gate_module():
    spec = importlib.util.spec_from_file_location("build_release_gate", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_with_mtime(path: Path, mtime: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def test_stale_frontend_is_rejected(tmp_path: Path) -> None:
    module = load_gate_module()
    write_with_mtime(tmp_path / "dist" / "index.html", 1_000)
    write_with_mtime(tmp_path / "dist" / "assets" / "index-old.js", 1_000)
    write_with_mtime(tmp_path / "src" / "App.tsx", 2_000)
    with pytest.raises(SystemExit):
        module.ensure_frontend_fresh(tmp_path / "dist")


def test_fresh_frontend_passes(tmp_path: Path) -> None:
    module = load_gate_module()
    write_with_mtime(tmp_path / "dist" / "assets" / "index-new.js", 2_000)
    write_with_mtime(tmp_path / "src" / "App.tsx", 1_000)
    module.ensure_frontend_fresh(tmp_path / "dist")


def test_allow_stale_reports_warning(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    module = load_gate_module()
    write_with_mtime(tmp_path / "dist" / "assets" / "index-old.js", 1_000)
    write_with_mtime(tmp_path / "src" / "App.tsx", 2_000)
    module.ensure_frontend_fresh(tmp_path / "dist", allow_stale=True)
    assert "warning" in capsys.readouterr().out


def test_missing_source_directory_is_ignored(tmp_path: Path) -> None:
    module = load_gate_module()
    write_with_mtime(tmp_path / "dist" / "assets" / "index.js", 1_000)
    module.ensure_frontend_fresh(tmp_path / "dist")


def test_non_source_extension_does_not_block(tmp_path: Path) -> None:
    module = load_gate_module()
    write_with_mtime(tmp_path / "dist" / "assets" / "index.js", 1_000)
    write_with_mtime(tmp_path / "src" / "notes.md", 2_000)
    module.ensure_frontend_fresh(tmp_path / "dist")
