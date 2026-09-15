from pathlib import Path

import pytest

from ts_knowledge_agent.config import MIN_SCAN_INTERVAL_MINUTES, parse_interval_minutes


def test_minimum_scan_interval_is_five_minutes():
    assert MIN_SCAN_INTERVAL_MINUTES == 5
    assert parse_interval_minutes("5") == 5
    assert parse_interval_minutes(None) == 60


def test_scan_interval_below_minimum_is_rejected():
    for value in ("1", "4", "0", "-10"):
        with pytest.raises(ValueError):
            parse_interval_minutes(value)


def test_settings_from_file_rejects_too_small_interval(tmp_path: Path):
    import json

    from ts_knowledge_agent.config import Settings

    config = tmp_path / "ts-kb.json"
    config.write_text(
        json.dumps(
            {
                "personal_workspace": "whm",
                "shared_source_directory": str(tmp_path / "src"),
                "working_directory": str(tmp_path / "work"),
                "shared_knowledge_repository_directory": str(tmp_path / "repo"),
                "scan_interval_minutes": 2,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        Settings.from_file(config)
