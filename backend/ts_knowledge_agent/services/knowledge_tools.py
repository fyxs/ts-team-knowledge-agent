from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.repositories.search_store import SearchStore, query_tokens
from ts_knowledge_agent.repositories.state_store import SUCCESS_STATUSES, WARNING_STATUSES, StateStore

SNIPPET_WIDTH = 80


@dataclass(frozen=True)
class KnowledgeHit:
    path: str
    title: str
    snippet: str
    matched_by: str


@dataclass(frozen=True)
class KnowledgeDocument:
    path: str
    title: str
    content: str
    offset: int
    returned_lines: int
    total_lines: int
    truncated: bool


def _member_prefix(member: str | None) -> str:
    return f"members/{member}/" if member else "members/"


def _search_store(settings: Settings) -> SearchStore:
    return SearchStore(settings.shared_knowledge_repository_directory / "data" / "state.sqlite3")


def _snippet(content: str, query: str, width: int = SNIPPET_WIDTH) -> str:
    flat = content.replace("\r", " ").replace("\n", " ")
    index = flat.find(query)
    if index < 0:
        return flat[: width * 2].strip()
    start = max(0, index - width // 2)
    end = min(len(flat), index + len(query) + width // 2)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(flat) else ""
    return f"{prefix}{flat[start:end].strip()}{suffix}"


def knowledge_search(settings: Settings, query: str, limit: int = 5, member: str | None = None) -> list[KnowledgeHit]:
    """检索知识库：先用 FTS5 分词匹配，再用子串匹配补齐中文召回。"""

    query = (query or "").strip()
    if not query:
        raise ValueError("query must not be empty")
    if limit < 1:
        raise ValueError("limit must be at least 1")
    prefix = _member_prefix(member)
    store = _search_store(settings)
    try:
        hits: list[KnowledgeHit] = []
        seen: set[str] = set()
        for row in store.search(query, limit * 3):
            if not row["path"].startswith(prefix) or row["path"] in seen:
                continue
            hits.append(KnowledgeHit(row["path"], row["title"], row["snippet"] or "", "fts"))
            seen.add(row["path"])
        if len(hits) < limit:
            for row in store.search_like(query, limit * 4):
                if not row["path"].startswith(prefix) or row["path"] in seen:
                    continue
                terms = query_tokens(query)
                best = max(terms, key=len) if terms else query
                hits.append(KnowledgeHit(row["path"], row["title"], _snippet(row["content"], best), "substring"))
                seen.add(row["path"])
        return hits[:limit]
    finally:
        store.close()


def knowledge_read(settings: Settings, path: str, offset: int = 0, limit: int = 200) -> KnowledgeDocument:
    """读取知识文档的分页内容，路径必须位于知识仓 members/ 之下。"""

    if offset < 0:
        raise ValueError("offset must not be negative")
    if limit < 1:
        raise ValueError("limit must be at least 1")
    repo = settings.shared_knowledge_repository_directory.resolve()
    target = (repo / path).resolve()
    if not target.is_relative_to(repo / "members"):
        raise ValueError(f"path must stay inside the members directory: {path}")
    if target.suffix.lower() != ".md":
        raise ValueError(f"only markdown knowledge can be read: {path}")
    if not target.is_file():
        raise FileNotFoundError(f"knowledge document does not exist: {path}")
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    window = lines[offset : offset + limit]
    title = next((line[2:].strip() for line in lines if line.startswith("# ")), target.stem)
    return KnowledgeDocument(
        path=target.relative_to(repo).as_posix(),
        title=title,
        content="\n".join(window),
        offset=offset,
        returned_lines=len(window),
        total_lines=len(lines),
        truncated=offset + len(window) < len(lines),
    )


def knowledge_list(settings: Settings, member: str | None = None, prefix: str | None = None, limit: int = 200) -> list[dict[str, str]]:
    """列出已索引的知识文档。"""

    if limit < 1:
        raise ValueError("limit must be at least 1")
    path_prefix = prefix or _member_prefix(member)
    store = _search_store(settings)
    try:
        rows = store.connection.execute(
            "SELECT path, title FROM documents WHERE path LIKE ? ORDER BY path LIMIT ?",
            (f"{path_prefix}%", limit),
        ).fetchall()
        return [{"path": row["path"], "title": row["title"]} for row in rows]
    finally:
        store.close()


def knowledge_status(settings: Settings) -> dict[str, object]:
    """返回知识库健康概览：状态计数与失败清单。"""

    store = StateStore(settings.shared_knowledge_repository_directory / "data" / "state.sqlite3")
    try:
        source_counts: dict[str, int] = {}
        for row in store.list_sources():
            source_counts[row["status"]] = source_counts.get(row["status"], 0) + 1
        failures = [
            {"path": row["relative_path"], "status": row["status"], "error": (row["error_message"] or "")[:400]}
            for row in store.list_conversions()
            if row["status"] not in SUCCESS_STATUSES
        ]
        warnings = [
            {"path": row["relative_path"], "status": row["status"], "warning": (row["warning_message"] or "")[:400]}
            for row in store.list_conversions()
            if row["status"] in WARNING_STATUSES
        ]
        return {
            "personal_workspace": settings.personal_workspace,
            "sources": source_counts,
            "total_sources": sum(source_counts.values()),
            "open_issues": len(failures),
            "failures": failures,
            "open_warnings": len(warnings),
            "warnings": warnings,
        }
    finally:
        store.close()
