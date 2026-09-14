from pathlib import Path

from ts_knowledge_agent.agent.anthropic import AnthropicProvider
from ts_knowledge_agent.agent.runtime import OpenAICompatibleProvider, create_provider, normalize_openai_base_url
from ts_knowledge_agent.config import Settings


def test_base_url_without_path_gets_v1():
    assert normalize_openai_base_url('http://192.168.20.200:3000') == 'http://192.168.20.200:3000/v1'


def test_base_url_with_trailing_slash_gets_v1():
    assert normalize_openai_base_url('http://host:3000/') == 'http://host:3000/v1'


def test_base_url_with_v1_is_unchanged():
    assert normalize_openai_base_url('http://host:3000/v1') == 'http://host:3000/v1'


def test_base_url_with_custom_prefix_is_unchanged():
    assert normalize_openai_base_url('https://gw.example.com/openai/v1') == 'https://gw.example.com/openai/v1'


def test_empty_base_url_stays_empty():
    assert normalize_openai_base_url('') == ''


def test_create_provider_normalizes_openai_base_url(tmp_path):
    settings = Settings(
        'whm',
        tmp_path / 'source',
        tmp_path / 'work',
        tmp_path / 'repo',
        5,
        model_provider='ts_proxy',
        model_name='deepseek-v4-flash',
        model_base_url='http://192.168.20.200:3000',
    )
    settings.working_directory.mkdir(parents=True, exist_ok=True)
    from ts_knowledge_agent.agent.secrets import write_api_key

    write_api_key(settings.working_directory, 'k' * 20)
    provider = create_provider(settings)
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.base_url == 'http://192.168.20.200:3000/v1'


def test_anthropic_base_url_is_not_normalized(tmp_path):
    settings = Settings(
        'whm',
        tmp_path / 'source',
        tmp_path / 'work',
        tmp_path / 'repo',
        5,
        model_provider='anthropic',
        model_name='claude-sonnet-4-5',
        model_base_url='',
    )
    settings.working_directory.mkdir(parents=True, exist_ok=True)
    from ts_knowledge_agent.agent.secrets import write_api_key

    write_api_key(settings.working_directory, 'k' * 20)
    provider = create_provider(settings)
    assert isinstance(provider, AnthropicProvider)
    assert provider.base_url == 'https://api.anthropic.com'
