"""旧版 Word（.doc）正文抽取：Word COM 子进程 → 文本 → 我们自己的 markdown。

为什么不能像 pdf/docx 那样交给 MinerU：
- .doc 是 OLE 复合文档，MinerU 的 pdfium 通道直接读会失败
  （"Failed to load document"），每个文件白烧 90~100 秒后报错；
- 先用 Word 转 PDF/docx 也不行：本机 E-SafeNet 对 Word 写出的文件透明加密，
  MinerU 的独立 venv 读到的是密文（实测 "Unknown file suffix"）。
所以让 Word 只把**正文文本**通过 stdout 交回来，落盘由我们自己写（明文）。

子进程的必要性：Word COM 遇到损坏/加密/带宏的旧文档会卡住调用线程，
子进程可以被超时终止（taskkill /T），不会把整轮转换连同锁一起拖死。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from ts_knowledge_agent.adapters.mineru_adapter import terminate_process_tree

WORD_WORKER = Path(__file__).with_name("word_worker.py")
DOC_TIMEOUT_SECONDS = 180


def extract_doc_text(source: Path, python: str | Path | None = None, timeout: int = DOC_TIMEOUT_SECONDS) -> str:
    """调用 Word 抽取正文；失败/超时抛 RuntimeError/TimeoutError。"""

    interpreter = str(python or sys.executable)
    process = subprocess.Popen(
        [interpreter, str(WORD_WORKER), str(source)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        terminate_process_tree(process)
        raise TimeoutError(f"Word 抽取超过 {timeout}s 未完成，已终止其进程树：{source}") from None
    if process.returncode or not (stdout or "").strip():
        detail = (stderr or "").strip()[-1200:]
        raise RuntimeError(f"Word 抽取正文失败（{source.name}）：{detail or f'exit={process.returncode}'}")
    return stdout


def markdown_from_word_text(text: str) -> str:
    """Word 正文 → markdown：单元格以 \\r\\x07 结尾，段落以 \\r 分隔。"""

    # 先处理「段落符 + 单元格符」组合（Word 表格单元格的真实写法），再处理残留单元格符
    normalized = text.replace("\r\x07", " | ").replace("\x07", " | ").replace("\r", "\n").replace("\x0b", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip().strip("|").strip() for line in normalized.split("\n")]
    return "\n\n".join(line for line in lines if line)
