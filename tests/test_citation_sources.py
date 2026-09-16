from pathlib import Path

from ts_knowledge_agent.agent.runtime import ProviderReply, run_agent
from ts_knowledge_agent.config import Settings

DOC = """# 前端编码规范

## 环境变量

环境变量集中读取，禁止在业务代码里直接读 process.env。

密钥不进前端：只有 VITE_ 前缀的变量才会被注入。
"""


class ScriptedProvider:
    def __init__(self, script):
        self.script = list(script)

    def chat(self, messages, tools):
        return self.script.pop(0)


def _settings(tmp_path: Path) -> Settings:
    settings = Settings("whm", tmp_path / "source", tmp_path / "work", tmp_path / "repo", 5)
    settings.working_directory.mkdir(parents=True, exist_ok=True)
    folder = settings.shared_knowledge_repository_directory / "members" / "whm" / "规范"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "前端编码规范.md").write_text(DOC, encoding="utf-8")
    from ts_knowledge_agent.services.indexing import index_converted

    index_converted(settings)
    return settings


def test_search_citation_carries_title_and_hit_lines(tmp_path):
    settings = _settings(tmp_path)
    provider = ScriptedProvider(
        [
            ProviderReply(
                content="",
                tool_calls=[{"id": "1", "name": "knowledge_search", "arguments": {"query": "环境变量集中读取"}}],
            ),
            ProviderReply(content="结论：集中读取。", tool_calls=[]),
        ]
    )

    result = run_agent(settings, "环境变量怎么读取？", provider, skills=[], max_steps=3)

    # citations 保持字符串数组：CLI 与评测按这个形状消费，结构化信息走新增的 sources。
    assert result.citations == ["members/whm/规范/前端编码规范.md"]
    assert len(result.sources) == 1
    source = result.sources[0]
    assert source["path"] == "members/whm/规范/前端编码规范.md"
    assert source["title"].startswith("前端编码规范")
    # 命中行按行号升序；行号取自全量正文，前端据此落到被引用的那一段。
    assert [hit["line"] for hit in source["hits"]] == [3, 5, 7]
    assert "环境变量集中读取" in source["hits"][1]["snippet"]


def test_read_only_citation_keeps_source_without_inventing_hits(tmp_path):
    settings = _settings(tmp_path)
    provider = ScriptedProvider(
        [
            ProviderReply(
                content="",
                tool_calls=[{"id": "1", "name": "knowledge_read", "arguments": {"path": "members/whm/规范/前端编码规范.md"}}],
            ),
            ProviderReply(content="结论：见规范。", tool_calls=[]),
        ]
    )

    result = run_agent(settings, "规范里写了什么？", provider, skills=[], max_steps=3)

    assert result.citations == ["members/whm/规范/前端编码规范.md"]
    assert len(result.sources) == 1
    # 只读过文档、没有检索词：不编造命中，hits 留空，由前端显示「已引用」。
    assert result.sources[0]["hits"] == []
    assert result.sources[0]["title"].startswith("前端编码规范")


def test_list_only_turn_has_no_sources(tmp_path):
    settings = _settings(tmp_path)
    provider = ScriptedProvider(
        [
            ProviderReply(content="", tool_calls=[{"id": "1", "name": "knowledge_list", "arguments": {}}]),
            ProviderReply(content="结论：见文档。", tool_calls=[]),
            ProviderReply(content="结论：只列了目录。", tool_calls=[]),
        ]
    )

    result = run_agent(settings, "知识库有哪些文档？", provider, skills=[], max_steps=4)

    assert result.citations == []
    assert result.sources == []


def test_http_layer_carries_sources_to_the_client(monkeypatch, tmp_path):
    """引用能不能点开，取决于 sources 真的走到了 HTTP 出口与会话库，而不只是进程内。"""

    import json

    from fastapi.testclient import TestClient

    from ts_knowledge_agent.api import main as api_main

    settings = _settings(tmp_path)
    settings.write_file(settings.working_directory / "ts-kb.json")
    monkeypatch.setenv("TS_KB_CONFIG", str(settings.working_directory / "ts-kb.json"))
    provider = ScriptedProvider(
        [
            ProviderReply(
                content="",
                tool_calls=[{"id": "1", "name": "knowledge_search", "arguments": {"query": "环境变量集中读取"}}],
            ),
            ProviderReply(content="## 结论\n环境变量集中读取。", tool_calls=[]),
        ]
    )
    monkeypatch.setattr(api_main, "create_provider", lambda settings: provider)
    client = TestClient(api_main.app)

    with client.stream("POST", "/api/v1/chat/stream", json={"question": "环境变量怎么读取？"}) as response:
        assert response.status_code == 200
        body = "".join(chunk for chunk in response.iter_text())

    events = [
        json.loads(line[6:])
        for line in body.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]
    answer = [event for event in events if event["type"] == "answer"][-1]
    assert answer["citations"] == ["members/whm/规范/前端编码规范.md"]
    assert answer["sources"][0]["title"].startswith("前端编码规范")
    assert [hit["line"] for hit in answer["sources"][0]["hits"]] == [3, 5, 7]

    # 历史会话回放同样要带 sources，否则重开一条会话，引用就退化成不可点的纯文本。
    session_id = client.get("/api/v1/sessions").json()["sessions"][0]["id"]
    messages = client.get(f"/api/v1/sessions/{session_id}/messages").json()["messages"]
    stored = [message for message in messages if message["kind"] == "answer"]
    assert stored and stored[0]["sources"][0]["path"] == "members/whm/规范/前端编码规范.md"
