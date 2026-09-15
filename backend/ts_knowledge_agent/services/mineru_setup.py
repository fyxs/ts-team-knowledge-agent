"""制备 MinerU 转换环境。

免安装包（exe）内不含 MinerU（torch 约 1.1GB，且转换走独立解释器进程），
因此首次使用需要独立制备：建环境 → 安装 MinerU → 自检 → 把解释器路径写进配置。

引导解释器按顺序选择（谁先可用用谁）：
1. 显式传入的 --python
2. 随包附带的 uv（release zip 的 tools/uv.exe，体积小、能自动准备 Python）
3. 系统 Python（py -3 / python）
4. 环境变量 TS_KB_BOOTSTRAP_PYTHON
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_REQUIREMENT = "MinerU[pipeline]"
ENV_DIRECTORY_NAME = "mineru-env"


def default_mineru_env_path() -> Path:
    """MinerU 环境的默认落点（与工作目录无关，便于多机统一与复用）。"""

    local = os.getenv("LOCALAPPDATA", "").strip()
    base = Path(local) / "ts-team-kb" if local else Path.home() / ".ts-team-kb"
    return base / ENV_DIRECTORY_NAME


def environment_python(env_dir: Path) -> Path:
    """环境内解释器路径：兼容 Windows（Scripts）与 POSIX（bin）两种布局。"""

    windows = env_dir / "Scripts" / "python.exe"
    if windows.exists():
        return windows
    return env_dir / "bin" / "python"


def predicted_python(env_dir: Path) -> Path:
    """环境尚未创建时的解释器路径预测（按平台取布局，供 dry-run 展示）。"""

    if os.name == "nt":
        return env_dir / "Scripts" / "python.exe"
    return env_dir / "bin" / "python"


def bundled_uv_candidates() -> list[Path]:
    """随包附带的 uv（构建时放进 packaging 的 tools/ 目录）。"""

    here = Path(__file__).resolve()
    roots = [here.parents[2], here.parents[3], Path(sys.executable).parent]
    names = ("uv.exe", "uv")
    return [root / "tools" / name for root in roots for name in names]


def resolve_bootstrap() -> list[str] | None:
    """返回创建环境用的命令前缀，例如 ["uv"] 或 ["py", "-3"]。"""

    explicit = os.getenv("TS_KB_BOOTSTRAP_PYTHON", "").strip()
    if explicit:
        return [explicit]
    for candidate in bundled_uv_candidates():
        if candidate.is_file():
            return [str(candidate)]
    found = shutil.which("uv")
    if found:
        return [found]
    for name, probe in (("py", ["py", "-3", "-c", "import sys"]), ("python", ["python", "-c", "import sys"])):
        if shutil.which(name) and subprocess.run(probe, capture_output=True).returncode == 0:
            return ["py", "-3"] if name == "py" else ["python"]
    return None


@dataclass
class SetupResult:
    ok: bool
    python: Path | None = None
    steps: list[str] = field(default_factory=list)
    error: str | None = None
    version: str | None = None


def create_environment(env_dir: Path, bootstrap: list[str], *, dry_run: bool = False) -> list[str]:
    """创建虚拟环境，返回已执行步骤（命令以列表形式，便于审计与复现）。"""

    if not dry_run:
        env_dir.parent.mkdir(parents=True, exist_ok=True)
    if bootstrap and Path(bootstrap[0]).name.startswith("uv"):
        command = [*bootstrap, "venv", str(env_dir)]
    else:
        command = [*bootstrap, "-m", "venv", str(env_dir)]
    if dry_run:
        return [" ".join(command)]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    if result.returncode != 0:
        raise RuntimeError(f"创建环境失败（{result.returncode}）：{(result.stderr or result.stdout).strip()[:300]}")
    return [" ".join(command)]


def install_mineru(env_dir: Path, bootstrap: list[str], requirement: str, *, dry_run: bool = False) -> list[str]:
    """安装 MinerU；uv 与 pip 两种路径都支持。"""

    python = environment_python(env_dir) if env_dir.exists() else predicted_python(env_dir)
    if bootstrap and Path(bootstrap[0]).name.startswith("uv"):
        command = [*bootstrap, "pip", "install", "--python", str(python), requirement]
    else:
        command = [str(python), "-m", "pip", "install", requirement]
    if dry_run:
        return [" ".join(command)]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=7200)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout).strip().splitlines()[-6:]
        raise RuntimeError("安装 MinerU 失败：" + " | ".join(tail))
    return [" ".join(command)]


def verify_mineru(python: Path, *, timeout: int = 600) -> tuple[bool, str | None]:
    """自检：确认解释器能导入 mineru 与 torch，并回报版本。"""

    probe = "import mineru, torch; print(getattr(mineru, '__version__', 'unknown'), torch.__version__)"
    result = subprocess.run([str(python), "-c", probe], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=timeout)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()[-3:]
        return False, " | ".join(detail) or "导入 mineru/torch 失败"
    return True, (result.stdout or "").strip()


def setup_mineru(
    *,
    env_dir: Path | None = None,
    python: Path | None = None,
    requirement: str = DEFAULT_REQUIREMENT,
    dry_run: bool = False,
    verify: bool = True,
) -> SetupResult:
    """制备 MinerU：已给解释器则直接校验，否则建环境安装。"""

    steps: list[str] = []
    try:
        if python is not None:
            steps.append(f"使用已有解释器：{python}")
            if not python.exists():
                return SetupResult(False, python, steps, f"解释器不存在：{python}")
        else:
            target = env_dir or default_mineru_env_path()
            steps.append(f"目标环境：{target}")
            bootstrap = resolve_bootstrap()
            if bootstrap is None:
                return SetupResult(False, None, steps,
                                   "未找到可用的引导解释器：请提供 --python，或把 uv.exe 放到 tools/ 目录")
            steps += create_environment(target, bootstrap, dry_run=dry_run)
            steps += install_mineru(target, bootstrap, requirement, dry_run=dry_run)
            python = environment_python(target)
            if not dry_run and not python.exists():
                return SetupResult(False, None, steps, f"环境中找不到解释器：{python}")

        if dry_run:
            steps.append("dry-run：未安装、未自检")
            return SetupResult(True, python, steps)

        if verify:
            ok, detail = verify_mineru(python)
            steps.append(f"自检：{detail}")
            if not ok:
                return SetupResult(False, python, steps, detail)
            return SetupResult(True, python, steps, version=detail)

        return SetupResult(True, python, steps)
    except Exception as error:  # noqa: BLE001
        return SetupResult(False, None, steps, str(error))
