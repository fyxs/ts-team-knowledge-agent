from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Protocol
from ts_knowledge_agent.adapters.mineru_adapter import MinerUConverter
from ts_knowledge_agent.adapters.excel_adapter import convert_excel

CONVERTER_VERSION = "mineru-3.4.5"
SUPPORTED_DIRECT_COPY_EXTENSIONS = frozenset({".md", ".txt"})
SUPPORTED_MINERU_EXTENSIONS = frozenset({".ppt", ".pptx", ".doc", ".docx", ".xls", ".xlsx", ".pdf"})
SUPPORTED_EXTENSIONS = SUPPORTED_DIRECT_COPY_EXTENSIONS | SUPPORTED_MINERU_EXTENSIONS
class Converter(Protocol):
    def convert(self, source: Path) -> str: ...
def is_supported(source: Path) -> bool: return source.suffix.lower() in SUPPORTED_EXTENSIONS
def is_direct_copy(source: Path) -> bool: return source.suffix.lower() in SUPPORTED_DIRECT_COPY_EXTENSIONS
@dataclass(frozen=True)
class ConversionResult:
    source_path: Path
    output_path: Path
    bytes_written: int
def convert_file(source: Path, output: Path, converter: Converter | None = None, mineru_python: str | Path | None = None) -> ConversionResult:
    source=source.expanduser().resolve(); output=output.expanduser().resolve()
    if not source.is_file(): raise FileNotFoundError(f"source file does not exist: {source}")
    if source == output: raise ValueError("conversion output must not overwrite the source file")
    if not is_supported(source): raise ValueError(f"unsupported source format: {source.suffix or '<no extension>'}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if converter is not None: output.write_text(converter.convert(source), encoding="utf-8")
    elif is_direct_copy(source): shutil.copy2(source, output)
    elif source.suffix.lower() in {".xls", ".xlsx"}: convert_excel(source, output)
    else: MinerUConverter(mineru_python).convert_to(source, output)
    return ConversionResult(source, output, output.stat().st_size)
