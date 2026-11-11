"""回归：.xls（Excel 97-2003，OLE 二进制）不能交给 MinerU，要走 xlrd 直读。

生产事故背景（2026-11-10）：一天内 286 次 .xls 转换全部 RuntimeError，
每个白烧 143~435 秒（MinerU 用 pdfium 读 OLE 复合文档）。
"""

from pathlib import Path

import pytest

from ts_knowledge_agent.adapters.excel_adapter import convert_legacy_excel


def _xls_stub(path: Path) -> None:
    """最小的 BIFF8 文件由 xlrd 依赖的库生成不便，这里直接跳过真实写盘。"""


@pytest.fixture()
def real_xls() -> Path:
    candidate = Path(r"D:\2Work\Knowledge\TS-Share\业务线\能源\方案\原始资料\材料\医院系统导出材料\广德路制冷机房\23供暖水泵外科.xls")
    if not candidate.is_file():
        pytest.skip("样例 .xls 不存在（换机器跑测试时正常）")
    return candidate


def test_legacy_xls_is_converted_with_xlrd(real_xls: Path, tmp_path: Path) -> None:
    output = tmp_path / "out" / "legacy.md"
    convert_legacy_excel(real_xls, output, max_rows=200)

    assert output.is_file()
    body = output.read_text(encoding="utf-8")
    assert "## Sheets" in body, "索引页要有 sheets 清单"
    parts = sorted((output.parent / "sheets").glob("*.md"))
    assert parts, "至少产出一个分表"
    # 分表按 max_rows 切块，文件名形如「采暖分项能耗.md」与「采暖分项能耗-002.md」；
    # 英文排序会把 -002 排在 .md 之前，所以必须合并全部块再断言，否则只看到后半段。
    table = "".join(part.read_text(encoding="utf-8") for part in parts)
    assert table.startswith("# "), "分表要有标题"
    assert "|" in table, "必须是 markdown 表格"
    # 日期列可能是 xlrd 的日期单元格（转成 2023-11-01 00:00）或纯文本（2023/11/01 00:00:00），
    # 两种都必须保持可读，不能退化成 45231.0 这样的序列号
    assert "2023" in table and "2024" in table, "日期要可读，不能是 Excel 序列号"
    assert "| 日期 |" in table, "表头要保留"


def test_legacy_xls_conversion_is_fast(real_xls: Path, tmp_path: Path) -> None:
    import time

    output = tmp_path / "out" / "legacy.md"
    started = time.monotonic()
    convert_legacy_excel(real_xls, output, max_rows=200)
    elapsed = time.monotonic() - started
    assert elapsed < 10, f"xlrd 直读应在秒级完成，实测 {elapsed:.1f}s"


def test_corrupt_xls_reports_clear_error(tmp_path: Path) -> None:
    broken = tmp_path / "broken.xls"
    broken.write_bytes(b"not-an-ole-file")
    with pytest.raises(RuntimeError) as excinfo:
        convert_legacy_excel(broken, tmp_path / "out" / "broken.md")
    assert "旧版 Excel 读取失败" in str(excinfo.value)
