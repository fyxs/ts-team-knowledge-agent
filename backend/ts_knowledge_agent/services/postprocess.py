"""转换产物后处理：仅在产物缺少一级标题时补一行，不改动源文件。"""

from __future__ import annotations

import re
from pathlib import Path

HEADING = re.compile(r"^#\s+\S+", re.MULTILINE)


def has_markdown_title(path: Path) -> bool:
    return bool(HEADING.search(Path(path).read_text(encoding="utf-8", errors="replace")))


def ensure_markdown_title(path: Path, title: str) -> bool:
    """产物没有一级标题时补一行 `# 标题`，返回是否发生改动。

    只用于工具转换产物：源文件直复制的产物必须与源逐字一致，不做补写。
    """

    path = Path(path)
    if has_markdown_title(path):
        return False
    text = path.read_text(encoding="utf-8")
    heading = (title or path.stem).strip() or path.stem
    path.write_text(f"# {heading}\n\n{text.lstrip()}", encoding="utf-8", newline="\n")
    return True
