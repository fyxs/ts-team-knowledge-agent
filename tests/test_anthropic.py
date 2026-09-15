import json

from ts_knowledge_agent.agent.anthropic import (
    AnthropicProvider,
    extract_system,
    from_anthropic_response,
    to_anthropic_messages,
    to_anthropic_tools,
)
from ts_knowledge_agent.agent.runtime import OpenAICompatibleProvider, create_provider_from_env

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "knowledge_search",
            "description": "检索知识库",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    }
]


def _clear_env(monkeypatch):
    for name in (
        "TS_TEAM_KB_MODEL_PROVIDER",
        "TS_TEAM_KB_MODEL_NAME",
        "TS_TEAM_KB_MODEL_API_KEY",
        "TS_TEAM_KB_MODEL_BASE_URL",
        "TS_TEAM_KB_MODEL_MAX_TOKENS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_system_message_is_extracted_from_messages():
    messages = [
        {"role": "system", "content": "规则一"},
        {"role": "system", "content": "规则二"},
        {"role": "user", "content": "问题"},
    ]
    assert extract_system(messages) == "规则一\n\n规则二"
    converted = to_anthropic_messages(messages)
    assert converted == [{"role": "user", "content": [{"type": "text", "text": "问题"}]}]


def test_assistant_tool_calls_become_tool_use_blocks_and_results_become_user_message():
    messages = [
        {"role": "user", "content": "问题"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "knowledge_search", "arguments": json.dumps({"query": "架构"})}}],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "[]"},
    ]
    converted = to_anthropic_messages(messages)
    assert converted[1]["role"] == "assistant"
    tool_use = converted[1]["content"][0]
    assert tool_use["type"] == "tool_use"
    assert tool_use["id"] == "call_1"
    assert tool_use["name"] == "knowledge_search"
    assert tool_use["input"] == {"query": "架构"}
    assert converted[2] == {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": "[]"}]}


def test_consecutive_tool_results_are_merged_into_one_user_message():
    messages = [
        {"role": "assistant", "content": "", "tool_calls": [{"id": "a", "function": {"name": "t", "arguments": "{}"}}, {"id": "b", "function": {"name": "t", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "a", "content": "1"},
        {"role": "tool", "tool_call_id": "b", "content": "2"},
    ]
    converted = to_anthropic_messages(messages)
    assert len(converted) == 2
    assert [block["tool_use_id"] for block in converted[1]["content"]] == ["a", "b"]


def test_tools_are_converted_to_input_schema_format():
    converted = to_anthropic_tools(OPENAI_TOOLS)
    assert converted[0]["name"] == "knowledge_search"
    assert converted[0]["input_schema"]["required"] == ["query"]


def test_response_is_converted_to_reply_with_text_and_tool_calls():
    body = {
        "content": [
            {"type": "text", "text": "先检索一下"},
            {"type": "tool_use", "id": "toolu_1", "name": "knowledge_search", "input": {"query": "架构"}},
        ]
    }
    reply = from_anthropic_response(body)
    assert reply.content == "先检索一下"
    assert reply.tool_calls == [{"id": "toolu_1", "name": "knowledge_search", "arguments": {"query": "架构"}}]


def test_provider_builds_anthropic_payload_and_headers():
    provider = AnthropicProvider(api_key="k", model="claude-sonnet", base_url="https://api.anthropic.com", max_tokens=2048)
    messages = [{"role": "system", "content": "系统规则"}, {"role": "user", "content": "问题"}]
    payload = provider.build_payload(messages, OPENAI_TOOLS)
    assert payload["model"] == "claude-sonnet"
    assert payload["max_tokens"] == 2048
    assert payload["system"] == "系统规则"
    assert payload["tools"][0]["input_schema"]["type"] == "object"
    headers = provider.headers()
    assert headers["anthropic-version"] == "2023-06-01"
    assert headers["x-api-key"] == "k"


def test_provider_selection_prefers_anthropic_when_configured(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("TS_TEAM_KB_MODEL_PROVIDER", "anthropic")
    monkeypatch.setenv("TS_TEAM_KB_MODEL_NAME", "claude-sonnet")
    monkeypatch.setenv("TS_TEAM_KB_MODEL_API_KEY", "key")
    provider = create_provider_from_env()
    assert isinstance(provider, AnthropicProvider)
    assert provider.base_url == "https://api.anthropic.com"


def test_provider_selection_infers_anthropic_from_base_url(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("TS_TEAM_KB_MODEL_BASE_URL", "https://api.anthropic.com")
    monkeypatch.setenv("TS_TEAM_KB_MODEL_NAME", "claude-sonnet")
    monkeypatch.setenv("TS_TEAM_KB_MODEL_API_KEY", "key")
    assert isinstance(create_provider_from_env(), AnthropicProvider)


def test_provider_selection_defaults_to_openai_compatible(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("TS_TEAM_KB_MODEL_BASE_URL", "https://gateway.example.com/v1")
    monkeypatch.setenv("TS_TEAM_KB_MODEL_NAME", "model-x")
    monkeypatch.setenv("TS_TEAM_KB_MODEL_API_KEY", "key")
    assert isinstance(create_provider_from_env(), OpenAICompatibleProvider)


def test_provider_selection_returns_none_when_incomplete(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("TS_TEAM_KB_MODEL_PROVIDER", "anthropic")
    monkeypatch.setenv("TS_TEAM_KB_MODEL_NAME", "claude-sonnet")
    assert create_provider_from_env() is None
