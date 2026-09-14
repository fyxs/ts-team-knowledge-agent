from pathlib import Path

from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.repositories.state_store import StateStore
from ts_knowledge_agent.services.indexing import index_converted
from ts_knowledge_agent.services.knowledge_tools import (
    knowledge_list,
    knowledge_read,
    knowledge_search,
    knowledge_status,
)

ARCH = "# 移动端整体架构与开发指南\n\n本文介绍团队知识库的架构设计与前端规范。\n"
OTHER = "# 其他成员文档\n\n这是另一个成员空间的内容。\n"


def _settings(tmp_path: Path) -> Settings:
    repo = tmp_path / "repo"
    own = repo / "members" / "whm" / "研发指南" / "架构"
    own.mkdir(parents=True)
    (own / "架构.md").write_text(ARCH, encoding="utf-8")
    folder = own / "images"
    folder.mkdir()
    other = repo / "members" / "other" / "docs"
    other.mkdir(parents=True)
    (other / "other.md").write_text(OTHER, encoding="utf-8")
    source = tmp_path / "source"
    source.mkdir()
    settings = Settings("whm", source, tmp_path / "work", repo, 60)
    settings.working_directory.mkdir(parents=True, exist_ok=True)
    index_converted(settings)
    return settings


def test_index_covers_every_member_space(tmp_path):
    settings = _settings(tmp_path)
    paths = {row["path"] for row in knowledge_list(settings)}
    assert "members/whm/研发指南/架构/架构.md" in paths
    assert "members/other/docs/other.md" in paths


def test_search_finds_chinese_substring_that_fts_misses(tmp_path):
    settings = _settings(tmp_path)
    hits = knowledge_search(settings, "知识库")
    assert hits, "中文子串检索必须有召回"
    assert hits[0].path == "members/whm/研发指南/架构/架构.md"
    assert "知识库" in hits[0].snippet


def test_search_respects_member_filter(tmp_path):
    settings = _settings(tmp_path)
    assert knowledge_search(settings, "成员空间", member="other")
    assert not knowledge_search(settings, "成员空间", member="whm")


def test_search_rejects_empty_query(tmp_path):
    settings = _settings(tmp_path)
    try:
        knowledge_search(settings, "   ")
    except ValueError as exc:
        assert "query" in str(exc)
    else:
        raise AssertionError("empty query was accepted")


def test_read_paginates_and_reports_truncation(tmp_path):
    settings = _settings(tmp_path)
    document = knowledge_read(settings, "members/whm/研发指南/架构/架构.md", offset=0, limit=2)
    assert document.title.startswith("移动端整体架构")
    assert document.returned_lines == 2
    assert document.total_lines >= 3
    assert document.truncated is True
    rest = knowledge_read(settings, "members/whm/研发指南/架构/架构.md", offset=2, limit=50)
    assert rest.truncated is False


def test_read_rejects_paths_outside_members(tmp_path):
    settings = _settings(tmp_path)
    for bad in ["../escape.md", "data/state.sqlite3", "/etc/passwd"]:
        try:
            knowledge_read(settings, bad)
        except (ValueError, FileNotFoundError):
            continue
        raise AssertionError(f"unsafe path was accepted: {bad}")


def test_read_rejects_non_markdown(tmp_path):
    settings = _settings(tmp_path)
    target = settings.shared_knowledge_repository_directory / "members" / "whm" / "note.txt"
    target.write_text("not markdown", encoding="utf-8")
    try:
        knowledge_read(settings, "members/whm/note.txt")
    except ValueError as exc:
        assert "markdown" in str(exc)
    else:
        raise AssertionError("non-markdown file was accepted")


def test_status_reports_failures(tmp_path):
    settings = _settings(tmp_path)
    store = StateStore(settings.shared_knowledge_repository_directory / "data" / "state.sqlite3")
    try:
        store.connection.execute(
            "INSERT OR REPLACE INTO sources(relative_path,size,mtime_ns,sha256,status) VALUES(?,?,?,?,?)",
            ("broken.pdf", 10, 1, "b" * 64, "quality_failed"),
        )
        store.connection.commit()
        store.record_conversion("broken.pdf", "b" * 64, tmp_path / "x.md", "mineru-3.4.5", "quality_failed", "contains Unicode replacement characters")
    finally:
        store.close()
    status = knowledge_status(settings)
    assert status["total_sources"] == 1
    assert status["open_issues"] == 1
    assert status["failures"][0]["path"] == "broken.pdf"
    assert "Unicode" in status["failures"][0]["error"]
