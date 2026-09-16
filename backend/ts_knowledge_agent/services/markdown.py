"""知识文档的呈现层规范化。

MinerU 转换出的文档里有一批保留了原始 `<table>` 块（实测 10/104 篇）。
前端统一走 react-markdown + remark-gfm，默认**不渲染原始 HTML**，这些表格在
阅读视图里会整块消失。这里在「给人看」的出口做一次规范化，把它换成 GFM 管道表。

放在服务层而不是前端，是因为换渲染插件会引入新依赖，而表格语义本来就该在
入库/出口一侧收敛；索引内容与 agent 读到的内容都保持原样，两边的行为可以分别回归。
"""

from __future__ import annotations

import html
import re

_TABLE_BLOCK = re.compile(r"<table\b.*?</table>", re.IGNORECASE | re.DOTALL)
_TABLE_ROW = re.compile(r"<tr\b.*?</tr>", re.IGNORECASE | re.DOTALL)
_TABLE_CELL = re.compile(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", re.IGNORECASE | re.DOTALL)
_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG = re.compile(r"</?[a-zA-Z][^>]*>")

# GFM 的单元格分隔符：单元格内的竖线必须转义，否则一列会被拆成两列。
_PIPE = "|"


def _cell_text(raw: str) -> str:
    text = _BREAK.sub(" ", raw)
    text = _TAG.sub("", text)
    text = html.unescape(text)
    text = text.replace(_PIPE, "\\" + _PIPE)
    return " ".join(text.split())


def html_table_to_gfm(block: str) -> str:
    """把一段 `<table>` 转成 GFM 管道表；无法解析出行时原样返回。

    `rowspan` / `colspan` 只被丢弃属性、保留文本 —— GFM 表达不了合并单元格，
    宁可让文本按一格显示，也不要静默丢内容。实测 10 篇里只有 1 篇用到 `rowspan`。
    """

    rows: list[list[str]] = []
    for row in _TABLE_ROW.findall(block):
        cells = [_cell_text(cell) for cell in _TABLE_CELL.findall(row)]
        if cells:
            rows.append(cells)
    if not rows:
        return block
    width = max(len(row) for row in rows)
    padded = [row + [""] * (width - len(row)) for row in rows]
    header, body = padded[0], padded[1:]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines)


def normalize_html_tables(content: str) -> str:
    """把正文里所有原始 HTML 表格换成 GFM 管道表，其余内容不动。"""

    if "<table" not in content.lower():
        return content
    return _TABLE_BLOCK.sub(lambda match: html_table_to_gfm(match.group(0)), content)
