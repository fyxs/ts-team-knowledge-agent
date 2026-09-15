from pathlib import Path

from ts_knowledge_agent.agent.runtime import AgentResult, ProviderReply, run_agent
from ts_knowledge_agent.config import Settings


class ScriptedProvider:
    def __init__(self, script: list[ProviderReply]) -> None:
        self.script = list(script)
        self.calls: list[list[dict]] = []

    def chat(self, messages, tools):  # noqa: ANN001
        self.calls.append([dict(message) for message in messages])
        return self.script.pop(0)


def _settings(tmp_path: Path) -> Settings:
    source = tmp_path / "source"
    source.mkdir()
    repo = tmp_path / "repo"
    (repo / "members" / "whm" / "doc").mkdir(parents=True)
    (repo / "members" / "whm" / "doc" / "doc.md").write_text("# 文档\n\n内容足够长的知识正文，用于检索验证。\n", encoding="utf-8")
    from ts_knowledge_agent.services.indexing import index_converted

    settings = Settings("whm", source, tmp_path / "work", repo, 60)
    settings.working_directory.mkdir(parents=True, exist_ok=True)
    index_converted(settings)
    return settings


def test_prompts_for_retrieval_when_model_answers_without_tools(tmp_path):
    settings = _settings(tmp_path)
    provider = ScriptedProvider(
        [
            ProviderReply(content="我直接回答，不检索。", tool_calls=[]),
            ProviderReply(
                content="",
                tool_calls=[{"id": "call_1", "name": "knowledge_search", "arguments": {"query": "文档"}}],
            ),
            ProviderReply(content="## 结论\n\n来自知识库。", tool_calls=[]),
        ]
    )
    events: list[dict] = []

    result = run_agent(settings, "文档讲了什么？", provider, on_event=events.append)

    assert result.retrieved is True
    assert result.citations
    assert any(event.get("type") == "notice" for event in events)
    # 第二次调用时应带上要求检索的提醒
    assert any("必须先调用 knowledge_search" in str(message.get("content")) for message in provider.calls[1])


def test_flags_answer_without_retrieval_when_model_never_uses_tools(tmp_path):
    settings = _settings(tmp_path)
    provider = ScriptedProvider(
        [
            ProviderReply(content="第一轮直接回答。", tool_calls=[]),
            ProviderReply(content="第二轮仍然直接回答。", tool_calls=[]),
        ]
    )
    result = run_agent(settings, "文档讲了什么？", provider)

    assert isinstance(result, AgentResult)
    assert result.retrieved is False
    assert result.error is None
    assert result.answer
    assert result.citations == []


def test_nudge_happens_only_once(tmp_path):
    settings = _settings(tmp_path)
    provider = ScriptedProvider(
        [
            ProviderReply(content="一次不检索。", tool_calls=[]),
            ProviderReply(content="两次都不检索。", tool_calls=[]),
            ProviderReply(content="三次仍然不检索。", tool_calls=[]),
        ]
    )
    result = run_agent(settings, "问题", provider, max_steps=6)

    assert result.retrieved is False
    # 触发一次提醒后不再重复提醒：第二轮直接作为最终回答返回
    assert result.steps == 2
