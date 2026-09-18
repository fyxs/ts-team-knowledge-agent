"""MinerU worker 脚本：能力存在且可编译，且参数约定不被改坏。

内嵌脚本是字符串，改坏只在真实转换时才炸（且要等到跑大 PDF）。
这里直接编译运行时真正写出的脚本，把这类错误挡在提交前。
"""

import ast

from ts_knowledge_agent.adapters import mineru_adapter


def test_worker_script_compiles() -> None:
    ast.parse(mineru_adapter.WORKER_SCRIPT)


def test_worker_script_supports_page_ranges() -> None:
    script = mineru_adapter.WORKER_SCRIPT
    assert "start_page_id" in script and "end_page_id" in script
    assert "pages" in script and "parse" in script, "需要 pages/parse 两种模式"


def test_worker_script_reads_and_writes_the_documented_argv() -> None:
    script = mineru_adapter.WORKER_SCRIPT
    assert "sys.argv[1]" in script and "sys.argv[2]" in script
    assert "sys.argv[3]" in script


def test_converter_accepts_chunk_options() -> None:
    converter = mineru_adapter.MinerUConverter(__file__, timeout_seconds=120, chunk_pages=50,
                                               chunk_concurrency=3)
    assert converter.chunk_pages == 50
    assert converter.timeout_seconds == 120
    assert converter.chunk_concurrency == 3


def test_page_ranges_are_closed_intervals() -> None:
    """闭区间页段：MinerU 的 end_page_id 是含尾的，错一位就会丢页或重复页。"""

    assert mineru_adapter._page_ranges(6, 2) == [(0, 1), (2, 3), (4, 5)]
    assert mineru_adapter._page_ranges(5, 2) == [(0, 1), (2, 3), (4, 4)]
    assert mineru_adapter._page_ranges(3, 10) == [(0, 2)]
