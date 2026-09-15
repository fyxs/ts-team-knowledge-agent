"""本机会话存储：会话元信息与消息（含检索引用与工具过程）。

会话属于个人使用痕迹，只写本机 SQLite，不进入共享知识仓。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SESSIONS_DATABASE = "sessions.sqlite3"
TITLE_LIMIT = 40
DEFAULT_TITLE = "新会话"


@dataclass(frozen=True)
class SessionSummary:
    id: str
    title: str
    updated_at: int

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "updatedAt": self.updated_at}


def session_title_from(question: str, limit: int = TITLE_LIMIT) -> str:
    """用首个提问生成会话标题，超出部分截断。"""

    text = " ".join((question or "").split())
    if not text:
        return DEFAULT_TITLE
    return text[:limit]


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


class SessionStore:
    """会话与消息的本地存储。"""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions(
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS messages_by_session ON messages(session_id, id);
            """
        )
        self.connection.commit()

    def create_session(self, title: str = DEFAULT_TITLE) -> SessionSummary:
        stamp = _now_ms()
        session_id = f"s{stamp}{self.connection.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] + 1}"
        self.connection.execute(
            "INSERT INTO sessions(id, title, created_at, updated_at) VALUES(?,?,?,?)",
            (session_id, title or DEFAULT_TITLE, stamp, stamp),
        )
        self.connection.commit()
        return SessionSummary(session_id, title or DEFAULT_TITLE, stamp)

    def list_sessions(self) -> list[SessionSummary]:
        rows = self.connection.execute(
            "SELECT id, title, updated_at FROM sessions ORDER BY updated_at DESC, id DESC"
        )
        return [SessionSummary(row["id"], row["title"], row["updated_at"]) for row in rows]

    def get_session(self, session_id: str) -> SessionSummary | None:
        row = self.connection.execute(
            "SELECT id, title, updated_at FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        return SessionSummary(row["id"], row["title"], row["updated_at"])

    def rename_session(self, session_id: str, title: str) -> None:
        self.connection.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))
        self.connection.commit()

    def touch_session(self, session_id: str) -> None:
        self.connection.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?", (_now_ms(), session_id)
        )
        self.connection.commit()

    def append_message(self, session_id: str, kind: str, payload: dict) -> int:
        cursor = self.connection.execute(
            "INSERT INTO messages(session_id, kind, payload, created_at) VALUES(?,?,?,?)",
            (session_id, kind, json.dumps(payload, ensure_ascii=False), _now_ms()),
        )
        self.connection.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?", (_now_ms(), session_id)
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def list_messages(self, session_id: str) -> list[dict]:
        rows = self.connection.execute(
            "SELECT id, kind, payload FROM messages WHERE session_id = ? ORDER BY id", (session_id,)
        )
        messages: list[dict] = []
        for row in rows:
            try:
                payload = json.loads(row["payload"])
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            messages.append({"id": row["id"], "kind": row["kind"], **payload})
        return messages

    def ensure_session(self, session_id: str | None, question: str) -> SessionSummary:
        """按需创建或复用会话；首条提问用于生成标题。"""

        if session_id:
            existing = self.get_session(session_id)
            if existing is not None:
                if existing.title in ("", DEFAULT_TITLE):
                    self.rename_session(existing.id, session_title_from(question))
                return existing
        return self.create_session(session_title_from(question))

    def delete_session(self, session_id: str) -> None:
        self.connection.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        self.connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()


def session_database_path(working_directory: Path) -> Path:
    return Path(working_directory) / "data" / SESSIONS_DATABASE
