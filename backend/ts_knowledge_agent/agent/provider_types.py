from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ProviderReply:
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    error: str | None = None


class Provider(Protocol):
    model: str

    def chat(self, messages: list[dict], tools: list[dict]) -> ProviderReply: ...
