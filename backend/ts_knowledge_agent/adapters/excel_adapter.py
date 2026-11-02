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


def _openpyxl_sheets(source: Path):
    workbook = load_workbook(source, read_only=True, data_only=False)
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


def _write_sheets(sheets, output: Path, sheets_dir: Path, max_rows: int) -> int:
    index = [f"# {output.stem}", "", "## Sheets", ""]
    total = 0
    for title, rows in sheets:
        iterator = iter(rows)
        header = next(iterator, None)
        if header is None:
            continue
        headers = [_clean(value) or f"Column{position + 1}" for position, value in enumerate(header)]
        chunk: list = []
        part = 1
        files: list[Path] = []
        data_rows = 0

        def flush() -> None:
            nonlocal chunk, part, total
            if not chunk:
                return
            safe = re.sub(r"[^0-9A-Za-z_-]+", "_", title).strip("_") or f"Sheet{part}"
            name = f"{safe}.md" if part == 1 else f"{safe}-{part:03d}.md"
            target = sheets_dir / name
            lines = [f"# {title}" if part == 1 else f"# {title} (part {part})", "",
                     "| " + " | ".join(headers) + " |",
                     "|" + "|".join("---" for _ in headers) + "|"]
            lines += ["| " + " | ".join(_clean(value) for value in row[:len(headers)]) + " |" for row in chunk]
            target.write_text("\n".join(lines) + "\n", encoding="utf-8")
            files.append(target)
            total += target.stat().st_size
            chunk = []
            part += 1

        for row in iterator:
            chunk.append(row)
            data_rows += 1
            if len(chunk) >= max_rows:
                flush()
        flush()
        if files:
            index.append(f"- [{title}](sheets/{files[0].name}): {data_rows} rows, {len(files)} files")

    output.write_text("\n".join(index) + "\n", encoding="utf-8")
    return output.stat().st_size + total


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
