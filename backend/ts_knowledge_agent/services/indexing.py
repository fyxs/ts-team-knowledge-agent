from __future__ import annotations

import hashlib
from pathlib import Path
from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.repositories.search_store import SearchStore

# 仓库说明文件不是成员知识，不进入检索索引。
SKIPPED_RELATIVE_PATHS = frozenset({"members/README.md"})


def index_converted(settings: Settings) -> int:
    repository = settings.shared_knowledge_repository_directory
    root = repository / "members"
    store = SearchStore(repository / "data" / "state.sqlite3")
    count = 0
    seen: set[str] = set()
    try:
        if not root.exists():
            store.delete_paths(store.list_paths())
            return 0
        for path in sorted(root.rglob("*.md")):
            relative = path.relative_to(repository).as_posix()
            if relative in SKIPPED_RELATIVE_PATHS: continue
            content = path.read_text(encoding="utf-8")
            title = next((line[2:].strip() for line in content.splitlines() if line.startswith("# ")), path.stem)
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            store.upsert(relative, title, content, digest)
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
