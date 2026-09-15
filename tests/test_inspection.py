from pathlib import Path

from ts_knowledge_agent.services.inspection import check_document, document_files, is_source_derived


def test_excel_document_counts_sheet_fragments(tmp_path):
    directory = tmp_path / "book"
    (directory / "sheets").mkdir(parents=True)
    (directory / "book.md").write_text("# book\n\n- [Sheet1](sheets/Sheet1.md)\n", encoding="utf-8")
    (directory / "sheets" / "Sheet1.md").write_text("# Sheet1\n\n" + "数据行内容\n" * 80, encoding="utf-8")

    check = check_document("book.xlsx", ".xlsx", "converted", str(directory / "book.md"))

    assert check.total_files == 2
    assert check.total_chars > 200
    assert "near_empty" not in check.issues


def test_source_derived_output_skips_conversion_heuristics(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("# 标题\n\n" + "正文内容，源文件本身如此结尾，不必套用转换启发式。" * 8, encoding="utf-8")

    check = check_document("doc.md", ".md", "converted", str(path))

    assert check.ok, check.issues
    assert is_source_derived(".md") and is_source_derived(".txt")


def test_tool_output_flags_missing_title_and_replacement_chars(tmp_path):
    path = tmp_path / "tool.md"
    path.write_text("没有标题的转换产物，包含替换字符 \ufffd，结尾不完整", encoding="utf-8")

    check = check_document("paper.pdf", ".pdf", "converted", str(path))

    assert "no_h1_title" in check.issues
    assert any(issue.startswith("replacement_chars") for issue in check.issues)


def test_missing_output_is_reported(tmp_path):
    check = check_document("gone.pdf", ".pdf", "converted", str(tmp_path / "gone" / "gone.md"))

    assert check.issues == ("output_missing",)
    assert not check.ok


def test_broken_image_reference_is_reported(tmp_path):
    directory = tmp_path / "doc"
    directory.mkdir()
    (directory / "doc.md").write_text(
        "# 标题\n\n![图](images/missing.png)\n\n" + "正文内容" * 120, encoding="utf-8"
    )

    check = check_document("doc.pdf", ".pdf", "converted", str(directory / "doc.md"))

    assert any(issue.startswith("broken_images") for issue in check.issues)
    assert len(document_files(directory / "doc.md")) == 1


def test_near_empty_document_is_reported(tmp_path):
    path = tmp_path / "tiny.md"
    path.write_text("很短", encoding="utf-8")

    check = check_document("tiny.xlsx", ".xlsx", "converted", str(path))

    assert any(issue.startswith("near_empty") for issue in check.issues)

def test_slide_output_is_not_flagged_as_truncated(tmp_path):
    path = tmp_path / "deck.md"
    path.write_text("# 标题\n\n数据治理 / 特征与标签 / 训练调度\n\n效果评估 / 模型管理 / 业务反馈", encoding="utf-8")

    check = check_document("deck.pptx", ".pptx", "converted", str(path))

    assert "no_h1_title" not in check.issues
    assert not any(issue.startswith("suspect_truncation") for issue in check.issues)
