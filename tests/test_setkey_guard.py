import json
from pathlib import Path

from ts_knowledge_agent.agent.secrets import read_api_key
from ts_knowledge_agent.cli.main import main
from ts_knowledge_agent.config import Settings


def _settings(tmp_path: Path) -> Settings:
    source = tmp_path / "source"
    source.mkdir()
    settings = Settings("whm", source, tmp_path / "work", tmp_path / "repo", 60)
    settings.working_directory.mkdir(parents=True, exist_ok=True)
    settings.write_file(settings.working_directory / "ts-kb.json")
    return settings


def test_set_key_refuses_command_line_argument(tmp_path, monkeypatch, capsys):
    settings = _settings(tmp_path)
    monkeypatch.setenv("TS_KB_CONFIG", str(settings.working_directory / "ts-kb.json"))

    code = main(["config", "set-key", "should-not-be-accepted"])

    output = capsys.readouterr().out
    assert code == 2
    assert "refused" in output
    assert read_api_key(settings.working_directory) == ""


def test_set_key_reads_from_file(tmp_path, monkeypatch, capsys):
    settings = _settings(tmp_path)
    monkeypatch.setenv("TS_KB_CONFIG", str(settings.working_directory / "ts-kb.json"))
    key_file = tmp_path / "key.txt"
    key_file.write_text("gw-v1-test-key-value\n", encoding="utf-8")

    code = main(["config", "set-key", "--from-file", str(key_file)])

    assert code == 0
    assert read_api_key(settings.working_directory) == "gw-v1-test-key-value"
    assert str(key_file) in capsys.readouterr().out


def test_set_key_reads_hidden_prompt(tmp_path, monkeypatch, capsys):
    settings = _settings(tmp_path)
    monkeypatch.setenv("TS_KB_CONFIG", str(settings.working_directory / "ts-kb.json"))
    monkeypatch.setattr("ts_knowledge_agent.cli.main.getpass.getpass", lambda prompt="": "typed-secret")

    code = main(["config", "set-key"])

    assert code == 0
    assert read_api_key(settings.working_directory) == "typed-secret"


def test_set_key_missing_file_is_reported(tmp_path, monkeypatch, capsys):
    settings = _settings(tmp_path)
    monkeypatch.setenv("TS_KB_CONFIG", str(settings.working_directory / "ts-kb.json"))

    code = main(["config", "set-key", "--from-file", str(tmp_path / "missing.txt")])

    assert code == 2
    assert "key file not found" in capsys.readouterr().out
