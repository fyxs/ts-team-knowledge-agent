"""本机留存清理：系统产物超限删最旧；用户数据与埋点永不触碰。

规则见 `docs/logging-v1.md`「留存规则」：
- 巡检/评测报告：保留最近 keep 份，超出删最旧
- runs.jsonl：超过保留期按月份归档为 .gz（归档，不是删除）
- *.log：单文件超过上限时轮转，最多保留 keep 份历史
- 明确不触碰：data/sessions.sqlite3（用户数据）、logs/usage/（使用埋点，长期保留）、
  共享仓 governance/（其保留上限由 governance 模块自己裁剪）

默认只出计划（dry-run），必须显式 apply 才真正删除。
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

KEEP_INSPECTION_REPORTS = 30
KEEP_EVALUATION_REPORTS = 30
RUNS_RETENTION_DAYS = 365
LOG_MAX_BYTES = 10 * 1024 * 1024
LOG_KEEP = 2

LOG_FILES = (
    "api.log",
    "scheduled-run.log",
    "inspection-run.log",
    "evaluation-run.log",
    "serve.log",
    "web-service.log",
    "webui-dev.log",
    "runner-errors.log",
)

# 护栏：这些名字与目录永远不参与清理
PROTECTED_FILES = ("sessions.sqlite3",)
PROTECTED_DIRECTORIES = ("data", "usage")


def is_protected(path: Path, working_directory: Path) -> bool:
    """判断路径是否属于受保护的用户数据。"""

    if path.name in PROTECTED_FILES:
        return True
    try:
        parts = {part.lower() for part in path.relative_to(working_directory).parts[:-1]}
    except ValueError:
        return True
    return bool(parts & {item.lower() for item in PROTECTED_DIRECTORIES})


@dataclass
class PrunePlan:
    """清理计划：apply 之前的一切都是只读推断。"""

    delete: list[Path] = field(default_factory=list)
    rotate: list[Path] = field(default_factory=list)
    archive_months: list[str] = field(default_factory=list)
    kept: dict[str, int] = field(default_factory=dict)
    freed_bytes: int = 0
    cutoff: str = ""

    @property
    def empty(self) -> bool:
        return not self.delete and not self.rotate and not self.archive_months

    def to_dict(self) -> dict[str, object]:
        return {
            "delete": [str(path) for path in self.delete],
            "rotate": [str(path) for path in self.rotate],
            "archive_months": list(self.archive_months),
            "kept": dict(self.kept),
            "freed_bytes": self.freed_bytes,
            "cutoff": self.cutoff,
        }


def _report_files(directory: Path, prefix: str) -> list[Path]:
    return sorted(path for path in directory.glob(f"{prefix}-*.json") if "latest" not in path.name)


def _runs_split(path: Path, cutoff: datetime) -> tuple[list[str], list[str]]:
    """按保留期把 runs.jsonl 分成「保留」与「归档」两组。"""

    if not path.exists():
        return [], []
    keep: list[str] = []
    archive: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            moment = datetime.fromisoformat(str(json.loads(stripped).get("started_at", "")))
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
        except (ValueError, json.JSONDecodeError):
            keep.append(stripped)
            continue
        (keep if moment >= cutoff else archive).append(stripped)
    return keep, archive


def build_prune_plan(
    working_directory: Path,
    *,
    keep_inspection: int = KEEP_INSPECTION_REPORTS,
    keep_evaluation: int = KEEP_EVALUATION_REPORTS,
    runs_days: int = RUNS_RETENTION_DAYS,
    log_max_bytes: int = LOG_MAX_BYTES,
    log_keep: int = LOG_KEEP,
    now: datetime | None = None,
) -> PrunePlan:
    """生成清理计划（只读，不删除任何东西）。"""

    logs = working_directory / "logs"
    plan = PrunePlan()
    moment = now or datetime.now(timezone.utc)
    plan.cutoff = (moment - timedelta(days=runs_days)).isoformat()

    for prefix, keep in (("inspection", keep_inspection), ("evaluation", keep_evaluation)):
        reports = _report_files(logs, prefix)
        surplus = reports[: max(0, len(reports) - keep)]
        plan.kept[prefix] = min(len(reports), keep)
        for path in surplus:
            if is_protected(path, working_directory):
                continue
            plan.delete.append(path)
            plan.freed_bytes += path.stat().st_size

    keep_lines, archive_lines = _runs_split(logs / "runs.jsonl", moment - timedelta(days=runs_days))
    plan.kept["runs_lines"] = len(keep_lines)
    if archive_lines:
        months = sorted({line_ for line_ in (json.loads(item).get("started_at", "")[:7] for item in archive_lines)})
        plan.archive_months = [month for month in months if month]
        plan.freed_bytes += sum(len(item) for item in archive_lines)

    for name in LOG_FILES:
        path = logs / name
        if path.exists() and path.stat().st_size > log_max_bytes and not is_protected(path, working_directory):
            plan.rotate.append(path)
            plan.freed_bytes += path.stat().st_size

    return plan


def apply_prune(working_directory: Path, plan: PrunePlan, *, log_keep: int = LOG_KEEP) -> dict[str, object]:
    """执行清理计划，并写一条可审计记录到 logs/prune-runs.jsonl。"""

    logs = working_directory / "logs"
    deleted: list[str] = []
    frozen: list[str] = []

    for path in plan.delete:
        if is_protected(path, working_directory):
            frozen.append(str(path))
            continue
        path.unlink()
        deleted.append(path.name)

    archived_bytes = 0
    if plan.archive_months:
        runs = logs / "runs.jsonl"
        keep_lines, archive_lines = _runs_split(runs, datetime.fromisoformat(plan.cutoff))
        if archive_lines:
            archive_dir = logs / "archive"
            archive_dir.mkdir(parents=True, exist_ok=True)
            for month in plan.archive_months:
                bucket = [item for item in archive_lines if json.loads(item).get("started_at", "").startswith(month)]
                if not bucket:
                    continue
                target = archive_dir / f"runs-{month.replace('-', '')}.jsonl.gz"
                existing: list[str] = []
                if target.exists():
                    with gzip.open(target, "rt", encoding="utf-8") as handle:
                        existing = [line for line in handle.read().splitlines() if line.strip()]
                merged = existing + bucket
                with gzip.open(target, "wt", encoding="utf-8") as handle:
                    handle.write("\n".join(merged) + "\n")
                archived_bytes += sum(len(item) for item in bucket)
            runs.write_text("".join(f"{line}\n" for line in keep_lines), encoding="utf-8")

    rotated: list[str] = []
    for path in plan.rotate:
        for index in range(log_keep - 1, 0, -1):
            older = path.with_name(f"{path.name}.{index}")
            if older.exists():
                older.replace(path.with_name(f"{path.name}.{index + 1}"))
        path.replace(path.with_name(f"{path.name}.1"))
        rotated.append(path.name)

    record = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "deleted": deleted,
        "frozen_protected": frozen,
        "rotated": rotated,
        "archived_months": plan.archive_months,
        "archived_bytes": archived_bytes,
        "deleted_bytes": plan.freed_bytes,
        "kept": plan.kept,
        "cutoff": plan.cutoff,
    }
    logs.mkdir(parents=True, exist_ok=True)
    audit = logs / "prune-runs.jsonl"
    with audit.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def append_prune_run(working_directory: Path, record: dict[str, object]) -> Path:
    """独立写入一条清理记录（供外部调用）。"""

    audit = working_directory / "logs" / "prune-runs.jsonl"
    audit.parent.mkdir(parents=True, exist_ok=True)
    with audit.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return audit
