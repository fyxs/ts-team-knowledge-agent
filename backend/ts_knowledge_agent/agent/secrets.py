from __future__ import annotations

from pathlib import Path


def secret_path(working_directory: Path) -> Path:
    """模型凭据只落在工作目录内，不进入任何 Git 仓库。"""

    return Path(working_directory) / "secrets" / "model.key"


def read_api_key(working_directory: Path) -> str:
    path = secret_path(working_directory)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def write_api_key(working_directory: Path, api_key: str) -> Path:
    value = (api_key or "").strip()
    if not value:
        raise ValueError("api key must not be empty")
    path = secret_path(working_directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value + "\n", encoding="utf-8")
    return path


def mask_secret(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return "not configured"
    if len(value) < 8:
        return "configured"
    return f"configured (****{value[-4:]})"
