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


@dataclass(frozen=True)
class Settings:
    personal_workspace: str
    shared_source_directory: Path
    working_directory: Path
    shared_knowledge_repository_directory: Path
    scan_interval_minutes: int = DEFAULT_SCAN_INTERVAL_MINUTES
    shared_knowledge_repository_url: str = DEFAULT_SHARED_KNOWLEDGE_REPOSITORY_URL
    mineru_python: Path | None = None
    sync_on_schedule: bool = True
    model_provider: str = ""
    model_name: str = ""
    model_base_url: str = ""
    model_max_tokens: int = 4096
    model_max_steps: int = 8
    excluded_source_paths: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "Settings":
        working_directory = Path(os.getenv("TS_KB_WORKING_DIRECTORY", ".local")).expanduser()
        config_path = Path(os.getenv("TS_KB_CONFIG", str(working_directory / "ts-kb.json"))).expanduser()
        if not config_path.is_file():
            raise FileNotFoundError(f"configuration file not found: {config_path}; run ts-team-kb init first")
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
            sync_on_schedule=str(data.get("sync_on_schedule", "true")).strip().lower() not in {"false", "0", "no"},
            model_provider=str(data.get("model_provider", "")).strip(),
            model_name=str(data.get("model_name", "")).strip(),
            model_base_url=str(data.get("model_base_url", "")).strip(),
            model_max_tokens=int(data.get("model_max_tokens", 4096) or 4096),
            model_max_steps=int(data.get("model_max_steps", 8) or 8),
            excluded_source_paths=tuple(
                str(item).strip() for item in (data.get("excluded_source_paths") or []) if str(item).strip()
            ),
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
            "sync_on_schedule": self.sync_on_schedule,
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "model_base_url": self.model_base_url,
            "model_max_tokens": self.model_max_tokens,
            "model_max_steps": self.model_max_steps,
            "excluded_source_paths": list(self.excluded_source_paths),
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
