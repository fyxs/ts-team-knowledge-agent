from __future__ import annotations

import hashlib
from pathlib import Path
from dataclasses import dataclass

from ts_knowledge_agent.services.converter import is_supported

@dataclass(frozen=True)
class SourceFile:
    relative_path: str
    absolute_path: Path
    size: int
    mtime_ns: int
    sha256: str
    supported: bool = True


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def scan_directory(root: Path) -> list[SourceFile]:
    root = root.expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"source directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"source path is not a directory: {root}")
    results: list[SourceFile] = []
    for path in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: str(p).lower()):
        stat = path.stat()
        results.append(SourceFile(str(path.relative_to(root)), path, stat.st_size, stat.st_mtime_ns, sha256_file(path), is_supported(path)))
    return results