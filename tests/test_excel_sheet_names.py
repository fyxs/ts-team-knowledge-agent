"""Excel sheet 文件名：中文名不能被清空，否则多 sheet 互相覆盖。"""

from pathlib import Path


def _write(tmp_path: Path, sheets: dict[str, list[list[object]]]) -> Path:
    from ts_knowledge_agent.adapters.excel_adapter import _write_sheets

    out = tmp_path / "表" / "表.md"
    out.parent.mkdir(parents=True)
    return out


def test_chinese_sheet_names_are_distinct(tmp_path):
    from openpyxl import Workbook

    from ts_knowledge_agent.adapters.excel_adapter import _openpyxl_sheets, _write_sheets

    wb = Workbook()
    wb.remove(wb.active)
    for title, value in [("封面", "a"), ("站点总览", "b"), ("能流-电", "c"), ("能流-水", "d")]:
        ws = wb.create_sheet(title)
        ws.append(["列1", "列2"])
        ws.append([value, value.upper()])
    src = tmp_path / "附件.xlsx"
    wb.save(src)
    wb.close()

    out = tmp_path / "附件" / "附件.md"
    out.parent.mkdir(parents=True)
    (out.parent / "sheets").mkdir(parents=True, exist_ok=True)
    size = _write_sheets(_openpyxl_sheets(src), out, out.parent / "sheets", 5000)

    produced = sorted(p.name for p in (out.parent / "sheets").glob("*.md"))
    assert len(produced) == 4, produced
    assert "封面.md" in produced
    assert "站点总览.md" in produced
    assert "能流-电.md" in produced
    assert "能流-水.md" in produced
    assert size > 0


def test_illegal_characters_are_replaced_but_kept_readable(tmp_path):
    from ts_knowledge_agent.adapters.excel_adapter import _safe_sheet_name

    assert _safe_sheet_name("能流/电", 1) == "能流_电"
    assert _safe_sheet_name('a:b*c?d"e<f>g|h', 2) == "a_b_c_d_e_f_g_h"
    assert _safe_sheet_name("", 7) == "Sheet7"
    assert _safe_sheet_name("普通名字", 3) == "普通名字"


def test_duplicate_normalised_names_do_not_overwrite(tmp_path):
    from ts_knowledge_agent.adapters.excel_adapter import _write_sheets

    rows = [["列1"], ["值"]]
    sheets = [("能流/电", rows), ("能流:电", rows)]
    out = tmp_path / "x" / "x.md"
    out.parent.mkdir(parents=True)
    (out.parent / "sheets").mkdir(parents=True, exist_ok=True)
    _write_sheets(iter(sheets), out, out.parent / "sheets", 5000)

    produced = sorted(p.name for p in (out.parent / "sheets").glob("*.md"))
    assert len(produced) == 2, produced


def test_chunked_sheet_keeps_readable_prefix(tmp_path):
    from ts_knowledge_agent.adapters.excel_adapter import _write_sheets

    rows = [["列1"]] + [[f"v{i}"] for i in range(3)]
    out = tmp_path / "y" / "y.md"
    out.parent.mkdir(parents=True)
    (out.parent / "sheets").mkdir(parents=True, exist_ok=True)
    _write_sheets(iter([("制冷站", rows)]), out, out.parent / "sheets", 2)

    produced = sorted(p.name for p in (out.parent / "sheets").glob("*.md"))
    assert produced == ["制冷站-002.md", "制冷站.md"], produced
