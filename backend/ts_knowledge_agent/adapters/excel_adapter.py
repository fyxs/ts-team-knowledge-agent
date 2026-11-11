from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from openpyxl import load_workbook

DEFAULT_SHEET_ROWS = 5000

_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _clean(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")).strip()


def _column_index(letters: str) -> int:
    index = 0
    for char in letters:
        index = index * 26 + (ord(char.upper()) - ord("A") + 1)
    return index - 1


def _has_cached_values(source: Path) -> bool:
    """判断 xlsx 里公式是否带缓存值。

    Agent 读知识库要的是「人打开 Excel 看到的数」，不是 =VLOOKUP(...) 的源码。
    但程序生成的 xlsx 可能没有缓存值，此时 data_only=True 会读出一片空白，
    所以要先探测：只有存在公式且没有 <v> 缓存时，才退回读公式。
    """

    try:
        with zipfile.ZipFile(source) as archive:
            for name in archive.namelist():
                if not name.startswith("xl/worksheets/") or not name.endswith(".xml"):
                    continue
                data = archive.read(name)
                if b"<f>" in data or b"<f " in data:
                    return b"<v>" in data
            return True
    except Exception:
        return True


def _openpyxl_sheets(source: Path):
    workbook = load_workbook(source, read_only=True, data_only=_has_cached_values(source))
    for worksheet in workbook.worksheets:
        yield worksheet.title, worksheet.iter_rows(values_only=True)


def _zip_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        raw = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ElementTree.fromstring(raw)
    return ["".join(node.text or "" for node in item.iter(f"{_MAIN}t")) for item in root.findall(f"{_MAIN}si")]


def _zip_sheet_paths(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {node.get("Id"): node.get("Target", "") for node in relationships}
    sheets: list[tuple[str, str]] = []
    container = workbook.find(f"{_MAIN}sheets")
    for sheet in container if container is not None else []:
        target = targets.get(sheet.get(f"{_REL}id"), "")
        if target.startswith("/"):
            target = target[1:]
        elif not target.startswith("xl/"):
            target = "xl/" + target
        sheets.append((sheet.get("name") or "Sheet", target))
    return sheets


def _zip_cell_text(cell: ElementTree.Element, strings: list[str]) -> str:
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{_MAIN}t"))
    value = cell.find(f"{_MAIN}v")
    if value is None:
        return ""
    text = value.text or ""
    if kind == "s":
        try:
            return strings[int(text)]
        except (ValueError, IndexError):
            return ""
    return text


def _zip_sheets(source: Path):
    """不解析 styles.xml 的兜底读取。

    openpyxl 遇到历史文件里非法的 fill/border 定义会抛
    TypeError: expected <class 'openpyxl.styles.fills.Fill'>（实测两份历史 xlsx），
    但单元格数据本身是好的 —— 这类文件只能绕过样式解析，直接读 OOXML 的 sheetData。
    """

    with zipfile.ZipFile(source) as archive:
        strings = _zip_shared_strings(archive)
        for title, path in _zip_sheet_paths(archive):
            root = ElementTree.fromstring(archive.read(path))
            rows: list[list[str]] = []
            for row in root.iter(f"{_MAIN}row"):
                values: dict[int, str] = {}
                for position, cell in enumerate(row.findall(f"{_MAIN}c")):
                    reference = re.match(r"([A-Za-z]+)", cell.get("r") or "")
                    index = _column_index(reference.group(1)) if reference else position
                    values[index] = _zip_cell_text(cell, strings)
                if values:
                    rows.append([values.get(index, "") for index in range(max(values) + 1)])
            yield title, rows


def _trim_row(row) -> list | None:
    """去掉行尾的空单元格；整行为空则返回空列表（由调用方决定是否跳过）。

    xlsx 因格式残留常把整表撑到 16384 列，未修剪时一个 sheet 能写出 5MB 空列。
    """

    if row is None:
        return None
    values = list(row)
    while values and (values[-1] is None or (isinstance(values[-1], str) and not values[-1].strip())):
        values.pop()
    return values


def _safe_sheet_name(title: str, sheet_index: int) -> str:
    """把 sheet 名变成合法文件名：只去掉 Windows 禁止的字符，保留中文。

    历史缺陷：早期正则写成 [^0-9A-Za-z_-]+ → "_"，把中文名全部清空，
    于是同一文件里所有中文 sheet 都落到同一个 Sheet1.md，后者覆盖前者。
    实测 附件2.1 23 张只剩 3 张、附件2.2 26 张只剩 2 张，共丢 151 张表。
    """

    safe = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", title).strip(" .")
    safe = re.sub(r"\s+", " ", safe)
    return safe or f"Sheet{sheet_index}"


def _write_sheets(sheets, output: Path, sheets_dir: Path, max_rows: int) -> int:
    index = [f"# {output.stem}", "", "## Sheets", ""]
    total = 0
    used: set[str] = set()
    for sheet_index, (title, rows) in enumerate(sheets, start=1):
        iterator = iter(rows)
        header = _trim_row(next(iterator, None))
        if header is None:
            continue
        chunk: list = []
        part = 1
        files: list[Path] = []
        data_rows = 0

        def flush() -> None:
            nonlocal chunk, part, total
            if not chunk:
                return
            # 列宽按本批真实内容取：xlsx 常因格式把 max_column 撑到 16384，
            # 直接照抄会生成几十万个空 ColumnN，一个 sheet 就能到 5MB。
            width = max([len(header)] + [len(row) for row in chunk])
            headers = [_clean(value) or f"Column{position + 1}"
                       for position, value in enumerate(list(header) + [None] * (width - len(header)))]
            base_name = _safe_sheet_name(title, sheet_index)
            safe = base_name if part == 1 else f"{base_name}-{part:03d}"
            # 同名冲突兜底：极少数文件里两个 sheet 名只差非法字符，归一后相同
            unique = safe
            bump = 2
            while unique in used:
                unique = f"{safe}-dup{bump}"
                bump += 1
            used.add(unique)
            name = f"{unique}.md"
            target = sheets_dir / name
            lines = [f"# {title}" if part == 1 else f"# {title} (part {part})", "",
                     "| " + " | ".join(headers) + " |",
                     "|" + "|".join("---" for _ in headers) + "|"]
            lines += ["| " + " | ".join(_clean(value) for value in list(row) + [None] * (width - len(row))) + " |"
                      for row in chunk]
            target.write_text("\n".join(lines) + "\n", encoding="utf-8")
            files.append(target)
            total += target.stat().st_size
            chunk = []
            part += 1

        for row in iterator:
            chunk.append(_trim_row(row))
            data_rows += 1
            if len(chunk) >= max_rows:
                flush()
        flush()
        if files:
            index.append(f"- [{title}](sheets/{files[0].name}): {data_rows} rows, {len(files)} files")

    output.write_text("\n".join(index) + "\n", encoding="utf-8")
    return output.stat().st_size + total


def _xlrd_value(cell) -> object:
    """xlrd 单元格 → 便于写表的值（日期转 ISO，整数不带 .0）。"""

    import xlrd

    if cell.ctype == xlrd.XL_CELL_DATE:
        try:
            return xlrd.xldate.xldate_as_datetime(cell.value, 0).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return cell.value
    if cell.ctype == xlrd.XL_CELL_NUMBER:
        return int(cell.value) if float(cell.value).is_integer() else cell.value
    if cell.ctype == xlrd.XL_CELL_BOOLEAN:
        return "TRUE" if cell.value else "FALSE"
    if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
        return ""
    return cell.value


def _xlrd_sheets(source: Path):
    """读 Excel 97-2003（.xls，OLE 复合文档）。

    这类文件不是 PDF，MinerU 的 pdfium 通道读不了 —— 实测每个文件白烧 143~435 秒后
    RuntimeError（2026-11-10 一轮 286 次失败全是它）。xlrd 直接读二进制，毫秒级。
    """

    import xlrd

    workbook = xlrd.open_workbook(str(source), on_demand=True)
    try:
        for index in range(workbook.nsheets):
            sheet = workbook.sheet_by_index(index)
            rows = [
                [_xlrd_value(sheet.cell(row, column)) for column in range(sheet.ncols)]
                for row in range(sheet.nrows)
            ]
            yield sheet.name, rows
    finally:
        workbook.release_resources()


def convert_legacy_excel(source: Path, output: Path, max_rows: int = DEFAULT_SHEET_ROWS) -> int:
    """.xls 转换：xlrd 读表 → 与 .xlsx 相同的 markdown 分表写入。"""

    if max_rows < 1:
        raise ValueError("Excel sheet row limit must be at least 1")
    output.parent.mkdir(parents=True, exist_ok=True)
    sheets_dir = output.parent / "sheets"
    sheets_dir.mkdir(exist_ok=True)
    try:
        return _write_sheets(_xlrd_sheets(source), output, sheets_dir, max_rows)
    except Exception as exc:
        raise RuntimeError(f"旧版 Excel 读取失败（{source.name}）：{exc}") from exc


def convert_excel(source: Path, output: Path, max_rows: int = DEFAULT_SHEET_ROWS) -> int:
    if max_rows < 1:
        raise ValueError("Excel sheet row limit must be at least 1")
    output.parent.mkdir(parents=True, exist_ok=True)
    sheets_dir = output.parent / "sheets"
    sheets_dir.mkdir(exist_ok=True)
    try:
        return _write_sheets(_openpyxl_sheets(source), output, sheets_dir, max_rows)
    except Exception:
        for leftover in sheets_dir.glob("*.md"):
            leftover.unlink()
        return _write_sheets(_zip_sheets(source), output, sheets_dir, max_rows)
