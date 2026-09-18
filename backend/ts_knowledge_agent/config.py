from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess

from ts_knowledge_agent.services.member_space import ensure_member_space

DEFAULT_SHARED_KNOWLEDGE_REPOSITORY_URL = "git@github.com:fyxs/ts-team-knowledge-base.git"
DEFAULT_SCAN_INTERVAL_MINUTES = 60
MIN_SCAN_INTERVAL_MINUTES = 5

DEFAULT_SOURCES_MAX_DISPLAY = 8
DEFAULT_SOURCES_RELEVANCE_RATIO = 0.5
DEFAULT_MINERU_TIMEOUT_SECONDS = 3600
"""MinerU 单次转换的超时上限（秒）；超大文档可调高，配合 mineru_chunk_pages 分片。"""
MIN_MINERU_TIMEOUT_SECONDS = 60
DEFAULT_MINERU_CHUNK_PAGES = 0
DEFAULT_MINERU_CHUNK_CONCURRENCY = 2
"""分片并发数：实测 MinerU 只用 6/20 核，并发跑不同页段可显著缩短大文档总时长；
实际并发会按可用内存自动下调（约 4.5GB/worker）。"""
DEFAULT_MAX_ROUND_SECONDS = 0
"""单轮时间预算（秒）：0 = 不限。>0 时一轮跑到预算就收尾，剩余文件留给下一轮，
避免一个超大文档把整轮占死、也避免长时间看不到进度。"""
DEFAULT_SLOW_SOURCE_SECONDS = 600
"""单篇历史耗时超过此值即视为「慢文档」，排队后置，避免堵住中小文档。"""
DEFAULT_LARGE_SOURCE_MB = 20
"""首次遇到、体积超过此值的重活文档同样后置（0 = 不按体积后置）。"""
DEFAULT_MINERU_RENDER_TIMEOUT_SECONDS = 300
"""MinerU 单批 PDF 页面渲染超时（秒），对应 MINERU_PDF_RENDER_TIMEOUT；0 = 交给 MinerU 默认。"""
DEFAULT_MINERU_RENDER_THREADS = 3
"""MinerU 渲染线程数，对应 MINERU_PDF_RENDER_THREADS。"""
"""0 = 不分片。大于 0 时按此页数把大 PDF 分片转换再合并，降低单次失败代价。"""


def config_candidates() -> list[Path]:
    """按优先级列出配置文件的候选位置。

    init 把配置写到 <工作目录>\\ts-kb.json，而历史版本的其他命令会去找 <工作目录>\\.local\\ts-kb.json，
    导致"init 明明成功、后续命令却说找不到配置"。这里统一成一份候选清单，谁先存在用谁。
    """
    candidates: list[Path] = []
    explicit = os.getenv("TS_KB_CONFIG", "").strip()
    if explicit:
        candidates.append(Path(explicit).expanduser())
    candidates.append(Path.cwd() / "ts-kb.json")
    candidates.append(Path.cwd() / ".local" / "ts-kb.json")
    env_workdir = os.getenv("TS_KB_WORKING_DIRECTORY", "").strip()
    if env_workdir:
        candidates.append(Path(env_workdir).expanduser() / "ts-kb.json")
    unique: list[Path] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def resolve_config_path() -> Path:
    """返回第一个真实存在的候选路径；都不存在时返回优先级最高的那个（用于报错信息）。"""
    candidates = config_candidates()
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]



def parse_interval_minutes(value: str | None) -> int:
    if value is None or not value.strip():
        return DEFAULT_SCAN_INTERVAL_MINUTES
    try:
        minutes = int(value)
    except ValueError as exc:
        raise ValueError("scan interval must be an integer number of minutes") from exc
    if minutes < MIN_SCAN_INTERVAL_MINUTES:
        raise ValueError(f"scan interval must be at least {MIN_SCAN_INTERVAL_MINUTES} minutes")
    return minutes


def parse_mineru_render_timeout(value: object) -> int:
    """渲染超时（秒）：0 表示交给 MinerU 默认；负数非法。"""

    raw = str(value).strip() if value is not None else ""
    seconds = DEFAULT_MINERU_RENDER_TIMEOUT_SECONDS if not raw else int(float(raw))
    if seconds < 0:
        raise ValueError("mineru_render_timeout_seconds must not be negative, got " + str(seconds))
    return seconds


def parse_mineru_render_threads(value: object) -> int:
    """渲染线程数：至少 1。"""

    raw = str(value).strip() if value is not None else ""
    threads = DEFAULT_MINERU_RENDER_THREADS if not raw else int(float(raw))
    if threads < 1:
        raise ValueError("mineru_render_threads must be at least 1, got " + str(threads))
    return threads


def parse_non_negative_int(value: object, default: int, name: str) -> int:
    """通用非负整数解析：空值回退默认，负值报错。"""

    raw = str(value).strip() if value is not None else ""
    number = default if not raw else int(float(raw))
    if number < 0:
        raise ValueError(name + " must not be negative, got " + str(number))
    return number


def parse_positive_int(value: object, default: int, name: str) -> int:
    """通用正整数解析：空值回退默认，非正数报错。"""

    raw = str(value).strip() if value is not None else ""
    number = default if not raw else int(float(raw))
    if number < 1:
        raise ValueError(name + " must be at least 1, got " + str(number))
    return number


def parse_sources_max_display(value: object) -> int:
    """展示来源条数上限；非法值直接报错，避免静默退回默认值。"""
    if value is None or value == "":
        return DEFAULT_SOURCES_MAX_DISPLAY
    try:
        count = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError("sources_max_display must be an integer") from exc
    if count < 1:
        raise ValueError("sources_max_display must be at least 1")
    return count


def parse_sources_relevance_ratio(value: object) -> float:
    """证据强度阈值（相对最高强度）；低于该比例的来源不展示。"""
    if value is None or value == "":
        return DEFAULT_SOURCES_RELEVANCE_RATIO
    try:
        ratio = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError("sources_relevance_ratio must be a number") from exc
    if not 0.0 <= ratio <= 1.0:
        raise ValueError("sources_relevance_ratio must be between 0 and 1")
    return ratio


@dataclass(frozen=True)
class Settings:
    personal_workspace: str
    shared_source_directory: Path
    working_directory: Path
    shared_knowledge_repository_directory: Path
    scan_interval_minutes: int = DEFAULT_SCAN_INTERVAL_MINUTES
    shared_knowledge_repository_url: str = DEFAULT_SHARED_KNOWLEDGE_REPOSITORY_URL
    mineru_python: Path | None = None
    mineru_timeout_seconds: int = DEFAULT_MINERU_TIMEOUT_SECONDS
    mineru_chunk_pages: int = DEFAULT_MINERU_CHUNK_PAGES
    mineru_render_timeout_seconds: int = DEFAULT_MINERU_RENDER_TIMEOUT_SECONDS
    mineru_render_threads: int = DEFAULT_MINERU_RENDER_THREADS
    slow_source_threshold_seconds: int = DEFAULT_SLOW_SOURCE_SECONDS
    large_source_mb: int = DEFAULT_LARGE_SOURCE_MB
    mineru_chunk_concurrency: int = DEFAULT_MINERU_CHUNK_CONCURRENCY
    max_round_seconds: int = DEFAULT_MAX_ROUND_SECONDS
    sync_on_schedule: bool = True
    model_provider: str = ""
    model_name: str = ""
    model_base_url: str = ""
    model_max_tokens: int = 4096
    model_max_steps: int = 8
    excluded_source_paths: tuple[str, ...] = ()
    sources_max_display: int = DEFAULT_SOURCES_MAX_DISPLAY
    sources_relevance_ratio: float = DEFAULT_SOURCES_RELEVANCE_RATIO

    @classmethod
    def from_env(cls) -> "Settings":
        config_path = resolve_config_path()
        if not config_path.is_file():
            tried = "\n".join(f"  - {item}" for item in config_candidates())
            raise FileNotFoundError(
                "configuration file not found; looked for:\n"
                f"{tried}\n"
                "how to fix:\n"
                "  - run `ts-team-kb init --working-directory <dir> ...` first, "
                "then run later commands from that directory\n"
                "  - or set the environment variable TS_KB_CONFIG=<path to ts-kb.json>"
            )
        return cls.from_file(config_path)

    @classmethod
    def from_file(cls, path: Path) -> "Settings":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        required = ["personal_workspace", "shared_source_directory", "working_directory", "shared_knowledge_repository_directory"]
        missing = [key for key in required if not str(data.get(key, "")).strip()]
        if missing:
            raise ValueError("missing required configuration: " + ", ".join(missing))
        working_directory = Path(data["working_directory"]).expanduser()
        return cls(
            personal_workspace=str(data["personal_workspace"]).strip(),
            shared_source_directory=Path(data["shared_source_directory"]).expanduser(),
            working_directory=working_directory,
            shared_knowledge_repository_directory=Path(data["shared_knowledge_repository_directory"]).expanduser(),
            scan_interval_minutes=parse_interval_minutes(str(data.get("scan_interval_minutes", 60))),
            shared_knowledge_repository_url=str(data.get("shared_knowledge_repository_url", DEFAULT_SHARED_KNOWLEDGE_REPOSITORY_URL)).strip() or DEFAULT_SHARED_KNOWLEDGE_REPOSITORY_URL,
            mineru_python=Path(data["mineru_python"]).expanduser() if str(data.get("mineru_python", "")).strip() else None,
            mineru_timeout_seconds=parse_mineru_timeout_seconds(data.get("mineru_timeout_seconds")),
            mineru_chunk_pages=parse_mineru_chunk_pages(data.get("mineru_chunk_pages")),
            mineru_render_timeout_seconds=parse_mineru_render_timeout(data.get("mineru_render_timeout_seconds")),
            mineru_render_threads=parse_mineru_render_threads(data.get("mineru_render_threads")),
            slow_source_threshold_seconds=parse_non_negative_int(
                data.get("slow_source_threshold_seconds"), DEFAULT_SLOW_SOURCE_SECONDS,
                "slow_source_threshold_seconds"),
            large_source_mb=parse_non_negative_int(
                data.get("large_source_mb"), DEFAULT_LARGE_SOURCE_MB, "large_source_mb"),
            mineru_chunk_concurrency=parse_positive_int(
                data.get("mineru_chunk_concurrency"), DEFAULT_MINERU_CHUNK_CONCURRENCY,
                "mineru_chunk_concurrency"),
            max_round_seconds=parse_non_negative_int(
                data.get("max_round_seconds"), DEFAULT_MAX_ROUND_SECONDS, "max_round_seconds"),
            sync_on_schedule=str(data.get("sync_on_schedule", "true")).strip().lower() not in {"false", "0", "no"},
            model_provider=str(data.get("model_provider", "")).strip(),
            model_name=str(data.get("model_name", "")).strip(),
            model_base_url=str(data.get("model_base_url", "")).strip(),
            model_max_tokens=int(data.get("model_max_tokens", 4096) or 4096),
            model_max_steps=int(data.get("model_max_steps", 8) or 8),
            excluded_source_paths=tuple(
                str(item).strip() for item in (data.get("excluded_source_paths") or []) if str(item).strip()
            ),
            sources_max_display=parse_sources_max_display(data.get("sources_max_display")),
            sources_relevance_ratio=parse_sources_relevance_ratio(data.get("sources_relevance_ratio")),
        )

    def write_file(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "personal_workspace": self.personal_workspace,
            "shared_source_directory": str(self.shared_source_directory),
            "working_directory": str(self.working_directory),
            "shared_knowledge_repository_directory": str(self.shared_knowledge_repository_directory),
            "scan_interval_minutes": self.scan_interval_minutes,
            "shared_knowledge_repository_url": self.shared_knowledge_repository_url,
            "mineru_python": str(self.mineru_python) if self.mineru_python else "",
            "mineru_timeout_seconds": self.mineru_timeout_seconds,
            "mineru_chunk_pages": self.mineru_chunk_pages,
            "mineru_render_timeout_seconds": self.mineru_render_timeout_seconds,
            "mineru_render_threads": self.mineru_render_threads,
            "slow_source_threshold_seconds": self.slow_source_threshold_seconds,
            "large_source_mb": self.large_source_mb,
            "mineru_chunk_concurrency": self.mineru_chunk_concurrency,
            "max_round_seconds": self.max_round_seconds,
            "sync_on_schedule": self.sync_on_schedule,
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "model_base_url": self.model_base_url,
            "model_max_tokens": self.model_max_tokens,
            "model_max_steps": self.model_max_steps,
            "excluded_source_paths": list(self.excluded_source_paths),
            "sources_max_display": self.sources_max_display,
            "sources_relevance_ratio": self.sources_relevance_ratio,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


WORKSPACE_README_TEXT = """# 工作目录

本目录是本机运行数据与共享知识仓的落点，**不是 Git 仓库**：
除 `knowledge-base/` 之外的所有内容都不进入版本控制。

| 条目 | 内容 | 处置 |
| --- | --- | --- |
| `ts-kb.json` | 本机运行配置（源目录、工作区、模型、扫描间隔） | 不要删除；改配置用 `ts-team-kb config` |
| `data/` | 本机 SQLite（会话历史等） | 删除会丢失会话与状态 |
| `logs/` | 运行日志、巡检与评测报告、使用埋点明细 | 按留存规则清理（报告保留最近 30 份，埋点长期保留） |
| `runtime/` | 运行期锁与临时状态（如 `run.lock`，正常运行结束后会消失） | 可删，下次运行重建 |
| `feedback/` | 本机反馈闭环记录（会导出到共享仓 `registries/`） | 不要删，属质量追溯 |
| `secrets/` | 本机密钥（`model.key`），不进任何 Git 仓库 | 不要删；丢失需重配模型 |
| `knowledge-base/` | 共享知识仓的本地克隆（唯一有版本控制的目录） | 不要手改，由应用同步 |
| `run-*.cmd` / `run-*.vbs` | 启动器（由 `scripts/install-windows-tasks.ps1` 生成） | 由安装脚本重建，不要手改 |

## 使用约定

- 本工作目录由所有并发工作区（含 worktree）共享，不要在 worktree 内另建一套。
- 动手前先确认服务与计划任务状态（8088 是否在监听、任务是否在跑），避免锁冲突。
- 结构由 `ts-team-kb init` 初始化；本文件同样由 init 生成，可人工补充，但结构部分请保持与本表一致。
"""


def parse_mineru_timeout_seconds(value: object) -> int:
    """MinerU 超时（秒）：默认 DEFAULT_MINERU_TIMEOUT_SECONDS，下限 MIN_MINERU_TIMEOUT_SECONDS。"""

    raw = str(value).strip() if value is not None else ""
    seconds = DEFAULT_MINERU_TIMEOUT_SECONDS if not raw else int(float(raw))
    if seconds < MIN_MINERU_TIMEOUT_SECONDS:
        raise ValueError("mineru_timeout_seconds must be at least " + str(MIN_MINERU_TIMEOUT_SECONDS) + ", got " + str(seconds))
    return seconds


def parse_mineru_chunk_pages(value: object) -> int:
    """大 PDF 分片页数：0（默认）不分片；其它取值必须为正整数。"""

    raw = str(value).strip() if value is not None else ""
    pages = DEFAULT_MINERU_CHUNK_PAGES if not raw else int(float(raw))
    if pages < 0:
        raise ValueError("mineru_chunk_pages must not be negative, got " + str(pages))
    return pages


def clone_knowledge_repo(settings: Settings) -> None:
    path = settings.shared_knowledge_repository_directory
    path.parent.mkdir(parents=True, exist_ok=True)
    if (path / ".git").is_dir():
        return
    if path.exists() and any(path.iterdir()):
        raise RuntimeError(f"shared knowledge repository directory is not empty: {path}")
    result = subprocess.run(
        ["git", "clone", settings.shared_knowledge_repository_url, str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())


def initialize_working_directory(settings: Settings) -> None:
    if not settings.shared_source_directory.is_dir():
        raise RuntimeError(
            "shared source directory does not exist or is not a directory: "
            + str(settings.shared_source_directory)
        )
    settings.working_directory.mkdir(parents=True, exist_ok=True)
    for name in ("data", "logs", "runtime"):
        (settings.working_directory / name).mkdir(parents=True, exist_ok=True)
    _write_workspace_readme(settings.working_directory)
    clone_knowledge_repo(settings)
    config_path = settings.working_directory / "ts-kb.json"
    settings.write_file(config_path)
    if not config_path.is_file():
        raise RuntimeError("failed to write configuration file")
    if not (settings.shared_knowledge_repository_directory / ".git").is_dir():
        raise RuntimeError("shared knowledge repository was not initialized")
    ensure_member_space(settings.shared_knowledge_repository_directory, settings.personal_workspace)


def _write_workspace_readme(working_directory: Path) -> None:
    """首次初始化时写入工作目录说明；已存在则不覆盖（允许人工补充）。"""

    readme = working_directory / "README.md"
    if readme.is_file():
        return
    readme.write_text(WORKSPACE_README_TEXT, encoding="utf-8")
