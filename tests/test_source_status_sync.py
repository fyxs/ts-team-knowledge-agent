from pathlib import Path

from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.repositories.state_store import StateStore
from ts_knowledge_agent.services.pipeline import run_once


def test_pipeline_syncs_source_status_with_conversion_status(tmp_path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "ok.md").write_text("# ok\ncontent\n", encoding="utf-8")
    (source_root / "ignored.json").write_text("{}", encoding="utf-8")
    settings = Settings("whm", source_root, tmp_path / "work", tmp_path / "repo", 60)
    settings.working_directory.mkdir()

    summary = run_once(settings, batch_size=10)
    assert summary.converted == 1

    store = StateStore(settings.shared_knowledge_repository_directory / "data" / "state.sqlite3")
    try:
        statuses = {row["relative_path"]: row["status"] for row in store.list_sources()}
    finally:
        store.close()
    assert statuses["ok.md"] == "converted"
    assert statuses["ignored.json"] == "ignored"
