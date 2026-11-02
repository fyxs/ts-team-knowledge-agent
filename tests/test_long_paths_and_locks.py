"""回归：长标题输出路径 / .doc 预转换 / 索引库并发写。

三个缺陷都来自生产日志（2026-11-02）：
1. 输出绝对路径 >260 → shutil.copy2 报 FileNotFoundError，文件每轮重试必失败；
2. .doc 被当 PDF 交给 MinerU → pdfium 读不了，白烧 90~100s 后 RuntimeError；
3. serve 与转换轮并发写 state.sqlite3 → database is locked，整轮在索引阶段崩溃。
"""

from pathlib import Path

import pytest

from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.repositories.search_store import BUSY_TIMEOUT_SECONDS, SearchStore
from ts_knowledge_agent.services import converter as converter_module
from ts_knowledge_agent.services import pipeline
from ts_knowledge_agent.services.converter import CONVERTER_DOC, convert_file


def make_settings(tmp_path: Path) -> Settings:
    return Settings("whm", tmp_path / "source", tmp_path / "work", tmp_path / "repo", 60)


# ---------- 1. 长路径 ----------


def test_short_relative_path_keeps_layout(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    output = pipeline.output_path_for(settings, "会议纪要/短标题/短标题.md")
    assert output == settings.shared_knowledge_repository_directory / "members" / "whm" / "会议纪要" / "短标题" / "短标题" / "短标题.md"
    assert len(str(output)) <= pipeline.OUTPUT_PATH_LIMIT


def test_long_title_is_shortened_below_windows_limit(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    title = "智能纪要_会议纪要：" + "能耗基准修正与节能量测算口径" * 4
    relative = f"飞书导出/会议纪要/{title}/{title}.md"
    output = pipeline.output_path_for(settings, relative)
    assert len(str(output)) <= pipeline.OUTPUT_PATH_LIMIT
    assert output.name.endswith(".md")
    # 目录名、子目录名、文件名三者一致（压缩后仍与标题同源）
    assert output.parent.name == output.stem
    assert output.parent.parent.name == output.stem


def test_shortening_is_stable_and_distinct(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    long_a = "智能纪要_会议纪要：" + "能耗基准修正与节能量测算口径" * 4 + "A"
    long_b = "智能纪要_会议纪要：" + "能耗基准修正与节能量测算口径" * 4 + "B"
    first = pipeline.output_path_for(settings, f"目录/{long_a}/{long_a}.md")
    again = pipeline.output_path_for(settings, f"目录/{long_a}/{long_a}.md")
    other = pipeline.output_path_for(settings, f"目录/{long_b}/{long_b}.md")
    assert first == again, "同一来源必须稳定映射到同一路径"
    assert first != other, "不同标题压缩后不能撞车"


def test_shortened_path_is_writable(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    title = "智能纪要_会议纪要：" + "能耗基准修正与节能量测算口径" * 4
    output = pipeline.output_path_for(settings, f"飞书导出/会议纪要/{title}/{title}.md")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("# 测试\n\n正文\n", encoding="utf-8")
    assert output.is_file()


# ---------- 2. .doc 预转换 ----------


def test_doc_is_converted_through_word_first(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "legacy.doc"
    source.write_bytes(b"\xd0\xcf\x11\xe0fake-ole")
    output = tmp_path / "out" / "legacy.md"

    calls: dict[str, Path] = {}

    def fake_extract(source_path: Path, python=None, timeout=None) -> str:
        calls["source"] = source_path
        return "推荐书\r姓名\r\x07部门\r\x07岗位\r\x07"

    monkeypatch.setattr(converter_module, "extract_doc_text", fake_extract)

    result = convert_file(source, output, working_directory=tmp_path / "work")

    assert calls["source"] == source
    assert result.converter == CONVERTER_DOC
    body = output.read_text(encoding="utf-8")
    assert "推荐书" in body and "姓名 | 部门 | 岗位" in body, "表格单元格要转成 markdown 分隔"
    assert result.converter == CONVERTER_DOC
    assert output.is_file()


# ---------- 3. 索引库并发 ----------


def test_search_store_waits_for_lock_and_uses_wal(tmp_path: Path) -> None:
    store = SearchStore(tmp_path / "state.sqlite3")
    try:
        assert store.connection.execute("PRAGMA busy_timeout").fetchone()[0] == BUSY_TIMEOUT_SECONDS * 1000
        assert store.connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        store.upsert("members/whm/a.md", "a", "正文", "digest")
        assert store.list_paths() == ["members/whm/a.md"]
    finally:
        store.close()
