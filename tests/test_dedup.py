from pathlib import Path


FEISHU = """<!-- 来源：飞书 wiki｜智能纪要:某会议｜node_token=Na1｜obj_token={token}｜导出时间={stamp} -->

# 某会议

正文内容：这是一份会议纪要。
"""


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_exported_md_without_token_uses_normalized_content(tmp_path):
    from ts_knowledge_agent.services.dedup import fingerprint_file

    a = _write(tmp_path / "a.md", "---\ntype: 文档\n---\n\n# 标题\n\n正文\n")
    b = _write(tmp_path / "b.md", "# 标题\n\n正文\n")
    fa, fb = fingerprint_file(a), fingerprint_file(b)
    assert fa.kind == "content"
    # frontmatter 不同但正文相同 → 同一指纹
    assert fa.value == fb.value


def test_feishu_export_uses_obj_token_as_key(tmp_path):
    from ts_knowledge_agent.services.dedup import fingerprint_file

    a = _write(tmp_path / "a.md", FEISHU.format(token="TOKEN123456", stamp="2026-10-20T07:31:22"))
    b = _write(tmp_path / "b.md", FEISHU.format(token="TOKEN123456", stamp="2026-11-05T07:31:29"))
    fa, fb = fingerprint_file(a), fingerprint_file(b)
    assert fa.kind == "feishu"
    assert fa.value == fb.value == "TOKEN123456"
    assert fa.exported_at == "2026-10-20T07:31:22"
    assert fb.exported_at == "2026-11-05T07:31:29"


def test_duplicate_groups_merge_token_and_content(tmp_path):
    from ts_knowledge_agent.services.dedup import fingerprint_file, find_duplicate_groups

    rows = []
    for name, token, stamp in [
        ("export/old.md", "SAME0001", "2026-10-20T07:31:22"),
        ("export/new.md", "SAME0001", "2026-11-05T07:31:29"),
    ]:
        p = _write(tmp_path / name, FEISHU.format(token=token, stamp=stamp))
        fp = fingerprint_file(p)
        rows.append({"relative_path": name, "kind": fp.kind, "value": fp.value,
                     "exported_at": fp.exported_at, "content_sha256": fp.content_sha256})

    groups = find_duplicate_groups(rows)
    assert len(groups) == 1
    assert set(groups[0].members) == {"export/old.md", "export/new.md"}


def test_different_content_not_grouped(tmp_path):
    from ts_knowledge_agent.services.dedup import fingerprint_file, find_duplicate_groups

    rows = []
    for i, text in enumerate(["甲", "乙"]):
        name = f"f{i}.md"
        p = _write(tmp_path / name, text)
        fp = fingerprint_file(p)
        rows.append({"relative_path": name, "kind": fp.kind, "value": fp.value,
                     "exported_at": fp.exported_at, "content_sha256": fp.content_sha256})

    assert find_duplicate_groups(rows) == []


def test_canonical_prefers_ingested_path(tmp_path):
    from ts_knowledge_agent.services.dedup import fingerprint_file, find_duplicate_groups

    rows = []
    # b.md 层级更深，但它已入库，不能把已转换的那份废掉
    for name, text in [("a.md", "同内容"), ("deep/b.md", "同内容")]:
        p = _write(tmp_path / name, text)
        fp = fingerprint_file(p)
        rows.append({"relative_path": name, "kind": fp.kind, "value": fp.value,
                     "exported_at": fp.exported_at, "content_sha256": fp.content_sha256})

    groups = find_duplicate_groups(rows, ingested={"deep/b.md"})
    assert groups[0].canonical == "deep/b.md"
    assert groups[0].duplicates == ("a.md",)


def test_refresh_index_is_incremental(tmp_path):
    from ts_knowledge_agent.repositories.state_store import StateStore
    from ts_knowledge_agent.services.dedup import refresh_index
    from ts_knowledge_agent.services.scanner import scan_directory

    root = tmp_path / "src"
    _write(root / "a.md", "内容甲")
    _write(root / "b.md", "内容乙")
    state = StateStore(tmp_path / "state.sqlite3")
    try:
        first = refresh_index(state, scan_directory(root))
        second = refresh_index(state, scan_directory(root))
        assert first == 2
        assert second == 0  # 大小与 mtime 未变，不重算

        (root / "b.md").write_text("内容乙改", encoding="utf-8")
        third = refresh_index(state, scan_directory(root))
        assert third == 1

        (root / "a.md").unlink()
        refresh_index(state, scan_directory(root))
        assert [row["relative_path"] for row in state.list_fingerprints()] == ["b.md"]
    finally:
        state.close()


def test_pipeline_skips_duplicate_and_reports_count(tmp_path):
    from ts_knowledge_agent.config import Settings
    from ts_knowledge_agent.services.pipeline import run_once

    source_root = tmp_path / "source"
    repo = tmp_path / "repo"
    _write(source_root / "a.md", "# 同一篇\n\n正文\n")
    _write(source_root / "deep" / "b.md", "# 同一篇\n\n正文\n")

    settings = Settings("whm", source_root, tmp_path, repo, 60, "unused")

    class Fake:
        def convert(self, source):
            return source.read_text(encoding="utf-8")

    summary = run_once(settings, batch_size=10, converter=Fake())
    assert summary.duplicates == 1
    assert summary.converted == 1

    # 第二次运行仍然稳定跳过，不会反复重转
    again = run_once(settings, batch_size=10, converter=Fake())
    assert again.duplicates == 1
    assert again.converted == 0
