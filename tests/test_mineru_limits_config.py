"""MinerU 超时与分片配置：默认值、解析校验、读写往返。"""

from pathlib import Path

import pytest

from ts_knowledge_agent.config import (
    DEFAULT_MINERU_CHUNK_PAGES,
    DEFAULT_MINERU_TIMEOUT_SECONDS,
    MIN_MINERU_TIMEOUT_SECONDS,
    Settings,
    parse_mineru_chunk_pages,
    parse_mineru_timeout_seconds,
)


def _settings(tmp_path: Path, **overrides) -> Settings:
    source_root = tmp_path / "source"; repo = tmp_path / "repo"
    source_root.mkdir(exist_ok=True); repo.mkdir(exist_ok=True)
    payload = dict(personal_workspace="wanghm", shared_source_directory=source_root,
                   working_directory=tmp_path, shared_knowledge_repository_directory=repo,
                   scan_interval_minutes=60, shared_knowledge_repository_url="unused")
    payload.update(overrides)
    return Settings(**payload)


def test_defaults_keep_previous_behaviour() -> None:
    """默认不改行为：单次超时 3600 秒、不分片。"""

    assert DEFAULT_MINERU_TIMEOUT_SECONDS == 3600
    assert DEFAULT_MINERU_CHUNK_PAGES == 0


def test_timeout_parsing_accepts_int_and_float_strings() -> None:
    assert parse_mineru_timeout_seconds(7200) == 7200
    assert parse_mineru_timeout_seconds("14400") == 14400
    assert parse_mineru_timeout_seconds("") == DEFAULT_MINERU_TIMEOUT_SECONDS
    assert parse_mineru_timeout_seconds(None) == DEFAULT_MINERU_TIMEOUT_SECONDS


def test_timeout_rejects_below_floor() -> None:
    with pytest.raises(ValueError):
        parse_mineru_timeout_seconds(MIN_MINERU_TIMEOUT_SECONDS - 1)


def test_chunk_pages_parsing_and_validation() -> None:
    assert parse_mineru_chunk_pages(0) == 0
    assert parse_mineru_chunk_pages("200") == 200
    assert parse_mineru_chunk_pages(None) == DEFAULT_MINERU_CHUNK_PAGES
    with pytest.raises(ValueError):
        parse_mineru_chunk_pages(-1)


def test_settings_roundtrip_persists_both_fields(tmp_path: Path) -> None:
    config = tmp_path / "ts-kb.json"
    settings = _settings(tmp_path, mineru_timeout_seconds=14400, mineru_chunk_pages=100)
    settings.write_file(config)

    reloaded = Settings.from_file(config)
    assert reloaded.mineru_timeout_seconds == 14400
    assert reloaded.mineru_chunk_pages == 100


def test_legacy_config_without_fields_uses_defaults(tmp_path: Path) -> None:
    """老配置文件没有这两个键时，必须回退默认值而不是报错。"""

    import json

    config = tmp_path / "ts-kb.json"
    _settings(tmp_path).write_file(config)
    data = json.loads(config.read_text(encoding="utf-8"))
    data.pop("mineru_timeout_seconds", None)
    data.pop("mineru_chunk_pages", None)
    config.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    reloaded = Settings.from_file(config)
    assert reloaded.mineru_timeout_seconds == DEFAULT_MINERU_TIMEOUT_SECONDS
    assert reloaded.mineru_chunk_pages == DEFAULT_MINERU_CHUNK_PAGES

def test_render_settings_parsing_and_defaults() -> None:
    """渲染层（MINERU_PDF_RENDER_*）同样可配，且有下限保护。"""

    from ts_knowledge_agent.config import (
        DEFAULT_MINERU_RENDER_THREADS,
        DEFAULT_MINERU_RENDER_TIMEOUT_SECONDS,
        parse_mineru_render_threads,
        parse_mineru_render_timeout,
    )

    assert DEFAULT_MINERU_RENDER_TIMEOUT_SECONDS == 300
    assert DEFAULT_MINERU_RENDER_THREADS == 3
    assert parse_mineru_render_timeout(None) == 300
    assert parse_mineru_render_timeout(0) == 0          # 0 = 交给 MinerU 默认
    assert parse_mineru_render_timeout("1800") == 1800
    assert parse_mineru_render_threads(8) == 8
    with pytest.raises(ValueError):
        parse_mineru_render_timeout(-1)
    with pytest.raises(ValueError):
        parse_mineru_render_threads(0)


def test_render_settings_roundtrip(tmp_path: Path) -> None:
    config = tmp_path / "ts-kb.json"
    settings = _settings(tmp_path, mineru_render_timeout_seconds=1800, mineru_render_threads=6)
    settings.write_file(config)

    reloaded = Settings.from_file(config)
    assert reloaded.mineru_render_timeout_seconds == 1800
    assert reloaded.mineru_render_threads == 6


def test_adapter_injects_render_env(monkeypatch, tmp_path: Path) -> None:
    """渲染超时必须真的以环境变量传给 MinerU 子进程，而不是只存在配置里。"""

    from ts_knowledge_agent.adapters import mineru_adapter

    captured = {}

    class FakeProcess:
        pid = 1
        returncode = 0
        args = ["python", "run.py"]

        def poll(self):
            return 0

        def communicate(self, timeout=None):
            return "", ""

    def fake_popen(args, **kwargs):
        captured["env"] = kwargs.get("env") or {}
        captured["args"] = args
        return FakeProcess()

    interpreter = tmp_path / "python.exe"
    interpreter.write_bytes(b"x")
    monkeypatch.setattr(mineru_adapter.subprocess, "Popen", fake_popen)

    converter = mineru_adapter.MinerUConverter(
        interpreter, timeout_seconds=60, chunk_pages=50,
        render_timeout_seconds=1800, render_threads=6)
    work = tmp_path / "work"; work.mkdir()
    converter._run_worker("parse", tmp_path / "a.pdf", work / "output", start=0, end=49)

    assert captured["env"]["MINERU_PDF_RENDER_TIMEOUT"] == "1800"
    assert captured["env"]["MINERU_PDF_RENDER_THREADS"] == "6"
    # 页范围随参数传给子进程：mode / source / out_dir / start / end
    assert captured["args"][2] == "parse"
    assert captured["args"][4].endswith("output")
    assert captured["args"][5] == "0" and captured["args"][6] == "49"
