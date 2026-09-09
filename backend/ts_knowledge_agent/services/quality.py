from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re

@dataclass(frozen=True)
class QualityReport:
    errors: tuple[str,...]=()
    warnings: tuple[str,...]=()
    @property
    def ok(self)->bool: return not self.errors

def inspect_markdown(text: str)->QualityReport:
    errors=[]; warnings=[]
    if not text.strip(): errors.append("empty markdown output")
    if "\ufffd" in text: errors.append("contains Unicode replacement characters")
    if "\x00" in text: errors.append("contains NUL bytes")
    if not re.search(r"^#\s+\S+",text,re.MULTILINE): warnings.append("no Markdown H1 title detected")
    if len(text.strip())<80: warnings.append("very short markdown output")
    repeated=re.findall(r"(.)\1{2,}",text)
    if repeated: warnings.append(f"contains {len(repeated)} adjacent repeated-character patterns")
    return QualityReport(tuple(errors),tuple(warnings))

def inspect_markdown_file(path: Path)->QualityReport:
    try: data=path.read_bytes()
    except OSError as exc: return QualityReport((f"cannot read markdown output: {exc}",),())
    if b"\x00" in data: return QualityReport(("contains NUL bytes",),())
    try: text=data.decode("utf-8")
    except UnicodeDecodeError as exc: return QualityReport((f"invalid UTF-8 markdown output: {exc}",),())
    return inspect_markdown(text)
