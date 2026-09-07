from pathlib import Path
from openpyxl import Workbook
from ts_knowledge_agent.adapters.excel_adapter import convert_excel

def test_excel_is_split_into_markdown_sheets(tmp_path: Path):
    source = tmp_path / "sample.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(["ID", "Content"])
    ws.append([1, "Alpha"])
    ws.append([2, "Beta"])
    wb.save(source)
    output = tmp_path / "sample.md"
    convert_excel(source, output, max_rows=1)
    assert output.is_file()
    parts = sorted((output.parent / "sheets").glob("*.md"))
    assert len(parts) == 2
    assert "| ID | Content |" in parts[0].read_text(encoding="utf-8")
