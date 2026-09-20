from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

# ── 占位符判定 ────────────────────────────────────────────────────────────
# 门禁按「形态」匹配，技术文档里示范 API 调用写的是示例值，会被当成真凭据，
# 导致整篇文档被静默隔离。这里补一层占位符判定：明确的示例值放行，其余照拦。
#
# 收益与代价：压住「文档写 API 示例就被隔离」的误报；
# 代价是理论上真凭据若恰好含占位词会被放过 —— 因此判定只在**明确**信号下成立，
# 拿不准一律返回 False（继续拦截）。

PLACEHOLDER_SUBSTRINGS: tuple[str, ...] = (
    "xxx", "yyy", "zzz", "your", "example", "placeholder", "changeme",
    "change-me", "change_me", "redacted", "replace", "todo", "tbd",
    "undefined", "待填", "示例", "占位", "替换", "你的",
)

PLACEHOLDER_TOKENS: frozenset[str] = frozenset({
    "test", "demo", "fake", "sample", "dummy", "none", "null", "nil",
    "foo", "bar", "baz",
})

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_\-\.]{6,}")),
    ("bearer_token", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_\-\.=+/]{12,}")),
    (
        "credential_field",
        re.compile(
            r'(?i)"(?:api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|client[_-]?secret|app[_-]?secret|secret[_-]?key)"\s*:\s*"([^"]{4,})"'
        ),
    ),
    ("header_key", re.compile(r"(?i)\b(?:x-api-key|api-key)\s*[:=]\s*(\S{8,})")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)

# 匹配本身是「标记」而非凭据值，不做占位符判定
_MARKER_ONLY_KINDS = frozenset({"private_key"})

_PREFIX = re.compile(r"(?i)^(?:sk|gh[pousr]|akia|xox[baprs])[-_]?")
_BEARER = re.compile(r"(?i)^bearer\s+")
_TRIM = "\"'{}[]<>= \t`$"


def _looks_like_placeholder(value: str) -> bool:
    """判断疑似凭据的字符串是否明显是占位符/示例值。

    明确的信号（任一成立即放行）：
      ① 含占位/示例子串（xxx、your、example、redacted…）
      ② 按非字母数字切段后某段是示例词（test、demo、fake…）
      ③ 字符种类 ≤ 2（xxxxxxxx、00000000）
      ④ 整串由重复单元构成（abababab、abcabcabc）
    其余一律返回 False —— 继续按凭据拦截。
    """
    core = _BEARER.sub("", _PREFIX.sub("", (value or "").strip())).strip(_TRIM)
    if not core:
        return True

    low = core.lower()

    if any(marker in low for marker in PLACEHOLDER_SUBSTRINGS):
        return True

    if any(part in PLACEHOLDER_TOKENS for part in re.split(r"[^a-z0-9]+", low) if part):
        return True

    if len(set(core)) <= 2:
        return True

    total = len(core)
    if 4 <= total <= 128:
        for unit in range(1, total // 2 + 1):
            if total % unit == 0 and core == core[:unit] * (total // unit):
                return True

    return False


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


def _candidate_value(kind: str, match: re.Match[str]) -> str:
    """从匹配中取出「值」部分（整段匹配或第一个捕获组）。"""
    if kind == "bearer_token":
        parts = match.group(0).split(None, 1)
        return parts[1] if len(parts) > 1 else match.group(0)
    if match.groups():
        return match.group(1)
    return match.group(0)


def scan_text(text: str) -> SecretScanResult:
    findings: list[SecretFinding] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        for kind, pattern in PATTERNS:
            for match in pattern.finditer(line):
                if kind not in _MARKER_ONLY_KINDS and _looks_like_placeholder(
                    _candidate_value(kind, match)
                ):
                    continue
                findings.append(SecretFinding(kind, line_number))
                break  # 同一行同一类型只记一次（与既有行为一致）
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
