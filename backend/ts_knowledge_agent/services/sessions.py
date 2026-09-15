"""本机会话存储：会话元信息与消息（含检索引用与工具过程）。

会话属于个人使用痕迹，只写本机 SQLite，不进入共享知识仓。
"""

from __future__ import annotations

import json
import re
import sqlite3
from ts_knowledge_agent.repositories.search_store import expanded_tokens, fts_query
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SESSIONS_DATABASE = "sessions.sqlite3"
TITLE_LIMIT = 20
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


def _searchable_text(payload: dict) -> str:
    """可检索文本：用户提问、回答正文、错误信息；工具过程与元数据不进索引。"""

    for key in ("content", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ''


CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
CJK_MIN_BIGRAM_LENGTH = 3


def _indexable_text(text: str) -> str:
    """索引侧做中文二元展开，与查询侧的 expanded_tokens 对称。

    没有中文分词器时，长中文串会被 FTS 当成一个词元，两字关键词（如「网关」）永远召不回；
    补上相邻二元片段后，查询与索引两侧才在同一粒度上匹配。
    """

    extras: list[str] = []
    for run in CJK_RUN.findall(text):
        if len(run) >= CJK_MIN_BIGRAM_LENGTH:
            extras.extend(run[index:index + 2] for index in range(len(run) - 1))
    if not extras:
        return text
    return text + " " + " ".join(dict.fromkeys(extras))


def _snippet(text: str, tokens: list[str], width: int = 30) -> str:
    """以首个命中的检索词为中心截取片段；片段取自原始文本，不含索引用的二元尾巴。"""

    lowered = text.lower()
    position = -1
    for token in tokens:
        found = lowered.find(token.lower())
        if found != -1 and (position == -1 or found < position):
            position = found
    if position == -1:
        clipped = text[: width * 2]
        return clipped + ("..." if len(text) > len(clipped) else "")
    start = max(0, position - width)
    end = min(len(text), position + width)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"


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
        self._init_message_index()

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
        """重命名：与首条提问共用同一套规范化（压缩空白 + 截断到标题上限）。"""

        normalized = session_title_from(title or "", limit=TITLE_LIMIT)
        self.connection.execute("UPDATE sessions SET title = ? WHERE id = ?", (normalized, session_id))
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
        message_id = int(cursor.lastrowid)
        searchable = _searchable_text(payload)
        if searchable:
            self.connection.execute(
                "INSERT INTO messages_fts(content, session_id, message_id, kind) VALUES(?,?,?,?)",
                (_indexable_text(searchable), session_id, message_id, kind),
            )
        self.connection.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?", (_now_ms(), session_id)
        )
        self.connection.commit()
        return message_id

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

    def _init_message_index(self) -> None:
        """消息全文索引：与 messages 表同库，按会话删除时一并清理。"""

        self.connection.executescript(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                content,
                session_id UNINDEXED,
                message_id UNINDEXED,
                kind UNINDEXED
            );
            """
        )
        self.connection.commit()
        if int(self.connection.execute("SELECT COUNT(*) AS n FROM messages_fts").fetchone()["n"]) == 0:
            self._backfill_message_index()

    def _backfill_message_index(self) -> None:
        """历史消息补建索引：索引为空时按 messages 表重建一次。"""

        self.connection.execute("DELETE FROM messages_fts")
        rows = self.connection.execute(
            "SELECT id, session_id, kind, payload FROM messages ORDER BY id"
        ).fetchall()
        for row in rows:
            payload = json.loads(row["payload"] or "{}")
            searchable = _searchable_text(payload)
            if searchable:
                self.connection.execute(
                    "INSERT INTO messages_fts(content, session_id, message_id, kind) VALUES(?,?,?,?)",
                    (_indexable_text(searchable), row["session_id"], row["id"], row["kind"]),
                )
        self.connection.commit()

    def search_messages(self, query: str, limit: int = 20) -> list[dict]:
        """在会话历史里按关键词检索；中文按二元片段扩展，避免整句无法命中。"""

        tokens = expanded_tokens(query or "")
        if not tokens:
            return []
        statement = (
            "SELECT m.session_id AS session_id, m.message_id AS message_id, m.kind AS kind, "
            "msg.payload AS payload, s.title AS session_title, s.updated_at AS updated_at "
            "FROM messages_fts m "
            "JOIN sessions s ON s.id = m.session_id "
            "JOIN messages msg ON msg.id = m.message_id "
            "WHERE messages_fts MATCH ? ORDER BY bm25(messages_fts) LIMIT ?"
        )
        try:
            rows = self.connection.execute(statement, (fts_query(tokens, "or"), limit)).fetchall()
        except sqlite3.OperationalError:
            return []
        hits: list[dict] = []
        for row in rows:
            payload = json.loads(row["payload"] or "{}")
            hits.append(
                {
                    "session_id": row["session_id"],
                    "session_title": row["session_title"],
                    "message_id": row["message_id"],
                    "kind": row["kind"],
                    "snippet": _snippet(_searchable_text(payload), tokens),
                    "updatedAt": row["updated_at"],
                }
            )
        return hits

    def delete_session(self, session_id: str) -> None:
        self.connection.execute("DELETE FROM messages_fts WHERE session_id = ?", (session_id,))
        self.connection.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        self.connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()


def session_database_path(working_directory: Path) -> Path:
    return Path(working_directory) / "data" / SESSIONS_DATABASE
