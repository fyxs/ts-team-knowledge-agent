from pathlib import Path

from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.repositories.state_store import StateStore
from ts_knowledge_agent.services.pipeline import run_once


class CleanConverter:
    def convert(self, source: Path) -> str:
        return "# 文档\n\n这是一份足够长的测试知识内容，用于通过质量门禁检查。\n" * 2


def _settings(tmp_path: Path, excluded: tuple[str, ...]) -> Settings:
    source = tmp_path / "source"
    source.mkdir()
    (source / "README.md").write_text("# 空间说明\n\n这里说明源目录用途。\n", encoding="utf-8")
    (source / "doc.md").write_text("# 文档\n\n正文内容。\n", encoding="utf-8")
    settings = Settings(
        "whm", source, tmp_path / "work", tmp_path / "repo", 60, excluded_source_paths=excluded
    )
    settings.working_directory.mkdir(parents=True, exist_ok=True)
    return settings


def test_excluded_source_is_not_converted(tmp_path):
    settings = _settings(tmp_path, ("README.md",))

    summary = run_once(settings, batch_size=10, converter=CleanConverter())

    assert summary.converted == 1
    assert summary.reason_counts.get("excluded") == 1
    repo = settings.shared_knowledge_repository_directory / "members" / "whm"
    assert not (repo / "README").exists(), "excluded source must not produce knowledge output"
    assert (repo / "doc" / "doc.md").is_file()


def test_excluded_source_is_marked_ignored_in_state(tmp_path):
    settings = _settings(tmp_path, ("README.md",))

    run_once(settings, batch_size=10, converter=CleanConverter())

    store = StateStore(settings.shared_knowledge_repository_directory / "data" / "state.sqlite3")
    try:
        statuses = {row["relative_path"]: row["status"] for row in store.list_sources()}
    finally:
        store.close()
    assert statuses["README.md"] == "ignored"


def test_without_exclusion_source_is_converted(tmp_path):
    settings = _settings(tmp_path, ())

    summary = run_once(settings, batch_size=10, converter=CleanConverter())

    assert summary.converted == 2
    assert not summary.reason_counts.get("excluded")
