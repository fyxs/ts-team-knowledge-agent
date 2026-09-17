from __future__ import annotations

from ts_knowledge_agent.config import config_candidates, resolve_config_path


def test_explicit_env_wins(monkeypatch, tmp_path):
    cfg = tmp_path / "ts-kb.json"
    cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("TS_KB_CONFIG", str(cfg))
    assert resolve_config_path() == cfg


def test_cwd_config_is_found_without_env(monkeypatch, tmp_path):
    cfg = tmp_path / "ts-kb.json"
    cfg.write_text("{}", encoding="utf-8")
    monkeypatch.delenv("TS_KB_CONFIG", raising=False)
    monkeypatch.delenv("TS_KB_WORKING_DIRECTORY", raising=False)
    monkeypatch.chdir(tmp_path)
    assert resolve_config_path() == cfg


def test_cwd_config_is_preferred_over_local_dir(monkeypatch, tmp_path):
    """init 把配置写到 <工作目录>\\ts-kb.json，历史实现却只在 .local\\ 下找，
    表现为"init 明明成功，后续命令却报找不到配置"——这里锁死正确优先级。"""
    top = tmp_path / "ts-kb.json"
    top.write_text("{}", encoding="utf-8")
    local = tmp_path / ".local"
    local.mkdir()
    (local / "ts-kb.json").write_text("{}", encoding="utf-8")
    monkeypatch.delenv("TS_KB_CONFIG", raising=False)
    monkeypatch.delenv("TS_KB_WORKING_DIRECTORY", raising=False)
    monkeypatch.chdir(tmp_path)
    assert resolve_config_path() == top


def test_working_directory_env_is_last_resort(monkeypatch, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    cfg = work / "ts-kb.json"
    cfg.write_text("{}", encoding="utf-8")
    monkeypatch.delenv("TS_KB_CONFIG", raising=False)
    monkeypatch.setenv("TS_KB_WORKING_DIRECTORY", str(work))
    monkeypatch.chdir(tmp_path)
    assert resolve_config_path() == cfg


def test_candidates_are_deduplicated(monkeypatch, tmp_path):
    monkeypatch.setenv("TS_KB_CONFIG", str(tmp_path / "ts-kb.json"))
    monkeypatch.setenv("TS_KB_WORKING_DIRECTORY", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    candidates = config_candidates()
    assert len(candidates) == len(set(candidates))
    assert candidates[0] == tmp_path / "ts-kb.json"
