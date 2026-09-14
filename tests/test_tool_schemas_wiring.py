from pathlib import Path

from ts_knowledge_agent.agent.runtime import ProviderReply, run_agent
from ts_knowledge_agent.agent.tools import TOOL_SCHEMAS
from ts_knowledge_agent.config import Settings


class RecordingProvider:
    def __init__(self, replies):
        self.replies = list(replies)
        self.tools_seen: list[list] = []

    def chat(self, messages, tools):
        self.tools_seen.append(list(tools or []))
        return self.replies.pop(0)


def _settings(tmp_path: Path) -> Settings:
    source = tmp_path / "source"
    source.mkdir()
    settings = Settings("whm", source, tmp_path / "work", tmp_path / "repo", 60)
    settings.working_directory.mkdir(parents=True, exist_ok=True)
    return settings


def test_run_agent_sends_tool_schemas_to_provider(tmp_path):
    settings = _settings(tmp_path)
    provider = RecordingProvider([ProviderReply(content="没有可用知识。", tool_calls=[])])

    run_agent(settings, "团队组件库架构？", provider)

    assert provider.tools_seen, "provider was never called"
    names = {tool["function"]["name"] for tool in provider.tools_seen[0]}
    assert "knowledge_search" in names
    assert "knowledge_read" in names


def test_run_agent_tool_schemas_match_definition(tmp_path):
    settings = _settings(tmp_path)
    provider = RecordingProvider([ProviderReply(content="ok", tool_calls=[])])

    run_agent(settings, "问题", provider)

    assert len(provider.tools_seen[0]) == len(TOOL_SCHEMAS)


def test_run_agent_flags_tool_markup_output_as_error(tmp_path):
    settings = _settings(tmp_path)
    markup = '我先检索。\n\n<||DSML||tool_calls>\n<||DSML||invoke name="knowledge_search">'
    provider = RecordingProvider([ProviderReply(content=markup, tool_calls=[])])

    result = run_agent(settings, "问题", provider)

    assert result.error is not None
    assert "tool markup" in result.error


def test_run_agent_accepts_normal_answer(tmp_path):
    settings = _settings(tmp_path)
    provider = RecordingProvider([ProviderReply(content="知识库中没有找到相关内容。", tool_calls=[])])

    result = run_agent(settings, "问题", provider)

    assert result.error is None
    assert result.answer == "知识库中没有找到相关内容。"
