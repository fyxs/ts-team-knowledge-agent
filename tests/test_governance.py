from datetime import datetime, timezone
from pathlib import Path

import pytest

from ts_knowledge_agent.services.governance import (
    KEEP_INSPECTION_REPORTS,
    member_governance_directory,
    prune_inspection_reports,
    publish_inspection_report,
)

REPORT = {"sampled": 25, "clean": 25, "blocking": 0, "issue_counts": {}, "by_type": {".md": 6}}


def test_publish_creates_member_tree_outside_knowledge_space(tmp_path):
    published = publish_inspection_report(tmp_path, "whm", REPORT)
    assert published.parent == tmp_path / "governance" / "whm" / "inspection"
    assert (tmp_path / "governance" / "whm" / "inspection-latest.json").is_file()
    assert (tmp_path / "governance" / "whm" / "README.md").is_file()
    assert not (tmp_path / "members").exists(), "治理记录不得写入个人知识空间"


def test_latest_matches_history_entry(tmp_path):
    publish_inspection_report(tmp_path, "whm", REPORT)
    latest = (tmp_path / "governance" / "whm" / "inspection-latest.json").read_text(encoding="utf-8")
    history = list((tmp_path / "governance" / "whm" / "inspection").glob("*.json"))
    assert len(history) == 1
    assert history[0].read_text(encoding="utf-8") == latest
    assert '"member": "whm"' in latest


def test_reports_are_pruned_to_retention_limit(tmp_path):
    directory = tmp_path / "inspection"
    directory.mkdir()
    for index in range(KEEP_INSPECTION_REPORTS + 5):
        (directory / f"2026010{index % 10}T0000{index:02d}Z.json").write_text("{}", encoding="utf-8")
    removed = prune_inspection_reports(directory, keep=KEEP_INSPECTION_REPORTS)
    assert removed == 5
    assert len(list(directory.glob("*.json"))) == KEEP_INSPECTION_REPORTS


def test_readme_is_written_once(tmp_path):
    publish_inspection_report(tmp_path, "whm", REPORT, published_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    readme = tmp_path / "governance" / "whm" / "README.md"
    original = readme.read_text(encoding="utf-8")
    publish_inspection_report(tmp_path, "whm", REPORT, published_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
    assert readme.read_text(encoding="utf-8") == original
    assert len(list((tmp_path / "governance" / "whm" / "inspection").glob("*.json"))) == 2


def test_empty_member_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        member_governance_directory(tmp_path, "  ")
