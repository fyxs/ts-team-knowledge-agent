from pathlib import Path

from ts_knowledge_agent.agent.runtime import ProviderReply, run_agent
from ts_knowledge_agent.config import Settings


class ScriptedProvider:
    def __init__(self, script):
        self.script = list(script)

    def chat(self, messages, tools):
        return self.script.pop(0)


def _settings(tmp_path: Path) -> Settings:
    settings = Settings("whm", tmp_path / "source", tmp_path / "work", tmp_path / "repo", 5)
    settings.working_directory.mkdir(parents=True, exist_ok=True)
    (settings.shared_knowledge_repository_directory / "members" / "whm" / "a").mkdir(parents=True, exist_ok=True)
    (settings.shared_knowledge_repository_directory / "members" / "whm" / "a" / "a.md").write_text(
        "# 架构文档\n\n组件库采用 Monorepo 模式管理多端组件。\n", encoding="utf-8"
    )
    from ts_knowledge_agent.services.indexing import index_converted

    index_converted(settings)
    return settings


def test_list_results_do_not_become_citations(tmp_path):
    settings = _settings(tmp_path)
    # 列目录不算引用；因此该轮结束后会触发一次「先检索」提醒，再给出回答。
    provider = ScriptedProvider(
        [
            ProviderReply(content="", tool_calls=[{"id": "1", "name": "knowledge_list", "arguments": {}}]),
            ProviderReply(content="结论：见文档。", tool_calls=[]),
            ProviderReply(content="结论：仍然只列了目录。", tool_calls=[]),
        ]
    )
    result = run_agent(settings, "知识库有哪些文档？", provider, skills=[], max_steps=4)
    assert result.citations == []
    assert result.retrieved is False


def test_read_results_become_citations(tmp_path):
    settings = _settings(tmp_path)
    provider = ScriptedProvider(
        [
            ProviderReply(
                content="",
                tool_calls=[{"id": "1", "name": "knowledge_read", "arguments": {"path": "members/whm/a/a.md"}}],
            ),
            ProviderReply(content="结论：Monorepo。", tool_calls=[]),
        ]
    )
    result = run_agent(settings, "组件库用什么模式？", provider, skills=[], max_steps=3)
    assert result.citations == ["members/whm/a/a.md"]
    assert result.retrieved is True


def test_search_results_become_citations(tmp_path):
    settings = _settings(tmp_path)
    provider = ScriptedProvider(
        [
            ProviderReply(
                content="",
                tool_calls=[{"id": "1", "name": "knowledge_search", "arguments": {"query": "架构"}}],
            ),
            ProviderReply(content="结论：Monorepo。", tool_calls=[]),
        ]
    )
    result = run_agent(settings, "架构是什么？", provider, skills=[], max_steps=3)
    assert "members/whm/a/a.md" in result.citations
