from pathlib import Path

import pytest

from ts_knowledge_agent.services.member_space import (
    ensure_member_space,
    member_governance_directory,
    member_knowledge_directory,
)


def test_ensure_member_space_creates_both_directories(tmp_path):
    space = ensure_member_space(tmp_path, "whm")
    assert space["knowledge"] == tmp_path / "members" / "whm"
    assert space["governance"] == tmp_path / "governance" / "whm"
    assert (space["knowledge"] / "README.md").is_file()
    assert (space["governance"] / "README.md").is_file()


def test_directories_are_siblings_not_nested(tmp_path):
    ensure_member_space(tmp_path, "whm")
    assert not (tmp_path / "members" / "whm" / "governance").exists()
    assert not list((tmp_path / "members").rglob("inspection*"))
    assert not list((tmp_path / "members").rglob("*.json"))


def test_knowledge_readme_points_to_governance(tmp_path):
    ensure_member_space(tmp_path, "whm")
    text = (tmp_path / "members" / "whm" / "README.md").read_text(encoding="utf-8")
    assert "governance/whm/" in text
    assert "只存放该成员共享的知识" in text


def test_ensure_member_space_is_idempotent(tmp_path):
    ensure_member_space(tmp_path, "whm")
    readme = tmp_path / "members" / "whm" / "README.md"
    original = readme.read_text(encoding="utf-8")
    ensure_member_space(tmp_path, "whm")
    assert readme.read_text(encoding="utf-8") == original


def test_helpers_agree_with_returned_paths(tmp_path):
    space = ensure_member_space(tmp_path, "whm")
    assert member_knowledge_directory(tmp_path, "whm") == space["knowledge"]
    assert member_governance_directory(tmp_path, "whm") == space["governance"]


def test_empty_member_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        member_knowledge_directory(tmp_path, "  ")


def test_governance_readme_lives_at_directory_level_and_member_readme_is_member_scoped(tmp_path):
    """目录级说明写在 governance/README.md；成员目录下是成员级说明。

    历史版本把目录级文本写进了 governance/<成员>/README.md，
    这里同时验证按标记修正历史错位内容的行为，以及幂等性。
    """

    from ts_knowledge_agent.services.member_space import (
        GOVERNANCE_MEMBER_README_TEXT,
        ensure_member_space,
    )

    root = tmp_path / "repo"
    root.mkdir()

    legacy = root / "governance" / "whm"
    legacy.mkdir(parents=True)
    (legacy / "README.md").write_text(
        "# 治理记录（governance）\n\n- 按成员划分：`governance/<成员>/`\n", encoding="utf-8"
    )

    ensure_member_space(root, "whm")

    directory_readme = root / "governance" / "README.md"
    assert directory_readme.is_file()
    assert "按成员划分：`governance/<成员>/`" in directory_readme.read_text(encoding="utf-8")

    member_readme = legacy / "README.md"
    assert member_readme.read_text(encoding="utf-8") == GOVERNANCE_MEMBER_README_TEXT.format(member="whm")

    before = member_readme.read_text(encoding="utf-8")
    ensure_member_space(root, "whm")
    assert member_readme.read_text(encoding="utf-8") == before

