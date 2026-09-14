from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ts_knowledge_agent.api.main import mount_web, resolve_web_dist
from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.services.preflight import (
    format_report,
    has_blocking_errors,
    run_preflight,
)


def _settings(tmp_path: Path, mineru: Path | None = None) -> Settings:
    source = tmp_path / "source"
    source.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    return Settings("whm", source, tmp_path / "work", repo, 60, mineru_python=mineru)


def _dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<div id=\"root\"></div>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    return dist


def test_preflight_reports_ready_environment(tmp_path):
    dist = _dist(tmp_path)
    settings = _settings(tmp_path)
    results = run_preflight(settings, web_dist=dist)

    levels = {result.name: result.level for result in results}
    assert levels["源目录"] == "ok"
    assert levels["共享知识仓"] == "ok"
    assert levels["前端产物"] == "ok"
    # 未配置模型与 MinerU 记为警告，不阻塞启动
    assert levels["模型配置"] == "warn"
    assert levels["MinerU 解释器"] == "warn"
    assert has_blocking_errors(results) is False


def test_preflight_blocks_when_source_missing(tmp_path):
    settings = _settings(tmp_path)
    settings.shared_source_directory.rmdir()
    results = run_preflight(settings, web_dist=_dist(tmp_path))

    assert has_blocking_errors(results) is True
    report = format_report(results)
    assert "源目录" in report
    assert "[error]" in report


def test_preflight_blocks_when_mineru_path_is_wrong(tmp_path):
    settings = _settings(tmp_path, mineru=tmp_path / "missing-python.exe")
    results = run_preflight(settings, web_dist=_dist(tmp_path))
    assert has_blocking_errors(results) is True
    assert any(result.name == "MinerU 解释器" and result.level == "error" for result in results)


def test_preflight_warns_without_web_dist(tmp_path):
    results = run_preflight(_settings(tmp_path), web_dist=None)
    assert any(result.name == "前端产物" and result.level == "warn" for result in results)


def test_mount_web_serves_index_and_assets(tmp_path):
    dist = _dist(tmp_path)
    application = FastAPI()

    @application.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    mount_web(application, dist)
    client = TestClient(application)

    assert client.get("/api/v1/health").json() == {"status": "ok"}
    root = client.get("/")
    assert root.status_code == 200
    assert "root" in root.text
    assert client.get("/assets/app.js").status_code == 200
    # 未知路径回落到前端入口，而不是 404
    assert client.get("/some/deep/route").status_code == 200


def test_resolve_web_dist_respects_env(tmp_path, monkeypatch):
    dist = _dist(tmp_path)
    monkeypatch.setenv("TS_KB_WEB_DIST", str(dist))
    assert resolve_web_dist() == dist

    monkeypatch.setenv("TS_KB_WEB_DIST", str(tmp_path / "nope"))
    assert resolve_web_dist() is None
