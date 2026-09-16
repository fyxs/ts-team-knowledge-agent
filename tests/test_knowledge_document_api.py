from fastapi.testclient import TestClient

from ts_knowledge_agent.api import main as api_main
from ts_knowledge_agent.config import Settings

TABLE_DOC = """# 群控评估

## 可控性

<table><tr><td>A</td><td>B</td></tr><tr><td rowspan=2 colspan=1>1</td><td>2</td></tr></table>

结论如上。
"""

PLAIN_DOC = """# 组件库架构

采用 Monorepo 管理多端组件。
"""


def _settings(tmp_path) -> Settings:
    repo = tmp_path / "repo"
    folder = repo / "members" / "whm" / "docs"
    folder.mkdir(parents=True)
    (folder / "table.md").write_text(TABLE_DOC, encoding="utf-8")
    (folder / "plain.md").write_text(PLAIN_DOC, encoding="utf-8")
    (folder / "note.txt").write_text("not markdown", encoding="utf-8")
    images = folder / "images"
    images.mkdir()
    (images / "shot.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 16)
    source = tmp_path / "source"
    source.mkdir()
    settings = Settings("whm", source, tmp_path / "work", repo, 5)
    settings.working_directory.mkdir(parents=True, exist_ok=True)
    settings.write_file(settings.working_directory / "ts-kb.json")
    from ts_knowledge_agent.services.indexing import index_converted

    index_converted(settings)
    return settings


def _client(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    monkeypatch.setenv("TS_KB_CONFIG", str(settings.working_directory / "ts-kb.json"))
    return TestClient(api_main.app), settings


def test_document_endpoint_pages_content(monkeypatch, tmp_path):
    client, _settings_obj = _client(monkeypatch, tmp_path)

    response = client.get("/api/v1/knowledge/document", params={"path": "members/whm/docs/plain.md"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["title"].startswith("组件库架构")
    assert payload["offset"] == 0
    assert payload["total_lines"] >= 3
    assert payload["returned_lines"] == payload["total_lines"]
    assert payload["truncated"] is False

    window = client.get(
        "/api/v1/knowledge/document",
        params={"path": "members/whm/docs/plain.md", "offset": 2, "limit": 1},
    ).json()
    assert window["offset"] == 2
    assert window["returned_lines"] == 1
    assert window["content"] == "采用 Monorepo 管理多端组件。"
    # 取到最后一行为止就不算截断
    assert window["truncated"] is False

    middle = client.get(
        "/api/v1/knowledge/document",
        params={"path": "members/whm/docs/plain.md", "offset": 1, "limit": 1},
    ).json()
    assert middle["returned_lines"] == 1
    assert middle["truncated"] is True


def test_document_endpoint_normalizes_html_table(monkeypatch, tmp_path):
    client, settings = _client(monkeypatch, tmp_path)

    payload = client.get("/api/v1/knowledge/document", params={"path": "members/whm/docs/table.md"}).json()

    # MinerU 的原始 <table> 换成 GFM 管道表：前端只用 remark-gfm，否则这 10 篇会整块丢表。
    assert "<table" not in payload["content"]
    assert "| A | B |" in payload["content"]
    assert "| --- | --- |" in payload["content"]
    # rowspan 在 GFM 里无法表达：属性丢掉，但单元格文字不能丢。
    assert "| 1 | 2 |" in payload["content"]

    # 索引与 agent 读到的内容保持原样：呈现层只在给人看的这条出口上做。
    raw = (settings.shared_knowledge_repository_directory / "members" / "whm" / "docs" / "table.md").read_text(encoding="utf-8")
    assert "<table" in raw


def test_document_endpoint_rejects_escape_and_non_markdown(monkeypatch, tmp_path):
    client, _settings_obj = _client(monkeypatch, tmp_path)

    for bad in ["../../etc/passwd", "/etc/passwd", "members/whm/docs/note.txt"]:
        response = client.get("/api/v1/knowledge/document", params={"path": bad})
        assert response.status_code == 400, bad

    missing = client.get("/api/v1/knowledge/document", params={"path": "members/whm/docs/gone.md"})
    assert missing.status_code == 404

    negative = client.get(
        "/api/v1/knowledge/document",
        params={"path": "members/whm/docs/plain.md", "offset": -1},
    )
    assert negative.status_code == 400


def test_asset_endpoint_serves_only_whitelisted_images(monkeypatch, tmp_path):
    client, _settings_obj = _client(monkeypatch, tmp_path)

    ok = client.get("/api/v1/knowledge/asset", params={"path": "members/whm/docs/images/shot.png"})
    assert ok.status_code == 200
    assert ok.headers["content-type"] == "image/png"
    assert ok.content.startswith(b"\x89PNG")

    assert client.get("/api/v1/knowledge/asset", params={"path": "members/whm/docs/note.txt"}).status_code == 400
    assert client.get("/api/v1/knowledge/asset", params={"path": "../../secret.png"}).status_code == 400
    assert client.get("/api/v1/knowledge/asset", params={"path": "members/whm/docs/images/gone.png"}).status_code == 404
