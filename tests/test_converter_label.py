from pathlib import Path

from ts_knowledge_agent.services.converter import (
    CONVERTER_EXCEL,
    CONVERTER_INJECTED,
    CONVERTER_MARKDOWN_COPY,
    CONVERTER_TEXT_DECODE,
    convert_file,
)


class FakeConverter:
    def convert(self, source: Path) -> str:
        return "# 注入转换器产物\n\n正文内容足够长，用于验证标注。" * 4


def test_direct_copy_records_markdown_copy(tmp_path):
    source = tmp_path / "doc.md"
    source.write_text("# 标题\n\n正文内容\n", encoding="utf-8")
    result = convert_file(source, tmp_path / "out" / "doc.md")
    assert result.converter == CONVERTER_MARKDOWN_COPY
    assert result.from_source is True


def test_text_source_records_text_decode(tmp_path):
    source = tmp_path / "note.txt"
    source.write_text("纯文本内容，用于验证重解码标注。\n", encoding="utf-8")
    result = convert_file(source, tmp_path / "out" / "note.md")
    assert result.converter == CONVERTER_TEXT_DECODE
    assert result.from_source is True


def test_injected_converter_is_labelled_as_custom(tmp_path):
    source = tmp_path / "doc.md"
    source.write_text("# 标题\n\n正文\n", encoding="utf-8")
    result = convert_file(source, tmp_path / "out" / "doc.md", converter=FakeConverter())
    assert result.converter == CONVERTER_INJECTED
    assert result.from_source is False


def test_excel_label_is_registered():
    assert CONVERTER_EXCEL == "excel-adapter"
