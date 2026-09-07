from pathlib import Path
import pytest
from ts_knowledge_agent.services.converter import convert_file

def test_txt_utf8_is_written_as_utf8_markdown(tmp_path: Path):
    source=tmp_path/"source.txt"; source.write_bytes("标题\n正文".encode("utf-8")); out=tmp_path/"out.md"
    convert_file(source,out); assert out.read_text(encoding="utf-8")=="标题\n正文"

def test_txt_gb18030_is_transcoded(tmp_path: Path):
    source=tmp_path/"source.txt"; source.write_bytes("标题\n正文".encode("gb18030")); out=tmp_path/"out.md"
    convert_file(source,out); assert out.read_text(encoding="utf-8")=="标题\n正文"

def test_txt_binary_is_rejected(tmp_path: Path):
    source=tmp_path/"source.txt"; source.write_bytes(b"abc\x00def"); out=tmp_path/"out.md"
    with pytest.raises(ValueError, match="binary"): convert_file(source,out)
