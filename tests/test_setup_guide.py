from pathlib import Path

from ts_knowledge_agent.agent.secrets import read_api_key
from ts_knowledge_agent.agent.setup import configure_model_interactively, parse_provider, resolve_base_url
from ts_knowledge_agent.config import Settings


def _settings(tmp_path: Path) -> Settings:
    source = tmp_path / "source"
    source.mkdir()
    settings = Settings("whm", source, tmp_path / "work", tmp_path / "repo", 60)
    settings.working_directory.mkdir(parents=True, exist_ok=True)
    return settings


def _reader(values):
    queue = list(values)

    def read(prompt: str) -> str:
        if not queue:
            raise AssertionError(f"unexpected prompt: {prompt}")
        return queue.pop(0)

    return read


def test_provider_defaults_to_openai():
    assert parse_provider("") == "openai"
    assert parse_provider("  DeepSeek-Proxy  ") == "deepseek-proxy"


def test_anthropic_uses_official_base_url_when_blank():
    assert resolve_base_url("anthropic", "") == "https://api.anthropic.com"
    assert resolve_base_url("openai", "") == ""
    assert resolve_base_url("openai", "https://gw.example.com/v1/") == "https://gw.example.com/v1"


def test_guided_setup_collects_four_steps_in_order(tmp_path):
    settings = _settings(tmp_path)
    prompts: list[str] = []
    lines: list[str] = []

    def ask_input(prompt: str) -> str:
        prompts.append(prompt)
        values = {"供应商名称: ": "deepseek-proxy", "请求地址: ": "http://gw.example.com/v1", "模型名称: ": "deepseek-flash"}
        return values[prompt]

    updated = configure_model_interactively(
        settings,
        ask_input=ask_input,
        ask_secret=lambda prompt: "secret-value-123",
        echo=lines.append,
    )

    assert [prompt for prompt in prompts] == ["供应商名称: ", "请求地址: ", "模型名称: "]
    assert updated.model_provider == "deepseek-proxy"
    assert updated.model_base_url == "http://gw.example.com/v1"
    assert updated.model_name == "deepseek-flash"
    assert read_api_key(settings.working_directory) == "secret-value-123"
    text = "\n".join(lines)
    assert "secret-value-123" not in text
    assert "[1/4]" in text and "[2/4]" in text and "[3/4]" in text and "[4/4]" in text


def test_guided_setup_skips_key_without_writing(tmp_path):
    settings = _settings(tmp_path)

    updated = configure_model_interactively(
        settings,
        ask_input=_reader(["openai", "https://gw.example.com/v1", "gpt-4o-mini"]),
        ask_secret=lambda prompt: "   ",
        echo=lambda line: None,
    )

    assert updated.model_name == "gpt-4o-mini"
    assert read_api_key(settings.working_directory) == ""


def test_guided_setup_keeps_other_settings(tmp_path):
    settings = _settings(tmp_path)

    updated = configure_model_interactively(
        settings,
        ask_input=_reader(["anthropic", "", "claude-sonnet-4-5"]),
        ask_secret=lambda prompt: "k",
        echo=lambda line: None,
    )

    assert updated.personal_workspace == settings.personal_workspace
    assert updated.shared_source_directory == settings.shared_source_directory
    assert updated.model_base_url == "https://api.anthropic.com"
