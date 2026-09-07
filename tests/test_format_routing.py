from pathlib import Path

from ts_knowledge_agent.services.converter import (
    SUPPORTED_EXTENSIONS,
    is_direct_copy,
    is_supported,
)
from ts_knowledge_agent.services.scanner import scan_directory


def test_default_supported_formats():
    for suffix in (".ppt", ".pptx", ".doc", ".docx", ".xls", ".xlsx", ".pdf", ".txt", ".md"):
        assert is_supported(Path("sample" + suffix))
    assert is_direct_copy(Path("sample.md"))
    assert is_direct_copy(Path("sample.txt"))
    assert not is_direct_copy(Path("sample.pdf"))


def test_unsupported_formats_are_scanned_but_not_supported(tmp_path: Path):
    (tmp_path / "keep.pdf").write_bytes(b"pdf")
    (tmp_path / "ignore.png").write_bytes(b"png")
    files = scan_directory(tmp_path)
    assert {item.relative_path for item in files} == {"keep.pdf", "ignore.png"}
    assert {item.relative_path for item in files if item.supported} == {"keep.pdf"}