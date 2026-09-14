from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess

DEFAULT_SHARED_KNOWLEDGE_REPOSITORY_URL = "git@github.com:fyxs/ts-team-knowledge-base.git"
DEFAULT_SCAN_INTERVAL_MINUTES = 60


def parse_interval_minutes(value: str | None) -> int:
    if value is None or not value.strip():
        return DEFAULT_SCAN_INTERVAL_MINUTES
    try:
        minutes = int(value)
    except ValueError as exc:
        raise ValueError("scan interval must be an integer number of minutes") from exc
    if minutes < 1:
        raise ValueError("scan interval must be at least 1 minute")
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

    @classmethod
    def from_env(cls) -> "Settings":
        working_directory = Path(os.getenv("TS_KB_WORKING_DIRECTORY", ".local")).expanduser()
        config_path = Path(os.getenv("TS_KB_CONFIG", str(working_directory / "ts-kb.json"))).expanduser()
        if not config_path.is_file():
            raise FileNotFoundError(f"configuration file not found: {config_path}; run ts-kb init first")
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
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
    clone_knowledge_repo(settings)
    config_path = settings.working_directory / "ts-kb.json"
    settings.write_file(config_path)
    if not config_path.is_file():
        raise RuntimeError("failed to write configuration file")
    if not (settings.shared_knowledge_repository_directory / ".git").is_dir():
        raise RuntimeError("shared knowledge repository was not initialized")
