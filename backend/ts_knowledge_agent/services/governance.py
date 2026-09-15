"""成员治理记录：与个人知识空间分离的检查与治理留痕。

个人空间（members/<成员>/）只存放该成员共享的知识；巡检报告、治理结论这类
运行期记录写入 governance/<成员>/，两者不交叉。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

GOVERNANCE_DIRECTORY = "governance"
INSPECTION_SUBDIRECTORY = "inspection"
KEEP_INSPECTION_REPORTS = 30

README_TEXT = """# 治理记录（governance）

本目录存放各成员的检查与治理留痕，**不是知识内容**。

- 按成员划分：`governance/<成员>/`
- 个人知识空间 `members/<成员>/` 只存放该成员共享的知识，两者不交叉
- 内容由应用写入（`ts-team-kb inspect`），不要手工编辑
- 巡检报告保留最近 {keep} 份，超出后自动清理最早的

约定：

- 本目录不参与知识检索与登记表生成（检索只覆盖 `members/`）
- 本目录内容随知识仓同步提交，供团队成员查看运行健康度
"""


def member_governance_directory(repository_root: Path, member: str) -> Path:
    """返回某个成员在共享仓中的治理记录目录。"""

    member_name = (member or "").strip()
    if not member_name:
        raise ValueError("member must not be empty")
    return Path(repository_root) / GOVERNANCE_DIRECTORY / member_name


def _write_readme(directory: Path) -> None:
    readme = directory / "README.md"
    if not readme.is_file():
        readme.write_text(README_TEXT.format(keep=KEEP_INSPECTION_REPORTS), encoding="utf-8", newline="\n")


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
    history = directory / INSPECTION_SUBDIRECTORY
    history.mkdir(parents=True, exist_ok=True)
    _write_readme(directory)

    moment = published_at or datetime.now(timezone.utc)
    payload = {"member": member, "published_at": moment.isoformat(), "report": report}
    text = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"

    stamp = moment.strftime("%Y%m%dT%H%M%SZ")
    report_path = history / f"{stamp}.json"
    report_path.write_text(text, encoding="utf-8", newline="\n")
    (directory / "inspection-latest.json").write_text(text, encoding="utf-8", newline="\n")
    prune_inspection_reports(history, keep)
    return report_path
