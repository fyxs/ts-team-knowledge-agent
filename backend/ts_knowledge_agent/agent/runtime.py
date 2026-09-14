from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, field

from ts_knowledge_agent.agent.anthropic import AnthropicProvider
from ts_knowledge_agent.agent.prompt import SYSTEM_PROMPT_VERSION, build_system_prompt
from ts_knowledge_agent.agent.provider_types import Provider, ProviderReply
from ts_knowledge_agent.agent.skills import Skill, load_skills
from ts_knowledge_agent.agent.tools import dispatch_tool
from ts_knowledge_agent.config import Settings

DEFAULT_MAX_STEPS = 6

__all__ = [
    "AgentResult",
    "AnthropicProvider",
    "DEFAULT_MAX_STEPS",
    "OpenAICompatibleProvider",
    "Provider",
    "ProviderReply",
    "create_provider_from_env",
    "run_agent",
]


@dataclass
class AgentResult:
    answer: str
    citations: list[str]
    steps: int
    prompt_version: str = SYSTEM_PROMPT_VERSION
    error: str | None = None
    transcript: list[dict] = field(default_factory=list)


class OpenAICompatibleProvider:
    """任意 OpenAI 兼容的 chat/completions 端点。凭据只从环境读取，不写入仓库。"""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 90) -> None:
        if not base_url or not api_key or not model:
            raise ValueError("base_url, api_key and model are required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def chat(self, messages: list[dict], tools: list[dict]) -> ProviderReply:
        payload: dict = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read())
        except Exception as exc:
            return ProviderReply(error=f"{type(exc).__name__}: {exc}")
        choices = body.get("choices") or []
        if not choices:
            return ProviderReply(error="provider returned no choices")
        message = choices[0].get("message") or {}
        calls = []
        for call in message.get("tool_calls") or []:
            raw = (call.get("function") or {}).get("arguments") or "{}"
            try:
                arguments = json.loads(raw)
            except json.JSONDecodeError:
                arguments = {}
            calls.append({"id": call.get("id") or "call_0", "name": (call.get("function") or {}).get("name") or "", "arguments": arguments})
        return ProviderReply(content=message.get("content") or "", tool_calls=calls)


def create_provider_from_env() -> Provider | None:
    """按环境变量创建 provider；未配置完整时返回 None，由调用方给出明确提示。"""

    provider_name = os.getenv("TS_TEAM_KB_MODEL_PROVIDER", "").strip().lower()
    model = os.getenv("TS_TEAM_KB_MODEL_NAME", "").strip()
    api_key = os.getenv("TS_TEAM_KB_MODEL_API_KEY", "").strip()
    base_url = os.getenv("TS_TEAM_KB_MODEL_BASE_URL", "").strip()
    max_tokens = int(os.getenv("TS_TEAM_KB_MODEL_MAX_TOKENS", "4096") or 4096)

    if provider_name in {"anthropic", "claude"} or (not provider_name and "anthropic" in base_url):
        if not (api_key and model):
            return None
        return AnthropicProvider(api_key=api_key, model=model, base_url=base_url, max_tokens=max_tokens)
    if not (base_url and api_key and model):
        return None
    return OpenAICompatibleProvider(base_url, api_key, model)


def run_agent(settings: Settings, question: str, provider: Provider, skills: list[Skill] | None = None, max_steps: int = DEFAULT_MAX_STEPS) -> AgentResult:
    """最小 Agent 循环：模型调用工具、运行时执行并把结果回灌，直到模型给出最终回答。"""

    question = (question or "").strip()
    if not question:
        raise ValueError("question must not be empty")
    active_skills = load_skills() if skills is None else skills
    transcript: list[dict] = [
        {"role": "system", "content": build_system_prompt(active_skills)},
        {"role": "user", "content": question},
    ]
    citations: list[str] = []
    for step in range(1, max_steps + 1):
        reply = provider.chat(list(transcript), [])
        if reply.error:
            return AgentResult(answer="", citations=_unique(citations), steps=step, error=reply.error, transcript=transcript)
        if not reply.tool_calls:
            return AgentResult(answer=reply.content.strip(), citations=_unique(citations), steps=step, transcript=transcript)
        transcript.append({
            "role": "assistant",
            "content": reply.content or "",
            "tool_calls": [
                {"id": call["id"], "type": "function", "function": {"name": call["name"], "arguments": json.dumps(call["arguments"], ensure_ascii=False)}}
                for call in reply.tool_calls
            ],
        })
        for call in reply.tool_calls:
            output = dispatch_tool(settings, active_skills, call["name"], call["arguments"])
            citations.extend(_paths_from(output))
            transcript.append({"role": "tool", "tool_call_id": call["id"], "content": output})
    return AgentResult(answer="", citations=_unique(citations), steps=max_steps, error="max_steps_exceeded", transcript=transcript)


def _paths_from(output: str) -> list[str]:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return []
    found: list[str] = []
    if isinstance(payload, dict):
        if isinstance(payload.get("path"), str):
            found.append(payload["path"])
        for value in payload.get("failures") or []:
            if isinstance(value, dict) and isinstance(value.get("path"), str):
                found.append(value["path"])
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and isinstance(item.get("path"), str):
                found.append(item["path"])
    return found


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
