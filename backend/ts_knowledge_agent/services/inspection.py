"""知识库质量巡检：对已转换文档做分层抽样与结构校验。"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.repositories.state_store import StateStore

IMAGE_REFERENCE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
HEADING = re.compile(r"^#\s+\S+", re.MULTILINE)
SOURCE_DERIVED_EXTENSIONS = frozenset({".md", ".txt"})
TOOL_OUTPUT_EXTENSIONS = frozenset({".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls"})
# 截断启发式只适用于正文型产物：幻灯片文本天然是片段，不以标点收尾属正常
TRUNCATION_CHECK_EXTENSIONS = frozenset({".pdf", ".docx", ".doc"})
NEAR_EMPTY_CHARS = 200


@dataclass(frozen=True)
class DocumentCheck:
    relative_path: str
    file_type: str
    status: str
    output_path: str
    total_files: int
    total_chars: int
    issues: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class InspectionReport:
    sampled: int
    clean: int
    issue_counts: dict[str, int]
    by_file_type: dict[str, int]
    checks: tuple[DocumentCheck, ...]
    generated_at: str = ""

    @property
    def blocking(self) -> int:
        """会直接损害检索或阅读的缺陷数量。"""
        blocking_kinds = ("output_missing", "empty_output", "invalid_utf8", "replacement_chars", "nul_bytes", "broken_images")
        return sum(count for kind, count in self.issue_counts.items() if kind in blocking_kinds)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["blocking"] = self.blocking
        return payload


def is_source_derived(file_type: str) -> bool:
    """判断产物是否直接来自源文件（Markdown 直复制、文本重解码），这类产物不应套用转换质量启发式。"""
    return file_type.lower() in SOURCE_DERIVED_EXTENSIONS


def document_files(output_path: Path) -> list[Path]:
    """主 Markdown 与分片（Excel 的 sheets/*.md）共同构成文档内容。"""
    main = Path(output_path)
    files = [main] if main.is_file() else []
    sheets = main.parent / "sheets"
    if sheets.is_dir():
        files.extend(sorted(path for path in sheets.glob("*.md") if path.is_file()))
    return files


def check_document(relative_path: str, file_type: str, status: str, output_path: str) -> DocumentCheck:
    main = Path(output_path)
    issues: list[str] = []

    if not main.is_file():
        return DocumentCheck(relative_path, file_type, status, output_path, 0, 0, ("output_missing",))

    files = document_files(main)
    texts: list[str] = []
    invalid = False
    for path in files:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            issues.append(f"unreadable: {path.name}")
            invalid = True
            continue
        if not raw:
            issues.append(f"empty_file: {path.name}")
            invalid = True
            continue
        try:
            texts.append(raw.decode("utf-8"))
        except UnicodeDecodeError:
            issues.append(f"invalid_utf8: {path.name}")
            invalid = True

    if invalid or not texts:
        return DocumentCheck(relative_path, file_type, status, output_path, len(files), 0, tuple(issues))

    combined = "\n".join(texts)
    total_chars = len(combined)

    replacement = combined.count("\ufffd")
    if replacement:
        issues.append(f"replacement_chars: {replacement}")

    nul = combined.count("\x00")
    if nul:
        issues.append(f"nul_bytes: {nul}")

    broken = []
    for reference in IMAGE_REFERENCE.findall(combined):
        if reference.startswith(("http://", "https://", "data:")):
            continue
        if not (main.parent / reference).resolve().is_file():
            broken.append(reference)
    if broken:
        issues.append(f"broken_images: {len(broken)}")

    if total_chars < NEAR_EMPTY_CHARS:
        issues.append(f"near_empty: {total_chars} chars")

    # 工具产物的结构启发式：直复制产物与源文件一致，不适用
    if not is_source_derived(file_type):
        if not HEADING.search(combined):
            issues.append("no_h1_title")
        stripped = combined.rstrip()
        if file_type.lower() in TRUNCATION_CHECK_EXTENSIONS and stripped and not re.search(
            r"[。！？.!?）」』】`\)\|\-\*0-9A-Za-z]$", stripped[-1]
        ):
            issues.append(f"suspect_truncation: last={stripped[-1]!r}")

    return DocumentCheck(relative_path, file_type, status, output_path, len(files), total_chars, tuple(issues))


def sample_conversions(store: StateStore, per_type: int = 6) -> list[tuple[str, str, str, str]]:
    """按文件类型分层、在各自范围内均匀抽样，避免同目录聚簇。"""
    buckets: dict[str, list[tuple[str, str, str, str]]] = {}
    for row in store.list_conversions():
        if row["status"] not in ("converted", "quality_warned"):
            continue
        file_type = Path(row["relative_path"]).suffix.lower()
        buckets.setdefault(file_type, []).append(
            (row["relative_path"], file_type, row["status"], row["output_path"])
        )

    sample: list[tuple[str, str, str, str]] = []
    for file_type in sorted(buckets):
        items = sorted(buckets[file_type])
        step = max(1, len(items) // per_type)
        sample.extend(items[::step][:per_type])
    return sample


def inspect_knowledge_base(settings: Settings, per_type: int = 6) -> InspectionReport:
    repository = settings.shared_knowledge_repository_directory
    store = StateStore(repository / "data" / "state.sqlite3")
    try:
        sample = sample_conversions(store, per_type=per_type)
    finally:
        store.close()

    checks = tuple(check_document(*item) for item in sample)
    counts: Counter[str] = Counter()
    by_type: Counter[str] = Counter()
    for check in checks:
        by_type[check.file_type] += 1
        for issue in check.issues:
            counts[issue.split(":")[0]] += 1

    return InspectionReport(
        sampled=len(checks),
        clean=sum(1 for check in checks if check.ok),
        issue_counts=dict(sorted(counts.items())),
        by_file_type=dict(sorted(by_type.items())),
        checks=checks,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def write_inspection_report(working_directory: Path, report: InspectionReport) -> Path:
    directory = Path(working_directory) / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report.to_dict(), ensure_ascii=False, indent=1)
    latest = directory / "inspection-latest.json"
    latest.write_text(payload, encoding="utf-8")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stamped = directory / f"inspection-{stamp}.json"
    stamped.write_text(payload, encoding="utf-8")
    return stamped
