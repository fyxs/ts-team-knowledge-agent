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
from ts_knowledge_agent.services.knowledge_tools import locate_sources

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
    # 本轮是否真正检索过知识库。模型偶尔会跳过检索直接作答，
    # 这里给出可判定的事实，供调用方提示或拦截。
    retrieved: bool = False
    # citations 的结构化补充（标题 + 命中行号与片段）。路径字符串那条链路保持不变，
    # CLI 与评测仍按字符串列表消费；界面要的是这一份。
    sources: list[dict] = field(default_factory=list)


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
    # 每条被检索/读取过的路径的证据强度：用于决定最终展示几条来源
    evidence: dict[str, dict] = {}
    # 模型检索时用的查询词：结构化来源要据此在文档里定位命中行。
    search_terms: list[str] = []

    def build_sources() -> list[dict]:
        """把本轮引用补成结构化来源（标题 + 命中行号与片段）。

        只在出口算一次，且只查被引用的那几篇；模型没有检索词时不编造命中。
        """

        return [source.to_dict() for source in locate_sources(settings, displayed_paths(), search_terms)]

    def displayed_paths() -> list[str]:
        """展示用来源：按证据强度筛过、带上限；citations 与 sources 用同一份，避免数量对不上。"""
        return rank_sources(
            citations,
            evidence,
            max_display=settings.sources_max_display,
            ratio=settings.sources_relevance_ratio,
        )

    nudged = False
    emit({"type": "start", "question": question})
    for step in range(1, max_steps + 1):
        reply = provider.chat(list(transcript), TOOL_SCHEMAS)
        if reply.error:
            emit({"type": "error", "error": reply.error, "step": step})
            return AgentResult(
                    answer="",
                    citations=displayed_paths(),
                    steps=step,
                    error=reply.error,
                    transcript=transcript,
                    retrieved=bool(citations),
                    sources=build_sources(),
                )
        if not reply.tool_calls:
            content = (reply.content or "").strip()
            markup = _tool_markup_marker(content)
            if markup:
                emit({"type": "error", "error": f"provider returned tool markup as text ({markup})", "step": step})
                return AgentResult(
                    answer=content,
                    citations=displayed_paths(),
                    steps=step,
                    error=f"provider returned tool markup as text ({markup}); tools were not honored",
                    transcript=transcript,
                    sources=build_sources(),
                )
            if not citations and not nudged and step < max_steps:
                nudged = True
                emit({"type": "notice", "message": "模型未检索即作答，已要求其先检索知识库"})
                transcript.append(
                    {
                        "role": "user",
                        "content": "注意：涉及团队知识的事实性问题必须先调用 knowledge_search 检索，并引用检索到的来源。请先检索再作答。",
                    }
                )
                continue
            answer_sources = build_sources()
            emit({"type": "answer", "content": content, "citations": displayed_paths(), "sources": answer_sources, "steps": step, "retrieved": bool(citations)})
            return AgentResult(
                answer=content,
                citations=displayed_paths(),
                steps=step,
                transcript=transcript,
                retrieved=bool(citations),
                sources=answer_sources,
            )
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
            if found:
                _record_evidence(evidence, output, found)
            if call["name"] == "knowledge_search":
                query = _query_argument(call.get("arguments"))
                if query:
                    search_terms.append(query)
            emit({"type": "tool_result", "name": call["name"], "paths": found, "step": step})
            transcript.append({"role": "tool", "tool_call_id": call["id"], "content": output})
    emit({"type": "error", "error": "max_steps_exceeded", "step": max_steps})
    return AgentResult(
        answer="",
        citations=displayed_paths(),
        steps=max_steps,
        error="max_steps_exceeded",
        transcript=transcript,
        retrieved=bool(citations),
        sources=build_sources(),
    )


def _query_argument(arguments: object) -> str:
    """取检索工具调用里的查询词；模型给的不是字符串时按「没有查询词」处理。"""

    if not isinstance(arguments, dict):
        return ""
    value = arguments.get("query")
    return value.strip() if isinstance(value, str) else ""


def _evidence_from(output: str) -> list[tuple[str, str]]:
    """从工具输出里取「路径 + 证据类型」。

    read      被 knowledge_read / knowledge_document 打开过（模型主动要看这篇）
    strong    关键词（FTS）命中
    weak      兜底子串命中
    """
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return []

    items = payload if isinstance(payload, list) else [payload]
    pairs: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        if not isinstance(path, str) or not path:
            continue
        matched_by = str(item.get("matched_by") or "")
        if not matched_by:
            pairs.append((path, "read"))
        else:
            pairs.append((path, "weak" if matched_by == "substring" else "strong"))
    return pairs


def _record_evidence(evidence: dict[str, dict], output: str, paths: list[str]) -> None:
    """累积每条被检索/读取过的路径的证据强度。"""
    pairs = _evidence_from(output) or [(path, "read") for path in paths]
    for path, kind in pairs:
        record = evidence.setdefault(path, {"hits": 0, "strong": False, "read": False})
        record["hits"] += 1
        if kind == "read":
            record["read"] = True
        elif kind == "strong":
            record["strong"] = True


def rank_sources(
    paths: list[str],
    evidence: dict[str, dict],
    *,
    max_display: int = 8,
    ratio: float = 0.5,
) -> list[str]:
    """挑出真正要展示的来源。

    强度 = 3×被打开过 + 2×关键词命中 + min(命中次数, 3)；低于最高强度 ratio 倍的不展示，
    最后按上限截断。目的：**来源数量由证据决定，而不是由模型搜了几次决定**。
    """
    ordered = _unique(paths)
    if not ordered:
        return []

    scored: list[tuple[int, int, str]] = []
    for index, path in enumerate(ordered):
        record = evidence.get(path) or {}
        score = (3 if record.get("read") else 0) + (2 if record.get("strong") else 0) + min(int(record.get("hits") or 0), 3)
        scored.append((score, index, path))

    best = max(score for score, _, _ in scored)
    threshold = best * ratio
    ranked = sorted(scored, key=lambda item: (-item[0], item[1]))
    kept = [path for score, _, path in ranked if score >= threshold]
    return kept[: max(1, max_display)]


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
