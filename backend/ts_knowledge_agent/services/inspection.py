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
INSPECTION_RUNS_FILE = "inspection-runs.jsonl"
DEFAULT_INSPECTION_INTERVAL_MINUTES = 1440


RUNS_FILE = "runs.jsonl"
LOCK_RECOVERIES_FILE = "lock-recoveries.jsonl"
RUN_HEALTH_WINDOW = 20
CONSECUTIVE_FAILURE_BLOCKING = 3


@dataclass(frozen=True)
class RunHealth:
    """运行健康：把"失败有记录但没有对外信号"变成可看见的检查项。"""

    window: int = 0
    ok: int = 0
    failed: int = 0
    locked: int = 0
    consecutive_failures: int = 0
    last_result: str = ""
    last_error: str = ""
    lock_recoveries: int = 0

    @property
    def blocking(self) -> int:
        return 1 if self.consecutive_failures >= CONSECUTIVE_FAILURE_BLOCKING else 0

    @property
    def summary(self) -> str:
        return (
            f"最近 {self.window} 轮：ok={self.ok} locked={self.locked} failed={self.failed}；"
            f"连续失败={self.consecutive_failures}；最近结果={self.last_result or 'unknown'}；"
            f"锁接管={self.lock_recoveries}"
        )


def _tail_jsonl(path: Path, window: int) -> list[dict]:
    if not path.is_file():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    records: list[dict] = []
    for line in lines[-window:]:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _record_result(record: dict) -> str:
    result = str(record.get("result") or "").strip()
    if result:
        return result
    return "failed" if record.get("error") else "ok"


def collect_run_health(working_directory: Path, window: int = RUN_HEALTH_WINDOW) -> RunHealth:
    """读取运行记录与锁接管记录，汇总为巡检可见的运行健康。"""

    logs = Path(working_directory) / "logs"
    records = _tail_jsonl(logs / RUNS_FILE, window)
    ok = failed = locked = 0
    for record in records:
        result = _record_result(record)
        if result == "ok":
            ok += 1
        elif result == "locked":
            locked += 1
        else:
            failed += 1
    consecutive = 0
    for record in reversed(records):
        if _record_result(record) == "ok":
            break
        consecutive += 1
    last = records[-1] if records else {}
    recoveries = _tail_jsonl(logs / LOCK_RECOVERIES_FILE, window)
    return RunHealth(
        window=len(records),
        ok=ok,
        failed=failed,
        locked=locked,
        consecutive_failures=consecutive,
        last_result=_record_result(last) if last else "",
        last_error=str(last.get("error") or "")[:200],
        lock_recoveries=len(recoveries),
    )


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
    run_health: RunHealth = RunHealth()

    @property
    def blocking(self) -> int:
        """会直接损害检索或阅读的缺陷数量。"""
        blocking_kinds = ("output_missing", "empty_output", "invalid_utf8", "replacement_chars", "nul_bytes", "broken_images")
        return sum(count for kind, count in self.issue_counts.items() if kind in blocking_kinds) + self.run_health.blocking

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
        run_health=collect_run_health(settings.working_directory),
    )


def append_inspection_run(working_directory: Path, report: "InspectionReport", started_at: str) -> Path:
    """追加一条巡检运行记录，供到期判定与趋势统计使用。"""

    path = Path(working_directory) / "logs" / INSPECTION_RUNS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "started_at": started_at,
        "sampled": report.sampled,
        "clean": report.clean,
        "blocking": report.blocking,
        "issue_counts": dict(report.issue_counts),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def last_inspection_started_at(working_directory: Path) -> datetime | None:
    """读取最近一次巡检的开始时间；没有记录时返回 None。"""

    path = Path(working_directory) / "logs" / INSPECTION_RUNS_FILE
    if not path.is_file():
        return None
    for line in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line).get("started_at")
            if not raw:
                continue
            return datetime.fromisoformat(raw)
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def is_inspection_due(
    working_directory: Path,
    interval_minutes: int = DEFAULT_INSPECTION_INTERVAL_MINUTES,
    now: datetime | None = None,
) -> bool:
    """判断距上次巡检是否已达到间隔；没有历史记录时视为到期。"""

    last = last_inspection_started_at(working_directory)
    if last is None:
        return True
    current = now or datetime.now(timezone.utc)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (current - last).total_seconds() / 60.0 >= float(interval_minutes)


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
