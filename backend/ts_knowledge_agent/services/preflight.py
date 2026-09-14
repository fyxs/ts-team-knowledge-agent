from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ts_knowledge_agent.agent.secrets import read_api_key
from ts_knowledge_agent.config import Settings

LEVEL_OK = "ok"
LEVEL_WARN = "warn"
LEVEL_ERROR = "error"

_MARKS = {LEVEL_OK: "[ok]   ", LEVEL_WARN: "[warn] ", LEVEL_ERROR: "[error]"}


@dataclass(frozen=True)
class CheckResult:
    name: str
    level: str
    detail: str


def run_preflight(settings: Settings, web_dist: Path | None = None) -> list[CheckResult]:
    """启动前检查：把「能不能跑起来、哪些功能不可用」一次性讲清楚。"""
    results: list[CheckResult] = []

    source = settings.shared_source_directory
    if source.is_dir():
        results.append(CheckResult("源目录", LEVEL_OK, str(source)))
    else:
        results.append(CheckResult("源目录", LEVEL_ERROR, f"不存在或不是目录：{source}"))

    repository = settings.shared_knowledge_repository_directory
    if (repository / ".git").is_dir():
        results.append(CheckResult("共享知识仓", LEVEL_OK, f"{repository}（已连接 Git）"))
    elif repository.exists():
        results.append(CheckResult("共享知识仓", LEVEL_ERROR, f"目录存在但不是 Git 仓库：{repository}"))
    else:
        results.append(CheckResult("共享知识仓", LEVEL_ERROR, f"目录不存在：{repository}"))

    if settings.shared_knowledge_repository_url.strip():
        results.append(CheckResult("知识仓远程", LEVEL_OK, settings.shared_knowledge_repository_url))
    else:
        results.append(CheckResult("知识仓远程", LEVEL_WARN, "未配置远程地址，无法拉取或推送"))

    mineru = settings.mineru_python
    if mineru is None:
        results.append(CheckResult("MinerU 解释器", LEVEL_WARN, "未配置，PDF / Office 转换不可用（Markdown 复制不受影响）"))
    elif Path(mineru).is_file():
        results.append(CheckResult("MinerU 解释器", LEVEL_OK, str(mineru)))
    else:
        results.append(CheckResult("MinerU 解释器", LEVEL_ERROR, f"配置的路径不存在：{mineru}"))

    missing = [
        label
        for label, value in (
            ("provider", settings.model_provider),
            ("model", settings.model_name),
            ("base_url", settings.model_base_url),
        )
        if not str(value).strip()
    ]
    has_key = bool(read_api_key(settings.working_directory))
    if missing or not has_key:
        detail = "缺少：" + "、".join(missing + ([] if has_key else ["api_key"]))
        results.append(CheckResult("模型配置", LEVEL_WARN, f"{detail}；问答功能不可用，可用 ts-team-kb config 补齐"))
    else:
        results.append(CheckResult("模型配置", LEVEL_OK, f"{settings.model_provider} / {settings.model_name}"))

    if web_dist is None:
        results.append(CheckResult("前端产物", LEVEL_WARN, "未检测构建产物；Web 界面不可用，仅 API 可用"))
    elif (web_dist / "index.html").is_file():
        results.append(CheckResult("前端产物", LEVEL_OK, str(web_dist)))
    else:
        results.append(CheckResult("前端产物", LEVEL_WARN, f"缺少 {web_dist / 'index.html'}；请先执行前端构建"))
    return results


def has_blocking_errors(results: list[CheckResult]) -> bool:
    return any(result.level == LEVEL_ERROR for result in results)


def format_report(results: list[CheckResult]) -> str:
    lines = ["启动前检查："]
    for result in results:
        lines.append(f"  {_MARKS.get(result.level, '[????]')} {result.name}：{result.detail}")
    return "\n".join(lines)
