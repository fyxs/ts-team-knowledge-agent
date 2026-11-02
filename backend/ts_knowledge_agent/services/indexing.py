from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path
from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.repositories.search_store import SearchStore
from ts_knowledge_agent.services.member_space import is_knowledge_document

# 仓库说明文件不是成员知识，不进入检索索引。
SKIPPED_RELATIVE_PATHS = frozenset({"members/README.md"})

# 并发写同一个库时（serve + 转换轮），单次 busy 等待之外再重试几次，
# 避免一条记录撞锁就让整轮在 index_converted 处崩掉。
UPSERT_ATTEMPTS = 3


def _upsert_with_retry(store: SearchStore, relative: str, title: str, content: str, digest: str) -> None:
    for attempt in range(UPSERT_ATTEMPTS):
        try:
            store.upsert(relative, title, content, digest)
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == UPSERT_ATTEMPTS - 1:
                raise
            time.sleep(1 + attempt)


def index_converted(settings: Settings) -> int:
    repository = settings.shared_knowledge_repository_directory
    root = repository / "members"
    store = SearchStore(repository / "data" / "state.sqlite3")
    count = 0
    seen: set[str] = set()
    try:
        existing = store.digests()
        if not root.exists():
            store.delete_paths(store.list_paths())
            return 0
        for path in sorted(root.rglob("*.md")):
            relative = path.relative_to(repository).as_posix()
            if relative in SKIPPED_RELATIVE_PATHS or not is_knowledge_document(relative): continue
            content = path.read_text(encoding="utf-8")
            title = next((line[2:].strip() for line in content.splitlines() if line.startswith("# ")), path.stem)
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if existing.get(relative) != digest:
                _upsert_with_retry(store, relative, title, content, digest)
            seen.add(relative)
            count += 1
        stale = [path for path in store.list_paths() if path not in seen]
        if stale:
            store.delete_paths(stale)
        return count
    finally:
        store.close()


def search_converted(settings: Settings, query: str) -> list[dict[str, str]]:
    store = SearchStore(settings.shared_knowledge_repository_directory / "data" / "state.sqlite3")
    try:
        return [dict(row) for row in store.search(query)]
    finally:
        store.close()
