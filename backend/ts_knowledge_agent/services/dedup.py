"""入库前查重：按内容指纹与飞书 obj_token 判定「这份资料是否已经进过库」。

设计边界（v1）：
- 只在**入库前**拦截，不改写、不移动、不删除任何源文件与知识产物。
- 命中重复的源文件状态记为 ``duplicate``，不转换，下一次运行仍稳定跳过。
- 「同一篇飞书文档的新导出取代旧导出」需要移动旧产物，属破坏性动作，
  v1 只在报告里给出 ``newer_export`` 提示，由人决定。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

# 飞书导出的 md 首行带固定格式的 HTML 注释，含文档唯一标识与导出时间。
OBJ_TOKEN = re.compile(r"obj_token=([A-Za-z0-9]{8,})")
EXPORTED_AT = re.compile(r"导出时间=([0-9T:+\-.]{8,})")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
FRONTMATTER = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n", re.S)
WHITESPACE = re.compile(r"\s+")

TEXT_SUFFIXES = frozenset({
    ".md", ".markdown", ".txt", ".csv", ".json", ".yaml", ".yml",
    ".html", ".htm", ".xml", ".log",
})

KIND_FEISHU = "feishu"
KIND_CONTENT = "content"
KIND_BINARY = "binary"


@dataclass(frozen=True)
class Fingerprint:
    """一个源文件的判重标识。

    ``value`` 是主键（飞书取 obj_token，其余取规范化内容哈希）；
    ``content_sha256`` 始终可用（二进制取原始 sha256），用于跨类型比对
    ——原始资料与飞书导出同一篇时必须能撞上。
    """

    kind: str
    value: str
    exported_at: str = ""
    content_sha256: str = ""


@dataclass(frozen=True)
class DuplicateGroup:
    key: str
    kind: str
    canonical: str
    members: tuple[str, ...]
    newer_export: tuple[str, ...] = ()

    @property
    def duplicates(self) -> tuple[str, ...]:
        return tuple(m for m in self.members if m != self.canonical)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def normalized_content_sha256(text: str) -> str:
    """剥掉导出注释、frontmatter 与空白后取哈希。

    飞书每次导出的注释里都带导出时间，直接对字节取哈希会把同一篇文档
    的两次导出算成两份不同内容；这里先剔除这部分噪声。
    """

    text = HTML_COMMENT.sub("", text)
    text = FRONTMATTER.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = WHITESPACE.sub(" ", text).strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fingerprint_file(path: Path, fallback_sha256: str = "") -> Fingerprint:
    """算一个源文件的判重标识。

    ``fallback_sha256`` 由扫描阶段传入可省一次全文件读取（扫描时已算过）。
    """

    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        text = _read_text(path)
        if text is not None:
            content = normalized_content_sha256(text)
            token = OBJ_TOKEN.search(text[:4000])
            if token:
                stamp = EXPORTED_AT.search(text[:4000])
                return Fingerprint(
                    kind=KIND_FEISHU,
                    value=token.group(1),
                    exported_at=stamp.group(1) if stamp else "",
                    content_sha256=content,
                )
            return Fingerprint(kind=KIND_CONTENT, value=content, content_sha256=content)
    sha = fallback_sha256 or _sha256_file(path)
    return Fingerprint(kind=KIND_BINARY, value=sha, content_sha256=sha)


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _path_rank(path: str) -> tuple[int, int, str]:
    """选主副本的次序：路径层级少者优先，其次路径短者，最后字典序。"""

    normalized = path.replace("\\", "/")
    return (normalized.count("/"), len(normalized), normalized.lower())


def _union_groups(pairs: list[tuple[str, str]]) -> list[set[str]]:
    """把「同 obj_token」与「同内容」两类关系合并成连通分量。"""

    parent: dict[str, str] = {}

    def find(node: str) -> str:
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for a, b in pairs:
        union(a, b)

    buckets: dict[str, set[str]] = {}
    for node in list(parent):
        buckets.setdefault(find(node), set()).add(node)
    return [group for group in buckets.values() if len(group) > 1]


def find_duplicate_groups(
    rows: list[dict],
    ingested: set[str] | None = None,
) -> list[DuplicateGroup]:
    """从指纹行里算重复组。

    ``rows`` 每项需含 ``relative_path`` / ``kind`` / ``value`` /
    ``exported_at`` / ``content_sha256``。``ingested`` 是已成功入库的路径集合，
    主副本优先从中挑选，避免把已经转换好的那份废掉。
    """

    ingested = ingested or set()
    by_key: dict[tuple[str, str], list[str]] = {}
    meta: dict[str, dict] = {}
    for row in rows:
        path = row["relative_path"]
        meta[path] = row
        kind = row.get("kind") or ""
        value = row.get("value") or ""
        content = row.get("content_sha256") or ""
        if kind and value:
            by_key.setdefault((kind, value), []).append(path)
        # 内容键只在有内容哈希时参与，二进制不参与跨类型比对
        if content and kind != KIND_BINARY:
            by_key.setdefault((KIND_CONTENT, content), []).append(path)

    pairs: list[tuple[str, str]] = []
    for (_kind, _value), paths in by_key.items():
        unique = sorted(set(paths))
        for other in unique[1:]:
            pairs.append((unique[0], other))

    groups: list[DuplicateGroup] = []
    for members in _union_groups(pairs):
        ordered = sorted(members)
        canonical = min(
            ordered,
            key=lambda p: (0 if p in ingested else 1, *_path_rank(p)),
        )
        kind = "mixed"
        for path in ordered:
            candidate = meta[path].get("kind") or ""
            if candidate:
                kind = candidate if kind in ("mixed", candidate) else "mixed"
        canonical_stamp = meta[canonical].get("exported_at") or ""
        newer = tuple(
            path
            for path in ordered
            if path != canonical
            and (meta[path].get("exported_at") or "") > canonical_stamp
        )
        groups.append(
            DuplicateGroup(
                key=meta[canonical].get("value") or "",
                kind=kind,
                canonical=canonical,
                members=tuple(ordered),
                newer_export=newer,
            )
        )
    groups.sort(key=lambda group: group.canonical.lower())
    return groups


def refresh_index(state, sources) -> int:
    """增量刷新指纹表：只重算大小或 mtime 变过的文件，并清掉已消失的路径。"""

    updated = 0
    for source in sources:
        row = state.fingerprint_row(source.relative_path)
        if row is not None and row["size"] == source.size and row["mtime_ns"] == source.mtime_ns:
            continue
        fp = fingerprint_file(source.absolute_path, fallback_sha256=source.sha256)
        state.upsert_fingerprint(
            source.relative_path,
            fp.kind,
            fp.value,
            fp.exported_at,
            fp.content_sha256,
            source.size,
            source.mtime_ns,
        )
        updated += 1
    state.prune_fingerprints({source.relative_path for source in sources})
    return updated


def duplicate_map(groups: list[DuplicateGroup]) -> dict[str, str]:
    """把重复组摊平成「重复路径 → 主副本路径」。"""

    mapping: dict[str, str] = {}
    for group in groups:
        for member in group.members:
            if member != group.canonical:
                mapping[member] = group.canonical
    return mapping
