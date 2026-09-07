from pathlib import Path
from ts_knowledge_agent.adapters.mineru_adapter import MinerUConverter, find_markdown

def test_find_markdown_returns_only_markdown(tmp_path: Path):
    (tmp_path / "doc.md").write_text("# ok", encoding="utf-8")
    (tmp_path / "doc_model.json").write_text("{}", encoding="utf-8")
    assert find_markdown(tmp_path) == tmp_path / "doc.md"

def test_mineru_converter_requires_explicit_python(tmp_path: Path):
    try:
        MinerUConverter(None)
    except ValueError as exc:
        assert "python" in str(exc).lower()
    else:
        raise AssertionError("missing MinerU interpreter must fail clearly")