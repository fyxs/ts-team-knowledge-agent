from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, field

from ts_knowledge_agent.agent.anthropic import AnthropicProvider
from ts_knowledge_agent.agent.prompt import SYSTEM_PROMPT_VERSION, build_system_prompt
from ts_knowledge_agent.agent.provider_types import Provider, ProviderReply
from ts_knowledge_agent.agent.secrets import read_api_key
from ts_knowledge_agent.agent.skills import Skill, load_skills
from ts_knowledge_agent.agent.tools import TOOL_SCHEMAS, dispatch_tool
from ts_knowledge_agent.config import Settings

DEFAULT_MAX_STEPS = 6

# 只有实际检索或读取过的文档才算引用；list/status 返回的是清单，不作为依据。
CITATION_TOOLS = frozenset({"knowledge_search", "knowledge_read"})

__all__ = [
    "AgentResult",
    "AnthropicProvider",
    "DEFAULT_MAX_STEPS",
    "OpenAICompatibleProvider",
    "Provider",
    "ProviderReply",
    "create_provider",
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


def normalize_openai_base_url(base_url: str) -> str:
    """OpenAI 兼容网关的 base_url 需要包含版本前缀（通常是 /v1）。

    用户常只填主机与端口（http://host:3000），此时补全 /v1；
    已带路径则原样保留，避免破坏 /v1、/openai/v1 等自定义前缀。
    """

    value = (base_url or "").strip().rstrip("/")
    if not value:
        return ""
    without_scheme = value.split("://", 1)[-1]
    if "/" not in without_scheme:
        return value + "/v1"
    return value


def create_provider(settings: Settings) -> Provider | None:
    """按“环境变量优先、配置文件其次”的顺序解析模型配置；密钥来自环境变量或本地密钥文件。"""

    provider_name = (os.getenv("TS_TEAM_KB_MODEL_PROVIDER") or settings.model_provider or "").strip().lower()
    base_url = (os.getenv("TS_TEAM_KB_MODEL_BASE_URL") or settings.model_base_url or "").strip()
    model = (os.getenv("TS_TEAM_KB_MODEL_NAME") or settings.model_name or "").strip()
    max_tokens = int(os.getenv("TS_TEAM_KB_MODEL_MAX_TOKENS") or settings.model_max_tokens or 4096)
    api_key = (os.getenv("TS_TEAM_KB_MODEL_API_KEY") or read_api_key(settings.working_directory)).strip()

    if provider_name in {"anthropic", "claude"} or (not provider_name and "anthropic" in base_url):
        if not (api_key and model):
            return None
        return AnthropicProvider(api_key=api_key, model=model, base_url=base_url, max_tokens=max_tokens)
    if not (base_url and api_key and model):
        return None
    return OpenAICompatibleProvider(normalize_openai_base_url(base_url), api_key, model)


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
    return OpenAICompatibleProvider(normalize_openai_base_url(base_url), api_key, model)


def run_agent(settings: Settings, question: str, provider: Provider, skills: list[Skill] | None = None, max_steps: int = DEFAULT_MAX_STEPS, on_event=None) -> AgentResult:
    """最小 Agent 循环：模型调用工具、运行时执行并把结果回灌，直到模型给出最终回答。"""

    question = (question or "").strip()
    if not question:
        raise ValueError("question must not be empty")
    emit = on_event or (lambda event: None)
    active_skills = load_skills() if skills is None else skills
    transcript: list[dict] = [
        {"role": "system", "content": build_system_prompt(active_skills)},
        {"role": "user", "content": question},
    ]
    citations: list[str] = []
    emit({"type": "start", "question": question})
    for step in range(1, max_steps + 1):
        reply = provider.chat(list(transcript), TOOL_SCHEMAS)
        if reply.error:
            emit({"type": "error", "error": reply.error, "step": step})
            return AgentResult(answer="", citations=_unique(citations), steps=step, error=reply.error, transcript=transcript)
        if not reply.tool_calls:
            content = (reply.content or "").strip()
            markup = _tool_markup_marker(content)
            if markup:
                emit({"type": "error", "error": f"provider returned tool markup as text ({markup})", "step": step})
                return AgentResult(
                    answer=content,
                    citations=_unique(citations),
                    steps=step,
                    error=f"provider returned tool markup as text ({markup}); tools were not honored",
                    transcript=transcript,
                )
            emit({"type": "answer", "content": content, "citations": _unique(citations), "steps": step})
            return AgentResult(answer=content, citations=_unique(citations), steps=step, transcript=transcript)
        transcript.append({
            "role": "assistant",
            "content": reply.content or "",
            "tool_calls": [
                {"id": call["id"], "type": "function", "function": {"name": call["name"], "arguments": json.dumps(call["arguments"], ensure_ascii=False)}}
                for call in reply.tool_calls
            ],
        })
        for call in reply.tool_calls:
            emit({"type": "tool_call", "name": call["name"], "arguments": call["arguments"], "step": step})
            output = dispatch_tool(settings, active_skills, call["name"], call["arguments"])
            found = _paths_from(output) if call["name"] in CITATION_TOOLS else []
            citations.extend(found)
            emit({"type": "tool_result", "name": call["name"], "paths": found, "step": step})
            transcript.append({"role": "tool", "tool_call_id": call["id"], "content": output})
    emit({"type": "error", "error": "max_steps_exceeded", "step": max_steps})
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

TOOL_MARKUP_MARKERS = ("<||DSML||", "</||DSML||", "<tool_call", "</tool_call", "<function_call")


def _tool_markup_marker(content: str) -> str | None:
    """模型把工具调用当作文本输出时返回命中的标记，否则返回 None。"""

    for marker in TOOL_MARKUP_MARKERS:
        if marker in content:
            return marker
    return None
