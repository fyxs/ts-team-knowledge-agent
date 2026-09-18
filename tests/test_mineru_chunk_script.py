"""MinerU 内嵌脚本：分片能力存在且运行时可编译。

这条元测试的价值：内嵌脚本是字符串，改坏只在真实转换时才炸（且要等到跑大 PDF）。
用 AST 取出运行时真正写入的脚本文本并编译它，把这类错误挡在提交前。
"""

import ast

from ts_knowledge_agent.adapters import mineru_adapter


def _embedded_script() -> str:
    source = open(mineru_adapter.__file__, encoding="utf-8").read()
    tree = ast.parse(source)

    def fold(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return fold(node.left) + fold(node.right)
        raise TypeError(type(node).__name__)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "write_text":
            for arg in node.args:
                try:
                    value = fold(arg)
                except Exception:
                    continue
                if isinstance(value, str) and value.lstrip().startswith("from pathlib"):
                    return value
    raise AssertionError("找不到内嵌的 MinerU 运行脚本")


def test_embedded_script_compiles() -> None:
    ast.parse(_embedded_script())


def test_embedded_script_supports_chunking() -> None:
    script = _embedded_script()
    assert "start_page_id" in script and "end_page_id" in script
    assert "merge_parts" in script
    # 分片图片必须加片名前缀，否则不同片的同名图片互相覆盖
    assert 'images/" + tag + "_' in script


def test_converter_accepts_chunk_pages() -> None:
    converter = mineru_adapter.MinerUConverter(__file__, timeout_seconds=120, chunk_pages=50)
    assert converter.chunk_pages == 50
    assert converter.timeout_seconds == 120
