from pathlib import Path

from ts_knowledge_agent.repositories.search_store import SearchStore, fts_query, query_tokens


def test_query_tokens_splits_natural_language():
    tokens = query_tokens("院事通 Agent 的 SSE 协议定义了哪些事件？")
    assert "院事通" in tokens
    assert "Agent" in tokens
    assert "SSE" in tokens
    assert all(len(token) >= 2 for token in tokens)


def test_query_tokens_deduplicates_case_insensitively():
    assert query_tokens("BFF bff BFF") == ["BFF"]


def test_fts_query_quotes_every_token():
    assert fts_query(["空调", "群控"], "and") == '"空调" AND "群控"'
    assert fts_query(["空调", "群控"], "or") == '"空调" OR "群控"'


def test_fts_query_neutralises_column_like_tokens():
    # 自然语言里的普通词曾会被 FTS5 当成列名而抛 OperationalError
    expression = fts_query(query_tokens("如何基于 tdf-bff 新起 BFF 项目"), "and")
    assert expression.startswith('"')
    assert "bff" in expression


def test_search_tolerates_natural_language_query(tmp_path):
    store = SearchStore(tmp_path / "state.sqlite3")
    try:
        store.upsert("members/whm/doc.md", "文档", "如何基于 tdf-bff 新起 BFF 项目的步骤", "d" * 64)
        hits = store.search("如何基于 tdf-bff 新起 BFF 项目", limit=5)
    finally:
        store.close()
    assert [row["path"] for row in hits] == ["members/whm/doc.md"]


def test_search_returns_empty_for_blank_query(tmp_path):
    store = SearchStore(tmp_path / "state.sqlite3")
    try:
        assert store.search("   ", limit=5) == []
    finally:
        store.close()


def test_search_tokens_prefers_documents_matching_more_terms(tmp_path):
    store = SearchStore(tmp_path / "state.sqlite3")
    try:
        store.upsert("members/whm/a.md", "空调", "空调群控 第一阶段 产品设计", "a" * 64)
        store.upsert("members/whm/b.md", "其他", "只有空调两个字", "b" * 64)
        rows = store.search_tokens(["空调", "群控", "产品设计"], limit=5)
    finally:
        store.close()
    assert [row["path"] for row in rows][0] == "members/whm/a.md"


def test_search_like_delegates_to_token_matching(tmp_path):
    store = SearchStore(tmp_path / "state.sqlite3")
    try:
        store.upsert("members/whm/a.md", "规则学习", "规则学习推理服务使用说明", "a" * 64)
        rows = store.search_like("规则学习推理服务-使用说明", limit=5)
    finally:
        store.close()
    assert any(row["path"] == "members/whm/a.md" for row in rows)
