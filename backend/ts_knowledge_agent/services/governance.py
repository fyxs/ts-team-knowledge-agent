"""成员治理记录：巡检报告等治理留痕的发布与保留策略。

目录定位与初始化见 `member_space`；本模块只负责把报告写进治理目录。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ts_knowledge_agent.services.member_space import (
    INSPECTION_SUBDIRECTORY,
    KEEP_INSPECTION_REPORTS,
    ensure_member_space,
    member_governance_directory,
)

__all__ = [
    "INSPECTION_SUBDIRECTORY",
    "KEEP_INSPECTION_REPORTS",
    "member_governance_directory",
    "prune_inspection_reports",
    "publish_inspection_report",
]


def prune_inspection_reports(directory: Path, keep: int = KEEP_INSPECTION_REPORTS) -> int:
    """只保留最近 keep 份巡检报告，返回删除数量。"""

    reports = sorted(directory.glob("*.json"))
    if len(reports) <= keep:
        return 0
    removed = 0
    for path in reports[: len(reports) - keep]:
        path.unlink()
        removed += 1
    return removed


def publish_inspection_report(
    repository_root: Path,
    member: str,
    report: dict,
    *,
    published_at: datetime | None = None,
    keep: int = KEEP_INSPECTION_REPORTS,
) -> Path:
    """把巡检报告写入共享仓治理目录：历史一份 + latest 一份。"""

    directory = member_governance_directory(repository_root, member)
    ensure_member_space(repository_root, member)
    history = directory / INSPECTION_SUBDIRECTORY
    history.mkdir(parents=True, exist_ok=True)

    moment = published_at or datetime.now(timezone.utc)
    payload = {"member": member, "published_at": moment.isoformat(), "report": report}
    text = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"

    stamp = moment.strftime("%Y%m%dT%H%M%SZ")
    report_path = history / f"{stamp}.json"
    report_path.write_text(text, encoding="utf-8", newline="\n")
    (directory / "inspection-latest.json").write_text(text, encoding="utf-8", newline="\n")
    prune_inspection_reports(history, keep)
    return report_path

def publish_evaluation_report(repository_root: Path, member: str, payload: dict, *, keep: int = 30) -> Path:
    """发布评测报告到 governance/<成员>/evaluation/ 并保留最近 keep 份。"""

    directory = member_governance_directory(repository_root, member) / "evaluation"
    directory.mkdir(parents=True, exist_ok=True)
    document = dict(payload)
    document["member"] = member
    document["kind"] = "evaluation"
    document["published_at"] = datetime.now(timezone.utc).isoformat()
    text = json.dumps(document, ensure_ascii=False, indent=2)
    stamped = directory / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    stamped.write_text(text, encoding="utf-8")
    (directory / "evaluation-latest.json").write_text(text, encoding="utf-8")
    reports = sorted(path for path in directory.glob("*.json") if path.name != "evaluation-latest.json")
    for stale in reports[:-keep] if keep > 0 else []:
        stale.unlink(missing_ok=True)
    return stamped

