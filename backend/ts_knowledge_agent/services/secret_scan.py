from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_\-\.]{6,}")),
    ("bearer_token", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_\-\.=+/]{12,}")),
    (
        "credential_field",
        re.compile(
            r'(?i)"(?:api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|client[_-]?secret|app[_-]?secret|secret[_-]?key)"\s*:\s*"(?!\[REDACTED\])[^"]{4,}"'
        ),
    ),
    ("header_key", re.compile(r"(?i)\b(?:x-api-key|api-key)\s*[:=]\s*(?!\[REDACTED\])\S{8,}")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)


@dataclass(frozen=True)
class SecretFinding:
    kind: str
    line: int


@dataclass(frozen=True)
class SecretScanResult:
    ok: bool
    findings: tuple[SecretFinding, ...]

    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted({finding.kind for finding in self.findings}))

    def summary(self) -> str:
        return ", ".join(f"{finding.kind}@L{finding.line}" for finding in self.findings)


def scan_text(text: str) -> SecretScanResult:
    findings = [
        SecretFinding(kind, line_number)
        for line_number, line in enumerate(text.splitlines(), 1)
        for kind, pattern in PATTERNS
        if pattern.search(line)
    ]
    return SecretScanResult(not findings, tuple(findings))


def scan_markdown_file(path: Path) -> SecretScanResult:
    return scan_text(Path(path).read_text(encoding="utf-8", errors="replace"))


def quarantine_document(working_directory: Path, repository_root: Path, document_directory: Path) -> Path:
    """Move a document directory out of the shared repository so it is never synced."""
    working_directory = Path(working_directory)
    repository_root = Path(repository_root)
    document_directory = Path(document_directory)
    try:
        relative = document_directory.relative_to(repository_root)
    except ValueError:
        relative = Path(document_directory.name)
    target = working_directory / "quarantine" / relative
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    if document_directory.exists():
        shutil.move(str(document_directory), str(target))
    return target
