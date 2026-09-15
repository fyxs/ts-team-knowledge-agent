from __future__ import annotations

import re
import sqlite3
from collections.abc import Sequence

TOKEN_PATTERN = re.compile(r"[0-9A-Za-z_\-\.]+|[\u4e00-\u9fff]{2,}")

RRF_K = 60
TITLE_WEIGHT = 8.0
CONTENT_WEIGHT = 3.0


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
        """执行一次 FTS5 MATCH，按带列权重的 bm25 排序；表达式非法时返回空列表。"""

        if not expression:
            return []
        statement = (
            "SELECT path, title, snippet(documents_fts, 2, '[', ']', '...', 24) AS snippet "
            "FROM documents_fts WHERE documents_fts MATCH ? "
            "ORDER BY bm25(documents_fts, 0.0, %.1f, %.1f) LIMIT ?" % (TITLE_WEIGHT, CONTENT_WEIGHT)
        )
        try:
            return list(self.connection.execute(statement, (expression, limit)))
        except sqlite3.OperationalError:
            return []

    def _path_hits(self, tokens: list[str], limit: int) -> list[dict]:
        """路径召回：路径里的项目名/模块名往往就是检索词。

        按文档频率做 IDF 抑制——像仓库名这类在大量路径中出现的词，命中它并不能说明
        这篇文档更相关；只有稀有项目名才应显著提升排序。
        """

        tokens = [token for token in tokens if token]
        if not tokens:
            return []
        rows = list(self.connection.execute("SELECT path, title FROM documents"))
        lower_paths = [(row["path"], row["title"], row["path"].lower()) for row in rows]
        frequency = {
            token: max(1, sum(1 for _, _, path in lower_paths if token.lower() in path))
            for token in tokens
        }
        scored: list[dict] = []
        for path, title, path_lower in lower_paths:
            score = sum(1.0 / frequency[token] for token in tokens if token.lower() in path_lower)
            if score > 0:
                scored.append({"path": path, "title": title, "snippet": "", "score": score})
        scored.sort(key=lambda item: (-item["score"], item["path"]))
        return scored[:limit]

    @staticmethod
    def _fuse(channels: list[list], limit: int) -> list[dict]:
        """RRF 融合多路召回：按 1/(k+rank) 累加，避免单路排序偏置。"""

        scores: dict[str, float] = {}
        rows: dict[str, dict] = {}
        for channel in channels:
            for rank, row in enumerate(channel, 1):
                path = row["path"]
                scores[path] = scores.get(path, 0.0) + 1.0 / (RRF_K + rank)
                existing = rows.get(path)
                snippet = row["snippet"] or ""
                if existing is None or (not existing["snippet"] and snippet):
                    rows[path] = {"path": path, "title": row["title"], "snippet": snippet}
        tiers = [
            {row["path"] for row in channel}
            for channel in channels
        ]

        def tier_of(path: str) -> int:
            for index, members in enumerate(tiers):
                if path in members:
                    return index
            return len(tiers)

        ordered = sorted(
            scores.items(),
            key=lambda item: (tier_of(item[0]), -item[1], item[0]),
        )[:limit]
        return [rows[path] for path, _ in ordered]

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """三路召回融合：FTS AND（精确）+ FTS OR（召回）+ 路径匹配（项目名）。"""

        tokens = query_tokens(query)
        if not tokens:
            return []
        channels = [
            self._match(fts_query(tokens, "and"), limit * 3),
            self._match(fts_query(tokens, "or"), limit * 3),
            self._path_hits(tokens, limit * 3),
        ]
        return self._fuse(channels, limit)

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
