from pathlib import Path

from ts_knowledge_agent.agent.prompt import SYSTEM_PROMPT_VERSION, build_system_prompt
from ts_knowledge_agent.agent.runtime import AgentResult, ProviderReply, run_agent
from ts_knowledge_agent.agent.skills import find_skill, load_skills
from ts_knowledge_agent.agent.tools import TOOL_NAMES, dispatch_tool
from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.services.indexing import index_converted

DOC = """# 移动端组件库架构与开发指南

本文描述团队组件库的架构设计、依赖关系与开发规范。

## 规范

组件发布需要遵循版本与主题约定。
"""


def _settings(tmp_path: Path) -> Settings:
    repo = tmp_path / "repo"
    document = repo / "members" / "whm" / "研发指南" / "架构" / "架构.md"
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text(DOC, encoding="utf-8")
    source = tmp_path / "source"
    source.mkdir()
    settings = Settings("whm", source, tmp_path / "work", repo, 60)
    settings.working_directory.mkdir(parents=True, exist_ok=True)
    index_converted(settings)
    return settings


class FakeProvider:
    def __init__(self, replies: list[ProviderReply]) -> None:
        self.replies = list(replies)
        self.seen_tools: list[list[dict]] = []
        self.model = "fake"

    def chat(self, messages, tools):
        self.seen_tools.append(list(tools))
        if not self.replies:
            return ProviderReply(content="没有更多回复")
        return self.replies.pop(0)


def test_system_prompt_lists_skills_and_version():
    skills = load_skills()
    prompt = build_system_prompt(skills)
    assert SYSTEM_PROMPT_VERSION == "v1"
    assert "knowledge-search" in prompt
    assert "先调用 knowledge_search" in prompt
    assert "不得编造" in prompt


def test_skills_are_loaded_from_markdown_with_frontmatter():
    skills = load_skills()
    names = {skill.name for skill in skills}
    assert {"knowledge-search", "source-grounding", "cross-document-analysis", "document-comparison"} <= names
    search = find_skill(skills, "knowledge-search")
    assert search is not None
    assert "检索" in search.description
    assert "步骤" in search.body
    assert find_skill(skills, "missing-skill") is None


def test_tool_schemas_cover_knowledge_tools():
    assert set(TOOL_NAMES) == {"knowledge_search", "knowledge_read", "knowledge_list", "knowledge_status", "load_skill"}


def test_dispatch_search_returns_paths(tmp_path):
    settings = _settings(tmp_path)
    output = dispatch_tool(settings, load_skills(), "knowledge_search", {"query": "架构"})
    assert "members/whm/研发指南/架构/架构.md" in output


def test_dispatch_unknown_tool_returns_error_without_raising(tmp_path):
    settings = _settings(tmp_path)
    output = dispatch_tool(settings, load_skills(), "not_a_tool", {})
    assert "unknown tool" in output


def test_dispatch_load_skill_returns_body():
    output = dispatch_tool(None, load_skills(), "load_skill", {"name": "source-grounding"})
    assert "来源与引用" in output


def test_agent_runs_tools_then_answers_with_citations(tmp_path):
    settings = _settings(tmp_path)
    provider = FakeProvider([
        ProviderReply(content="", tool_calls=[{"id": "call_1", "name": "knowledge_search", "arguments": {"query": "架构"}}]),
        ProviderReply(content="组件库架构见架构文档。"),
    ])
    result = run_agent(settings, "组件库架构是什么？", provider)
    assert isinstance(result, AgentResult)
    assert result.error is None
    assert result.steps == 2
    assert "组件库架构" in result.answer
    assert result.citations == ["members/whm/研发指南/架构/架构.md"]
    assert result.prompt_version == "v1"


def test_agent_reports_max_steps_when_model_keeps_calling_tools(tmp_path):
    settings = _settings(tmp_path)
    loop_reply = ProviderReply(content="", tool_calls=[{"id": "call_x", "name": "knowledge_list", "arguments": {}}])
    provider = FakeProvider([loop_reply] * 5)
    result = run_agent(settings, "列出文档", provider, max_steps=3)
    assert result.error == "max_steps_exceeded"
    assert result.steps == 3


def test_agent_propagates_provider_error(tmp_path):
    settings = _settings(tmp_path)
    provider = FakeProvider([ProviderReply(error="HTTPError: 401")])
    result = run_agent(settings, "问题", provider)
    assert result.error is not None
    assert "401" in result.error
    assert result.answer == ""


def test_agent_rejects_empty_question(tmp_path):
    settings = _settings(tmp_path)
    provider = FakeProvider([])
    try:
        run_agent(settings, "   ", provider)
    except ValueError as exc:
        assert "question" in str(exc)
    else:
        raise AssertionError("empty question was accepted")
