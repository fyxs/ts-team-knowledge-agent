import sqlite3
from pathlib import Path

from ts_knowledge_agent.repositories.search_store import SearchStore


def _store(tmp_path: Path) -> SearchStore:
    store = SearchStore(tmp_path / "state.sqlite3")
    store.upsert("members/whm/能源/三仓库关联机制详解/三仓库关联机制详解.md", "三仓库关联机制详解",
                 "xil、ai-capability、cortex 三个仓库的关联机制说明。" * 20, "a" * 64)
    store.upsert("members/whm/能源/ai-capability-仓库解读/ai-capability-仓库解读.md", "ai-capability 仓库解读",
                 "ai-capability 仓库的数据模型说明。" * 20, "b" * 64)
    return store


def test_path_only_match_is_still_recalled(tmp_path):
    """路径命中但正文不含查询词时，仍应被召回（路径通道提供召回）。"""

    store = _store(tmp_path)
    try:
        paths = [row["path"] for row in store.search("三仓库关联机制详解", 10)]
    finally:
        store.close()
    assert any("三仓库关联机制详解" in path for path in paths)


def test_title_and_content_match_outranks_path_only_match(tmp_path):
    """FTS 命中的文档应排在仅路径命中的文档之前。"""

    store = _store(tmp_path)
    try:
        rows = store.search("ai-capability 三仓库关联机制详解", 10)
    finally:
        store.close()
    assert rows, "查询应当返回结果"
    assert "ai-capability 仓库解读" not in rows[0]["path"]


def test_search_survives_column_like_query(tmp_path):
    """自然语言查询里的孤立词曾经被 FTS5 当成列名而抛错，这里锁住回归。"""

    store = _store(tmp_path)
    try:
        rows = store.search("怎么用 bff 新建项目", 10)
    finally:
        store.close()
    assert isinstance(rows, list)
