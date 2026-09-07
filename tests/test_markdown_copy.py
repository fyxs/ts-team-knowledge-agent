from pathlib import Path

def test_markdown_is_copied_byte_for_byte(tmp_path: Path):
    from ts_knowledge_agent.services.converter import convert_file
    source = tmp_path / "source.md"
    original = b"# title\r\n\xef\xbb\xbfraw bytes\r\n"
    source.write_bytes(original)
    output = tmp_path / "out.md"
    convert_file(source, output)
    assert output.read_bytes() == original