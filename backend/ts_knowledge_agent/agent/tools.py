from __future__ import annotations

import json

from ts_knowledge_agent.agent.skills import Skill, find_skill
from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.services.knowledge_tools import (
    knowledge_list,
    knowledge_read,
    knowledge_search,
    knowledge_status,
)

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "knowledge_search",
            "description": "检索团队知识库，返回匹配文档的路径、标题与片段。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索关键词"},
                    "limit": {"type": "integer", "description": "返回条数，默认 5"},
                    "member": {"type": "string", "description": "限定成员空间，可省略"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "knowledge_read",
            "description": "分页读取知识文档内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "knowledge_search 返回的路径"},
                    "offset": {"type": "integer", "description": "起始行，默认 0"},
                    "limit": {"type": "integer", "description": "读取行数，默认 200"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "knowledge_list",
            "description": "列出已索引的知识文档。",
            "parameters": {
                "type": "object",
                "properties": {
                    "member": {"type": "string"},
                    "prefix": {"type": "string"},
                    "limit": {"type": "integer", "description": "默认 200"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {"name": "knowledge_status", "description": "查看知识库转换状态与失败文件。", "parameters": {"type": "object", "properties": {}}},
    },
    {
        "type": "function",
        "function": {
            "name": "load_skill",
            "description": "按名称加载技能说明。",
            "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        },
    },
]

TOOL_NAMES = [schema["function"]["name"] for schema in TOOL_SCHEMAS]


def dispatch_tool(settings: Settings, skills: list[Skill], name: str, arguments: dict) -> str:
    """执行一次工具调用，返回给模型的 JSON 字符串；错误以 error 字段返回而不是抛出。"""

    arguments = arguments or {}
    try:
        if name == "knowledge_search":
            hits = knowledge_search(settings, arguments.get("query", ""), limit=int(arguments.get("limit") or 5), member=arguments.get("member"))
            return json.dumps([hit.__dict__ for hit in hits], ensure_ascii=False)
        if name == "knowledge_read":
            document = knowledge_read(settings, arguments.get("path", ""), offset=int(arguments.get("offset") or 0), limit=int(arguments.get("limit") or 200))
            return json.dumps(document.__dict__, ensure_ascii=False)
        if name == "knowledge_list":
            return json.dumps(knowledge_list(settings, member=arguments.get("member"), prefix=arguments.get("prefix"), limit=int(arguments.get("limit") or 200)), ensure_ascii=False)
        if name == "knowledge_status":
            return json.dumps(knowledge_status(settings), ensure_ascii=False)
        if name == "load_skill":
            skill = find_skill(skills, arguments.get("name", ""))
            if skill is None:
                return json.dumps({"error": f"unknown skill: {arguments.get('name')}"}, ensure_ascii=False)
            return json.dumps({"name": skill.name, "description": skill.description, "body": skill.body}, ensure_ascii=False)
        return json.dumps({"error": f"unknown tool: {name}"}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)
