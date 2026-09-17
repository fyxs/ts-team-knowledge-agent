from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Protocol
from ts_knowledge_agent.adapters.mineru_adapter import MinerUConverter
from ts_knowledge_agent.adapters.excel_adapter import convert_excel

CONVERTER_VERSION = "mineru-3.4.5"
CONVERTER_MARKDOWN_COPY = "markdown-copy"
CONVERTER_TEXT_DECODE = "text-decode"
CONVERTER_EXCEL = "excel-adapter"
CONVERTER_INJECTED = "custom-converter"
SUPPORTED_DIRECT_COPY_EXTENSIONS = frozenset({".md"})
SUPPORTED_TEXT_EXTENSIONS = frozenset({".txt"})
SUPPORTED_MINERU_EXTENSIONS = frozenset({".ppt", ".pptx", ".doc", ".docx", ".xls", ".xlsx", ".pdf"})
SUPPORTED_EXTENSIONS = SUPPORTED_DIRECT_COPY_EXTENSIONS | SUPPORTED_TEXT_EXTENSIONS | SUPPORTED_MINERU_EXTENSIONS
class Converter(Protocol):
    def convert(self, source: Path) -> str: ...
def is_supported(source: Path) -> bool: return source.suffix.lower() in SUPPORTED_EXTENSIONS
def is_direct_copy(source: Path) -> bool: return source.suffix.lower() in SUPPORTED_DIRECT_COPY_EXTENSIONS
ORIGIN_SOURCE = "source"
"""输出内容来自源文件本身（直复制、文本重解码）；质量问题只可能来自源文件。"""

ORIGIN_TOOL = "tool"
"""输出由转换工具生成（MinerU、Excel 适配器或注入的转换器）；质量问题可能由转换引入。"""


@dataclass(frozen=True)
class ConversionResult:
    source_path: Path
    output_path: Path
    bytes_written: int
    origin: str = ORIGIN_TOOL
    converter: str = CONVERTER_VERSION

    @property
    def from_source(self) -> bool:
        return self.origin == ORIGIN_SOURCE

def _decode_text(source: Path) -> str:
    raw = source.read_bytes()
    if b"\x00" in raw:
        raise ValueError(f"text source appears to be binary: {source}")
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeError(f"unable to decode text source as UTF-8 or GB18030: {source}")

HEAVY_SUFFIXES = frozenset({".pdf", ".docx", ".doc", ".pptx", ".ppt"})


def conversion_cost_class(source: Path) -> int:
    """转换代价分级：0=轻量（md 直接复制 / txt 转码 / xlsx 表格），1=重活（MinerU 推理）。

    队列按此排序，让新加入的 md/txt 优先入库，不被大文件堵在后面
    （实测一轮 15~30 分钟，绝大部分时间花在 pdf/pptx 的 CPU 推理上）。
    """
    return 1 if source.suffix.lower() in HEAVY_SUFFIXES else 0


def convert_file(source: Path, output: Path, converter: Converter | None = None, mineru_python: str | Path | None = None) -> ConversionResult:
    source=source.expanduser().resolve(); output=output.expanduser().resolve()
    if not source.is_file(): raise FileNotFoundError(f"source file does not exist: {source}")
    if source == output: raise ValueError("conversion output must not overwrite the source file")
    if not is_supported(source): raise ValueError(f"unsupported source format: {source.suffix or '<no extension>'}")
    output.parent.mkdir(parents=True, exist_ok=True)
    extension = source.suffix.lower()
    if converter is not None:
        output.write_text(converter.convert(source), encoding="utf-8")
        origin = ORIGIN_TOOL; label = CONVERTER_INJECTED
    elif is_direct_copy(source):
        shutil.copy2(source, output)
        origin = ORIGIN_SOURCE; label = CONVERTER_MARKDOWN_COPY
    elif extension == ".txt":
        output.write_text(_decode_text(source), encoding="utf-8")
        origin = ORIGIN_SOURCE; label = CONVERTER_TEXT_DECODE
    elif extension == ".xlsx":
        convert_excel(source, output)
        origin = ORIGIN_TOOL; label = CONVERTER_EXCEL
    else:
        MinerUConverter(mineru_python).convert_to(source, output)
        origin = ORIGIN_TOOL; label = CONVERTER_VERSION
    return ConversionResult(source, output, output.stat().st_size, origin, label)
