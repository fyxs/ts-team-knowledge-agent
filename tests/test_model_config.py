import json
from dataclasses import replace
from pathlib import Path

from ts_knowledge_agent.agent.anthropic import AnthropicProvider
from ts_knowledge_agent.agent.runtime import OpenAICompatibleProvider, create_provider, create_provider_from_env
from ts_knowledge_agent.agent.secrets import mask_secret, read_api_key, secret_path, write_api_key
from ts_knowledge_agent.cli.main import main
from ts_knowledge_agent.config import Settings

MODEL_ENV = (
    "TS_TEAM_KB_MODEL_PROVIDER",
    "TS_TEAM_KB_MODEL_NAME",
    "TS_TEAM_KB_MODEL_BASE_URL",
    "TS_TEAM_KB_MODEL_API_KEY",
    "TS_TEAM_KB_MODEL_MAX_TOKENS",
)


def _settings(tmp_path: Path) -> Settings:
    source = tmp_path / "source"
    source.mkdir()
    settings = Settings("whm", source, tmp_path / "work", tmp_path / "repo", 60)
    settings.working_directory.mkdir(parents=True, exist_ok=True)
    return settings


def _clear_env(monkeypatch):
    for name in MODEL_ENV:
        monkeypatch.delenv(name, raising=False)


def test_settings_roundtrip_model_fields(tmp_path):
    settings = _settings(tmp_path)
    updated = replace(settings, model_provider="anthropic", model_name="claude-sonnet", model_base_url="", model_max_tokens=2048)
    path = settings.working_directory / "ts-kb.json"
    updated.write_file(path)

    loaded = Settings.from_file(path)
    assert loaded.model_provider == "anthropic"
    assert loaded.model_name == "claude-sonnet"
    assert loaded.model_max_tokens == 2048


def test_api_key_is_stored_outside_repositories(tmp_path):
    settings = _settings(tmp_path)
    path = write_api_key(settings.working_directory, "sk-test-value-1234")
    assert path == secret_path(settings.working_directory)
    assert "knowledge-base" not in str(path)
    assert read_api_key(settings.working_directory) == "sk-test-value-1234"


def test_mask_secret_hides_value():
    assert mask_secret("") == "not configured"
    assert mask_secret("short") == "configured"
    masked = mask_secret("sk-ant-api03-abcdefgh1234")
    assert "abcdefgh" not in masked
    assert masked.endswith("1234)")


def test_create_provider_uses_settings_when_env_absent(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    settings = replace(_settings(tmp_path), model_provider="anthropic", model_name="claude-sonnet")
    write_api_key(settings.working_directory, "key-from-file")
    provider = create_provider(settings)
    assert isinstance(provider, AnthropicProvider)
    assert provider.model == "claude-sonnet"


def test_create_provider_prefers_environment_over_settings(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    settings = replace(_settings(tmp_path), model_provider="anthropic", model_name="from-file")
    write_api_key(settings.working_directory, "file-key")
    monkeypatch.setenv("TS_TEAM_KB_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("TS_TEAM_KB_MODEL_NAME", "from-env")
    monkeypatch.setenv("TS_TEAM_KB_MODEL_BASE_URL", "https://gateway.example.com/v1")
    monkeypatch.setenv("TS_TEAM_KB_MODEL_API_KEY", "env-key")
    provider = create_provider(settings)
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.model == "from-env"


def test_create_provider_returns_none_without_key(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    settings = replace(_settings(tmp_path), model_provider="anthropic", model_name="claude-sonnet")
    assert create_provider(settings) is None


def test_cli_config_set_writes_model_settings(tmp_path, monkeypatch, capsys):
    _clear_env(monkeypatch)
    settings = _settings(tmp_path)
    config_path = settings.working_directory / "ts-kb.json"
    settings.write_file(config_path)
    monkeypatch.setenv("TS_KB_CONFIG", str(config_path))

    code = main(["config", "set", "--provider", "anthropic", "--model", "claude-sonnet", "--max-tokens", "2048"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["updated"]["model_provider"] == "anthropic"

    loaded = Settings.from_file(config_path)
    assert loaded.model_name == "claude-sonnet"
    assert loaded.model_max_tokens == 2048


def test_cli_config_show_masks_api_key(tmp_path, monkeypatch, capsys):
    _clear_env(monkeypatch)
    settings = _settings(tmp_path)
    config_path = settings.working_directory / "ts-kb.json"
    replace(settings, model_provider="anthropic", model_name="claude-sonnet").write_file(config_path)
    write_api_key(settings.working_directory, "sk-ant-api03-secret-value")
    monkeypatch.setenv("TS_KB_CONFIG", str(config_path))

    code = main(["config", "show"])
    assert code == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["provider"] == "anthropic"
    assert payload["api_key"].startswith("configured")
    assert "sk-ant-api03-secret-value" not in output


def test_cli_config_set_requires_arguments(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    settings = _settings(tmp_path)
    config_path = settings.working_directory / "ts-kb.json"
    settings.write_file(config_path)
    monkeypatch.setenv("TS_KB_CONFIG", str(config_path))
    try:
        main(["config", "set"])
    except SystemExit as exc:
        assert exc.code != 0
    else:
        raise AssertionError("config set without arguments should fail")


def test_env_only_provider_factory_still_available(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("TS_TEAM_KB_MODEL_PROVIDER", "anthropic")
    monkeypatch.setenv("TS_TEAM_KB_MODEL_NAME", "claude-sonnet")
    monkeypatch.setenv("TS_TEAM_KB_MODEL_API_KEY", "key")
    assert isinstance(create_provider_from_env(), AnthropicProvider)
