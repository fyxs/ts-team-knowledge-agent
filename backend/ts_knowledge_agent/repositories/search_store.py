from __future__ import annotations

import re
import sqlite3
from collections.abc import Sequence

TOKEN_PATTERN = re.compile(r"[0-9A-Za-z_\-\.]+|[\u4e00-\u9fff]{2,}")


def query_tokens(text: str) -> list[str]:
    """把自然语言查询切成检索词：中文字符串与英文/数字词，长度至少 2。"""

    tokens: list[str] = []
    seen: set[str] = set()
    for token in TOKEN_PATTERN.findall(text or ""):
        token = token.strip()
        if len(token) < 2 or token.lower() in seen:
            continue
        seen.add(token.lower())
        tokens.append(token)
    return tokens


def fts_query(tokens: Sequence[str], mode: str = "and") -> str:
    """构造安全的 FTS5 查询：逐词加引号，避免被当成列名或语法错误。"""

    quoted = ["\"" + token.replace("\"", "\"\"") + "\"" for token in tokens]
    return (" AND " if mode == "and" else " OR ").join(quoted)

import sqlite3
from pathlib import Path


def clean_text(value: str) -> str:
    return value.lstrip("\ufeff")


class SearchStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            path TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            content_sha256 TEXT NOT NULL,
            indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
            path UNINDEXED, title, content
        );
        """)
        self.connection.commit()

    def upsert(self, path: str, title: str, content: str, sha256: str) -> None:
        title, content = clean_text(title), clean_text(content)
        self.connection.execute("DELETE FROM documents_fts WHERE path = ?", (path,))
        self.connection.execute("""INSERT INTO documents(path,title,content,content_sha256)
            VALUES(?,?,?,?) ON CONFLICT(path) DO UPDATE SET title=excluded.title,
            content=excluded.content, content_sha256=excluded.content_sha256,
            indexed_at=CURRENT_TIMESTAMP""", (path,title,content,sha256))
        self.connection.execute("INSERT INTO documents_fts(path,title,content) VALUES(?,?,?)", (path,title,content))
        self.connection.commit()

    def _match(self, expression: str, limit: int) -> list[sqlite3.Row]:
        """执行一次 FTS5 MATCH，按 bm25 相关性排序；表达式非法时返回空列表。"""

        if not expression:
            return []
        statement = (
            "SELECT path, title, snippet(documents_fts, 2, '[', ']', '...', 24) AS snippet "
            "FROM documents_fts WHERE documents_fts MATCH ? ORDER BY bm25(documents_fts) LIMIT ?"
        )
        try:
            return list(self.connection.execute(statement, (expression, limit)))
        except sqlite3.OperationalError:
            return []

    def search(self, query: str, limit: int = 10) -> list[sqlite3.Row]:
        """FTS5 检索：先按全部检索词 AND 精确匹配，再用 OR 补齐，均按相关性排序。"""

        tokens = query_tokens(query)
        if not tokens:
            return []
        rows = self._match(fts_query(tokens, "and"), limit)
        if len(rows) >= limit:
            return rows
        seen = {row["path"] for row in rows}
        for row in self._match(fts_query(tokens, "or"), limit * 2):
            if row["path"] in seen:
                continue
            seen.add(row["path"])
            rows.append(row)
            if len(rows) >= limit:
                break
        return rows[:limit]

    def search_like(self, query: str, limit: int = 10) -> list[sqlite3.Row]:
        """兼容入口：按查询词做子串匹配。"""

        return self.search_tokens(query_tokens(query), limit)

    def search_tokens(self, tokens: list[str], limit: int = 10) -> list[sqlite3.Row]:
        """按检索词做子串匹配，命中词数多的优先（FTS 未命中时的兜底）。"""

        tokens = [token for token in tokens if token]
        if not tokens:
            return []
        score = " + ".join(["(content LIKE ?) + (title LIKE ?)"] * len(tokens))
        params: list = []
        for token in tokens:
            params.extend([f"%{token}%", f"%{token}%"])
        params.append(limit)
        return list(self.connection.execute(
            f"SELECT * FROM (SELECT path, title, content, ({score}) AS score FROM documents) "
            "WHERE score > 0 ORDER BY score DESC, path LIMIT ?",
            params))

    def list_paths(self) -> list[str]:
        return [row["path"] for row in self.connection.execute("SELECT path FROM documents")]

    def delete_paths(self, paths: list[str]) -> int:
        for path in paths:
            self.connection.execute("DELETE FROM documents WHERE path = ?", (path,))
            self.connection.execute("DELETE FROM documents_fts WHERE path = ?", (path,))
        self.connection.commit()
        return len(paths)

    def close(self) -> None:
        self.connection.close()
