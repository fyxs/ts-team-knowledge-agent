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
