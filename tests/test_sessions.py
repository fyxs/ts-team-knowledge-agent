from pathlib import Path

from ts_knowledge_agent.services.sessions import (
    DEFAULT_TITLE,
    SessionStore,
    session_title_from,
)


def _store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "sessions.sqlite3")


def test_create_then_list_orders_by_activity(tmp_path):
    store = _store(tmp_path)
    first = store.create_session("会话一")
    second = store.create_session("会话二")
    store.touch_session(first.id)
    listed = store.list_sessions()
    assert [item.id for item in listed][0] == first.id
    assert {item.id for item in listed} == {first.id, second.id}
    store.close()


def test_messages_round_trip_keeps_citations_and_steps(tmp_path):
    store = _store(tmp_path)
    session = store.create_session("问句")
    store.append_message(session.id, "user", {"content": "问句"})
    store.append_message(
        session.id,
        "process",
        {"steps": [{"name": "knowledge_search", "detail": "空调群控", "status": "done"}], "running": False},
    )
    store.append_message(
        session.id,
        "answer",
        {"content": "回答", "citations": ["members/whm/a.md"], "steps": 2, "retrieved": True},
    )
    messages = store.list_messages(session.id)
    assert [item["kind"] for item in messages] == ["user", "process", "answer"]
    assert messages[2]["citations"] == ["members/whm/a.md"]
    assert messages[1]["steps"][0]["name"] == "knowledge_search"
    store.close()


def test_ensure_session_reuses_existing_and_backfills_title(tmp_path):
    store = _store(tmp_path)
    created = store.create_session(DEFAULT_TITLE)
    reused = store.ensure_session(created.id, "新问题")
    assert reused.id == created.id
    assert store.get_session(created.id).title == session_title_from("新问题")
    fresh = store.ensure_session(None, "另一个问题")
    assert fresh.id != created.id
    store.close()


def test_delete_session_removes_messages(tmp_path):
    store = _store(tmp_path)
    session = store.create_session("待删除")
    store.append_message(session.id, "user", {"content": "内容"})
    store.delete_session(session.id)
    assert store.get_session(session.id) is None
    assert store.list_messages(session.id) == []
    store.close()


def test_title_truncates_and_collapses_whitespace():
    assert session_title_from("  多  空格   问题  ") == "多 空格 问题"
    assert len(session_title_from("字" * 80)) == 40
    assert session_title_from("") == DEFAULT_TITLE
