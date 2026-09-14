import json

from fastapi.testclient import TestClient

from ts_knowledge_agent.agent.runtime import ProviderReply
from ts_knowledge_agent.api import main as api_main
from ts_knowledge_agent.config import Settings


class ScriptedProvider:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def chat(self, messages, tools=None):
        self.calls.append({"messages": list(messages), "tools": tools})
        if not self.script:
            return ProviderReply(content="没有更多脚本响应")
        return self.script.pop(0)


def _settings(tmp_path) -> Settings:
    repo = tmp_path / "repo"
    doc = repo / "members" / "whm" / "doc"
    doc.mkdir(parents=True)
    (doc / "doc.md").write_text("# 组件库架构\n\n这是组件库架构说明，包含 Monorepo 与 UniApp 内容。\n", encoding="utf-8")
    source = tmp_path / "source"
    source.mkdir()
    settings = Settings("whm", source, tmp_path / "work", repo, 5)
    settings.working_directory.mkdir(parents=True, exist_ok=True)
    settings.write_file(settings.working_directory / "ts-kb.json")
    from ts_knowledge_agent.services.indexing import index_converted

    index_converted(settings)
    return settings


def _client(monkeypatch, tmp_path, script):
    settings = _settings(tmp_path)
    monkeypatch.setenv("TS_KB_CONFIG", str(settings.working_directory / "ts-kb.json"))
    provider = ScriptedProvider(script)
    monkeypatch.setattr(api_main, "create_provider", lambda settings: provider)
    return TestClient(api_main.app), settings, provider


def test_chat_returns_answer_and_citations(monkeypatch, tmp_path):
    client, _settings_obj, _provider = _client(
        monkeypatch,
        tmp_path,
        [
            ProviderReply(
                content="先检索。",
                tool_calls=[{"id": "c1", "name": "knowledge_search", "arguments": {"query": "架构"}}],
            ),
            ProviderReply(content="## 结论\n组件库采用 Monorepo。\n\n## 依据\n- doc.md"),
        ],
    )

    response = client.post("/api/v1/chat", json={"question": "组件库架构是什么"})

    assert response.status_code == 200
    payload = response.json()
    assert "结论" in payload["answer"]
    assert payload["error"] is None
    assert payload["steps"] == 2
    assert any(path.endswith("doc.md") for path in payload["citations"])


def test_chat_rejects_empty_question(monkeypatch, tmp_path):
    client, _settings_obj, _provider = _client(monkeypatch, tmp_path, [])
    response = client.post("/api/v1/chat", json={"question": "   "})
    assert response.status_code == 400


def test_chat_stream_emits_tool_and_answer_events(monkeypatch, tmp_path):
    client, _settings_obj, _provider = _client(
        monkeypatch,
        tmp_path,
        [
            ProviderReply(
                content="检索中。",
                tool_calls=[{"id": "c1", "name": "knowledge_search", "arguments": {"query": "架构"}}],
            ),
            ProviderReply(content="## 结论\n采用 Monorepo 架构。"),
        ],
    )

    with client.stream("POST", "/api/v1/chat/stream", json={"question": "组件库架构是什么"}) as response:
        assert response.status_code == 200
        body = "".join(chunk for chunk in response.iter_text())

    events = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ") and line != "data: [DONE]"]
    kinds = [event["type"] for event in events]
    assert kinds[0] == "start"
    assert "tool_call" in kinds
    assert "tool_result" in kinds
    assert kinds[-1] == "answer"
    assert "Monorepo" in events[-1]["content"]


def test_config_endpoint_masks_api_key(monkeypatch, tmp_path):
    client, settings, _provider = _client(monkeypatch, tmp_path, [])
    from ts_knowledge_agent.agent.secrets import write_api_key

    write_api_key(settings.working_directory, "gw-test-abcdefghij")
    response = client.get("/api/v1/config")
    assert response.status_code == 200
    payload = response.json()
    assert payload["api_key"].startswith("configured")
    assert "gw-test-abcdefghij" not in json.dumps(payload)


def test_config_endpoint_updates_model_settings(monkeypatch, tmp_path):
    client, settings, _provider = _client(monkeypatch, tmp_path, [])
    response = client.put("/api/v1/config", json={"provider": "ts_proxy", "model": "deepseek-v4-flash", "max_steps": 12})
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "ts_proxy"
    assert payload["model"] == "deepseek-v4-flash"
    assert payload["max_steps"] == 12
    reloaded = Settings.from_file(settings.working_directory / "ts-kb.json")
    assert reloaded.model_max_steps == 12
    assert reloaded.model_name == "deepseek-v4-flash"


def test_chat_reports_missing_provider(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    monkeypatch.setenv("TS_KB_CONFIG", str(settings.working_directory / "ts-kb.json"))
    monkeypatch.setattr(api_main, "create_provider", lambda settings: None)
    client = TestClient(api_main.app)
    response = client.post("/api/v1/chat", json={"question": "你好"})
    assert response.status_code == 503
