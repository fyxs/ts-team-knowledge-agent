"""用 Word COM 抽取 .doc 的正文文本，结果只从 stdout 返回（不落盘）。

为什么不落盘：本机 E-SafeNet 会对 Word 写出的文件做透明加密，
落盘的 PDF/docx 在非授权进程（如 MinerU 的独立 venv）里读到的都是密文
（实测文件头 b'b\\x14#er'，MinerU 报 "Unknown file suffix"）。
COM 返回值走内存/管道，不受加密影响。

用法：python word_worker.py <源 .doc>
输出：UTF-8 正文（\\x07 为表格单元格分隔符，\\r 为段落分隔）
"""

from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: word_worker.py <source.doc>", file=sys.stderr)
        return 2
    source = sys.argv[1]

    import pythoncom  # pywin32
    import win32com.client

    pythoncom.CoInitialize()
    application = None
    document = None
    try:
        application = win32com.client.DispatchEx("Word.Application")
        application.Visible = False
        application.DisplayAlerts = 0
        document = application.Documents.Open(source, ReadOnly=True, AddToRecentFiles=False, Visible=False)
        text = document.Content.Text or ""
    finally:
        try:
            if document is not None:
                document.Close(False)
        finally:
            if application is not None:
                try:
                    application.Quit()
                except Exception:
                    pass

    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
