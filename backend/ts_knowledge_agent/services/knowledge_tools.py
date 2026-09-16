from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.repositories.search_store import CJK_RUN, SearchStore, query_tokens
from ts_knowledge_agent.repositories.state_store import SUCCESS_STATUSES, WARNING_STATUSES, StateStore
from ts_knowledge_agent.services.markdown import normalize_html_tables

SNIPPET_WIDTH = 80
# 一篇文档最多报几处命中：够说明「依据在哪一段」，又不至于把来源行堆成清单。
SOURCE_HITS_PER_DOCUMENT = 3
HIT_SNIPPET_WIDTH = 120
# 定位命中要看全文：分页只用于给前端展示，命中必须基于整篇算。
FULL_DOCUMENT_LIMIT = 100_000

MARKDOWN_SUFFIXES = frozenset({".md"})
# 文档内资源的白名单后缀：只放图片，不提供任意文件读。
ASSET_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"})
ASSET_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}


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


@dataclass(frozen=True)
class SourceHit:
    """引用来源里的一处命中：行号与命中行片段。"""

    line: int
    snippet: str

    def to_dict(self) -> dict[str, object]:
        return {"line": self.line, "snippet": self.snippet}


@dataclass(frozen=True)
class KnowledgeSource:
    """结构化引用来源。

    `citations` 的路径字符串按原样保留（CLI 与评测按字符串列表消费），
    这里补上标题与命中位置，供界面把引用变成可点、可定位的行。
    """

    path: str
    title: str
    hits: tuple[SourceHit, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "title": self.title,
            "hits": [hit.to_dict() for hit in self.hits],
        }


def _member_prefix(member: str | None) -> str:
    return f"members/{member}/" if member else "members/"


def _search_store(settings: Settings) -> SearchStore:
    return SearchStore(settings.shared_knowledge_repository_directory / "data" / "state.sqlite3")


def _member_path(settings: Settings, path: str, suffixes: frozenset[str], kind: str) -> Path:
    """把知识仓相对路径解析成绝对路径，并强制留在 members/ 之内。

    边界判断只在这一处：HTTP 出口、CLI 与后续调用方共用同一道闸，
    避免第二个出口各自实现一遍校验而出现口径差异。
    """

    repo = settings.shared_knowledge_repository_directory.resolve()
    target = (repo / path).resolve()
    if not target.is_relative_to(repo / "members"):
        raise ValueError(f"path must stay inside the members directory: {path}")
    if target.suffix.lower() not in suffixes:
        raise ValueError(f"only {kind} can be read: {path}")
    if not target.is_file():
        raise FileNotFoundError(f"knowledge document does not exist: {path}")
    return target


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
    target = _member_path(settings, path, MARKDOWN_SUFFIXES, "markdown knowledge")
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


def knowledge_document(settings: Settings, path: str, offset: int = 0, limit: int = 200) -> KnowledgeDocument:
    """读取给界面展示的文档分页：边界与 `knowledge_read` 完全一致。

    两处与 `knowledge_read` 不同，都是为了「引用能落到正确的那一行」：

    1. 先把原始 HTML 表格规范化为 GFM（否则前端整块丢表）；
    2. 分页切在**规范化之后**的全文上。若先切页再规范化，含多行 HTML 表格的文档会因
       行数变化而与 `locate_sources` 算出的命中行号错位，引用就会跳到别的地方。

    分页参数在这一层自己校验：整篇读进来之后再切片，`knowledge_read` 看不到 offset，
    少了这一步 `offset=-1` 会被静默当成 0。
    """

    if offset < 0:
        raise ValueError("offset must not be negative")
    if limit < 1:
        raise ValueError("limit must be at least 1")
    document = knowledge_read(settings, path, offset=0, limit=FULL_DOCUMENT_LIMIT)
    lines = normalize_html_tables(document.content).splitlines()
    window = lines[offset : offset + limit]
    return replace(
        document,
        content="\n".join(window),
        offset=offset,
        returned_lines=len(window),
        total_lines=len(lines),
        truncated=offset + len(window) < len(lines),
    )


def knowledge_asset(settings: Settings, path: str) -> tuple[Path, str]:
    """解析文档内的相对资源（实测是文档同级 `images/` 下的图片），返回绝对路径与媒体类型。"""

    target = _member_path(settings, path, ASSET_SUFFIXES, "knowledge image")
    return target, ASSET_MEDIA_TYPES.get(target.suffix.lower(), "application/octet-stream")


def _needles(queries: Sequence[str]) -> list[str]:
    """把提问拆成用于定位行的片段。

    没有中文分词器时，`query_tokens` 会把整段中文当成**一个**词元，
    直接拿它去匹配行必然落空；这里额外补一层二元片段，
    让「环境变量」这类复合词能在行内被计分命中，同时保留原词元。
    """

    needles: list[str] = []
    for query in queries:
        for token in query_tokens(query or ""):
            needles.append(token)
            if CJK_RUN.fullmatch(token) and len(token) > 2:
                needles.extend(token[index : index + 2] for index in range(len(token) - 1))
    unique: list[str] = []
    seen: set[str] = set()
    for needle in needles:
        key = needle.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(needle)
    return unique


def _line_snippet(line: str, needles: Sequence[str]) -> str:
    flat = " ".join(line.split())
    present = [needle for needle in needles if needle in flat]
    if not present:
        return flat[:HIT_SNIPPET_WIDTH]
    # 取最长（最具体）的那个片段作为居中锚点，短片段常常只是长片段的一部分。
    anchor = max(present, key=len)
    index = flat.find(anchor)
    start = max(0, index - HIT_SNIPPET_WIDTH // 3)
    end = min(len(flat), index + len(anchor) + HIT_SNIPPET_WIDTH // 2)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(flat) else ""
    return f"{prefix}{flat[start:end].strip()}{suffix}"


def locate_source_hits(
    content: str,
    needles: Sequence[str],
    limit: int = SOURCE_HITS_PER_DOCUMENT,
) -> tuple[SourceHit, ...]:
    """在全文里定位检索片段，返回命中行与片段。

    FTS5 只给带高亮符的字符串、没有位置信息；全文在 `documents.content` 里，
    用它在服务端算行号成本很低，不必改索引结构。

    按「命中片段数」挑行而不是取最前面的匹配行：中文二元片段会让大量行都命中，
    取最前面几行会稳定跳到与问题无关的段落。挑完再按行号升序，便于界面逐处跳转。
    """

    if not needles:
        return ()
    scored: list[tuple[int, int, str]] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            continue
        score = sum(1 for needle in needles if needle in line)
        if score:
            scored.append((score, line_number, line))
    if not scored:
        return ()
    chosen = sorted(sorted(scored, key=lambda item: (-item[0], item[1]))[:limit], key=lambda item: item[1])
    return tuple(SourceHit(line=line, snippet=_line_snippet(text, needles)) for _, line, text in chosen)


def _document_text(settings: Settings, path: str) -> tuple[str, str] | None:
    """取一篇文档的标题与全文：优先索引（被引用的文档必然已入库），索引缺失时回落到磁盘。"""

    store = _search_store(settings)
    try:
        row = store.connection.execute(
            "SELECT title, content FROM documents WHERE path = ?", (path,)
        ).fetchone()
    finally:
        store.close()
    if row is not None:
        return row["title"], row["content"]
    try:
        document = knowledge_read(settings, path, offset=0, limit=FULL_DOCUMENT_LIMIT)
    except (ValueError, FileNotFoundError):
        return None
    return document.title, document.content


def locate_sources(settings: Settings, paths: Sequence[str], queries: Sequence[str]) -> list[KnowledgeSource]:
    """把引用路径补成结构化来源：标题 + 命中行号与片段。

    命中片段在**规范化之后**的正文上算，与 `knowledge_document` 展示的行号同源；
    提问里没有可定位片段（例如模型只读过文档）时不编造命中，`hits` 留空，
    由界面显示为「已引用」。
    """

    needles = _needles(queries)
    sources: list[KnowledgeSource] = []
    for path in paths:
        resolved = _document_text(settings, path)
        if resolved is None:
            # 引用了却读不到：仍登记这条来源，标题退回文件名，不静默丢掉引用。
            sources.append(KnowledgeSource(path=path, title=Path(path).stem))
            continue
        title, content = resolved
        sources.append(
            KnowledgeSource(
                path=path,
                title=title or Path(path).stem,
                hits=locate_source_hits(normalize_html_tables(content), needles),
            )
        )
    return sources


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
