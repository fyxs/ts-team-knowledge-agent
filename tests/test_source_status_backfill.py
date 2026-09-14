from pathlib import Path

from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.repositories.state_store import StateStore
from ts_knowledge_agent.services.pipeline import run_once
from ts_knowledge_agent.services.scanner import SourceFile

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def _source(relative_path: str = "doc.md", sha256: str = HASH_A) -> SourceFile:
    return SourceFile(relative_path, Path("C:/tmp") / relative_path, 10, 1, sha256)


def _statuses(store: StateStore) -> dict[str, str]:
    return {row["relative_path"]: row["status"] for row in store.list_sources()}


def test_upsert_source_preserves_existing_status(tmp_path):
    store = StateStore(tmp_path / "state.sqlite3")
    try:
        store.upsert_source(_source())
        store.update_source_status("doc.md", "converted")
        store.upsert_source(_source())
        statuses = _statuses(store)
    finally:
        store.close()
    assert statuses["doc.md"] == "converted"


def test_upsert_source_resets_status_when_content_changed(tmp_path):
    store = StateStore(tmp_path / "state.sqlite3")
    try:
        store.upsert_source(_source())
        store.update_source_status("doc.md", "converted")
        store.upsert_source(_source(sha256=HASH_B))
        statuses = _statuses(store)
    finally:
        store.close()
    assert statuses["doc.md"] == "discovered"


def test_backfill_source_status_from_conversions(tmp_path):
    store = StateStore(tmp_path / "state.sqlite3")
    try:
        store.upsert_source(_source())
        store.record_conversion("doc.md", HASH_A, tmp_path / "doc" / "doc.md", "mineru-3.4.5", "converted")
        updated = store.backfill_source_statuses()
        statuses = _statuses(store)
    finally:
        store.close()
    assert updated == 1
    assert statuses["doc.md"] == "converted"


def test_backfill_ignores_conversion_with_different_source_hash(tmp_path):
    store = StateStore(tmp_path / "state.sqlite3")
    try:
        store.upsert_source(_source())
        store.record_conversion("doc.md", HASH_C, tmp_path / "doc" / "doc.md", "mineru-3.4.5", "converted")
        updated = store.backfill_source_statuses()
        statuses = _statuses(store)
    finally:
        store.close()
    assert updated == 0
    assert statuses["doc.md"] == "discovered"


class CleanConverter:
    def convert(self, source: Path) -> str:
        return "# clean document\n\n" + "clean knowledge content with enough detail. " * 4


def test_pipeline_keeps_source_status_across_runs(tmp_path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "doc.md").write_text("# doc\n", encoding="utf-8")
    settings = Settings("whm", source_root, tmp_path / "work", tmp_path / "repo", 60)
    settings.working_directory.mkdir(parents=True, exist_ok=True)

    first = run_once(settings, batch_size=5, converter=CleanConverter())
    second = run_once(settings, batch_size=5, converter=CleanConverter())

    assert first.converted == 1
    assert second.skipped >= 1

    store = StateStore(settings.shared_knowledge_repository_directory / "data" / "state.sqlite3")
    try:
        statuses = _statuses(store)
    finally:
        store.close()
    assert statuses["doc.md"] == "converted"
