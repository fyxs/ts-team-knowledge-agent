from pathlib import Path

from ts_knowledge_agent.services.postprocess import ensure_markdown_title, has_markdown_title


def test_missing_title_is_added_from_source_name(tmp_path):
    path = tmp_path / "paper.md"
    path.write_text("正文开头，产物没有一级标题。\n", encoding="utf-8")
    assert ensure_markdown_title(path, "某份报告") is True
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# 某份报告\n\n")
    assert "正文开头" in text
    assert has_markdown_title(path) is True


def test_existing_title_is_left_untouched(tmp_path):
    path = tmp_path / "paper.md"
    original = "# 已有标题\n\n正文\n"
    path.write_text(original, encoding="utf-8")
    assert ensure_markdown_title(path, "不该覆盖") is False
    assert path.read_text(encoding="utf-8") == original


def test_idempotent_on_second_call(tmp_path):
    path = tmp_path / "paper.md"
    path.write_text("无标题正文。\n", encoding="utf-8")
    ensure_markdown_title(path, "标题")
    first = path.read_text(encoding="utf-8")
    assert ensure_markdown_title(path, "标题") is False
    assert path.read_text(encoding="utf-8") == first
