from __future__ import annotations

import getpass
from dataclasses import replace
from typing import Callable

from ts_knowledge_agent.agent.secrets import secret_path, write_api_key
from ts_knowledge_agent.config import Settings

ANTHROPIC_DEFAULT_BASE_URL = "https://api.anthropic.com"


def parse_provider(value: str) -> str:
    return value.strip().lower() or "openai"


def resolve_base_url(provider: str, value: str) -> str:
    base_url = value.strip()
    if base_url:
        return base_url.rstrip("/")
    if provider in {"anthropic", "claude"}:
        return ANTHROPIC_DEFAULT_BASE_URL
    return ""


def configure_model_interactively(
    settings: Settings,
    *,
    ask_input: Callable[[str], str] = input,
    ask_secret: Callable[[str], str] = getpass.getpass,
    echo: Callable[[str], None] = print,
) -> Settings:
    """按顺序引导配置模型：供应商 → 请求地址 → API Key → 模型名称。"""

    echo("")
    echo("=== 模型配置（共 4 步，稍后都可用 ts-team-kb config 修改）===")

    echo("")
    echo("[1/4] 供应商名称")
    echo("      openai    使用 OpenAI 兼容接口：DeepSeek、通义、智谱以及多数自建网关都属于这一类")
    echo("      anthropic 使用 Claude 官方接口")
    echo("      也可以填写自定义名称（按 OpenAI 兼容协议调用）；直接回车默认 openai")
    provider = parse_provider(ask_input("供应商名称: "))

    echo("")
    echo("[2/4] 供应商请求地址")
    echo("      例如 https://api.deepseek.com/v1")
    echo("      自建网关形如 http://<网关地址>:<端口>/v1")
    echo(f"      选择 anthropic 时可留空，将使用官方地址 {ANTHROPIC_DEFAULT_BASE_URL}")
    base_url = resolve_base_url(provider, ask_input("请求地址: "))

    echo("")
    echo("[3/4] API Key")
    echo("      输入时不显示字符；直接回车可跳过，稍后用 ts-team-kb config set-key 补充")
    echo("      密钥只写入本机 secrets/model.key，不会进入仓库或共享知识库")
    api_key = ask_secret("API Key: ").strip()

    echo("")
    echo("[4/4] 模型名称")
    echo("      例如 deepseek-chat、deepseek-reasoner、claude-sonnet-4-5、gpt-4o-mini")
    model_name = ask_input("模型名称: ").strip()

    updated = replace(
        settings,
        model_provider=provider,
        model_base_url=base_url,
        model_name=model_name,
    )
    key_location = secret_path(settings.working_directory)
    if api_key:
        write_api_key(settings.working_directory, api_key)

    echo("")
    echo("已记录配置：")
    echo(f"  供应商   : {provider}")
    echo(f"  请求地址 : {base_url or '未设置'}")
    echo(f"  API Key  : {'已保存到 ' + str(key_location) if api_key else '未设置（可稍后用 config set-key 补充）'}")
    echo(f"  模型名称 : {model_name or '未设置'}")
    echo("")
    echo("检查配置：ts-team-kb config show")
    echo("试问一句：ts-team-kb ask \"<你的问题>\"")
    return updated
