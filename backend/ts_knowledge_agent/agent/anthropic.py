from __future__ import annotations

import json
import urllib.request

from ts_knowledge_agent.agent.provider_types import ProviderReply

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_BASE_URL = "https://api.anthropic.com"
DEFAULT_MAX_TOKENS = 4096


def extract_system(messages: list[dict]) -> str:
    parts = [message.get("content", "") for message in messages if message.get("role") == "system" and message.get("content")]
    return "\n\n".join(part for part in parts if part)


def to_anthropic_tools(tools: list[dict]) -> list[dict]:
    converted = []
    for tool in tools or []:
        function = tool.get("function") or {}
        if not function.get("name"):
            continue
        converted.append({
            "name": function.get("name"),
            "description": function.get("description") or "",
            "input_schema": function.get("parameters") or {"type": "object", "properties": {}},
        })
    return converted


def to_anthropic_messages(messages: list[dict]) -> list[dict]:
    """把内部 OpenAI 风格的消息转换为 Anthropic Messages 格式。"""

    result: list[dict] = []
    pending_results: list[dict] = []

    def flush() -> None:
        if pending_results:
            result.append({"role": "user", "content": list(pending_results)})
            pending_results.clear()

    for message in messages:
        role = message.get("role")
        if role == "system":
            continue
        if role == "tool":
            pending_results.append({
                "type": "tool_result",
                "tool_use_id": message.get("tool_call_id") or "",
                "content": message.get("content") or "",
            })
            continue
        flush()
        if role == "user":
            result.append({"role": "user", "content": [{"type": "text", "text": message.get("content") or ""}]})
        elif role == "assistant":
            blocks: list[dict] = []
            if message.get("content"):
                blocks.append({"type": "text", "text": message["content"]})
            for call in message.get("tool_calls") or []:
                function = call.get("function") or {}
                raw = function.get("arguments")
                if isinstance(raw, str):
                    try:
                        parsed = json.loads(raw)
                    except json.JSONDecodeError:
                        parsed = {}
                else:
                    parsed = raw or {}
                blocks.append({
                    "type": "tool_use",
                    "id": call.get("id") or "call_0",
                    "name": function.get("name") or "",
                    "input": parsed,
                })
            result.append({"role": "assistant", "content": blocks or [{"type": "text", "text": ""}]})
    flush()
    return result


def from_anthropic_response(body: dict) -> ProviderReply:
    texts: list[str] = []
    calls: list[dict] = []
    for index, block in enumerate(body.get("content") or []):
        block_type = block.get("type")
        if block_type == "text":
            texts.append(block.get("text") or "")
        elif block_type == "tool_use":
            calls.append({
                "id": block.get("id") or f"call_{index}",
                "name": block.get("name") or "",
                "arguments": block.get("input") or {},
            })
    return ProviderReply(content="\n".join(text for text in texts if text).strip(), tool_calls=calls)


class AnthropicProvider:
    """Anthropic Messages API。凭据只从环境读取，不写入仓库。"""

    def __init__(self, api_key: str, model: str, base_url: str = DEFAULT_BASE_URL, max_tokens: int = DEFAULT_MAX_TOKENS, timeout: int = 90) -> None:
        if not api_key or not model:
            raise ValueError("api_key and model are required")
        self.api_key = api_key
        self.model = model
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.max_tokens = max_tokens
        self.timeout = timeout

    def build_payload(self, messages: list[dict], tools: list[dict]) -> dict:
        payload: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": to_anthropic_messages(messages),
        }
        system = extract_system(messages)
        if system:
            payload["system"] = system
        converted = to_anthropic_tools(tools)
        if converted:
            payload["tools"] = converted
        return payload

    def headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        }

    def chat(self, messages: list[dict], tools: list[dict]) -> ProviderReply:
        request = urllib.request.Request(
            f"{self.base_url}/v1/messages",
            data=json.dumps(self.build_payload(messages, tools), ensure_ascii=False).encode("utf-8"),
            headers=self.headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read())
        except Exception as exc:
            return ProviderReply(error=f"{type(exc).__name__}: {exc}")
        if body.get("error"):
            return ProviderReply(error=str(body["error"]))
        return from_anthropic_response(body)
