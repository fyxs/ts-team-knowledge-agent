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
# MinerU 3.4.5 的 OCR 链路 import six，但未声明该依赖；缺了会在真实转换时崩。
# 这类"上游打包缺口"统一在这里补齐，并保持可扩展（--extra 可再加）。
EXTRA_REQUIREMENTS = ("six",)
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


def _usable(command: list[str]) -> bool:
    """命令能否真正跑起来（避免选到 WindowsApps 的占位 python）。"""

    try:
        return subprocess.run([*command, "-c", "import sys; print(sys.version_info[0])"],
                              capture_output=True, text=True, timeout=120).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def resolve_bootstrap() -> list[str] | None:
    """返回创建环境用的命令前缀。

    顺序：显式指定 → 系统解释器 → 随包 uv → PATH 上的 uv。
    优先系统解释器：不需要联网下载解释器，也不受 uv 托管目录是否可用影响
    （实测存在 uv 托管目录被安全软件改成不可访问重解析点的情况）。
    """

    explicit = os.getenv("TS_KB_BOOTSTRAP_PYTHON", "").strip()
    if explicit:
        return [explicit]
    if os.name == "nt":
        launcher = shutil.which("py")
        if launcher and _usable([launcher, "-3"]):
            return [launcher, "-3"]
    system_python = shutil.which("python")
    if system_python and _usable([system_python]):
        return [system_python]
    for candidate in bundled_uv_candidates():
        if candidate.is_file() and _usable([str(candidate), "--version"]):
            return [str(candidate)]
    found = shutil.which("uv")
    if found and _usable([found, "--version"]):
        return [found]
    return None


def uv_environment(env_dir: Path) -> dict[str, str]:
    """uv 调用环境：把它托管的 Python 放到我们可控的目录，避开不可访问的默认落点。"""

    environment = dict(os.environ)
    environment.setdefault("UV_PYTHON_INSTALL_DIR", str(env_dir.parent / "python"))
    return environment


@dataclass
class SetupResult:
    ok: bool
    python: Path | None = None
    steps: list[str] = field(default_factory=list)
    error: str | None = None
    version: str | None = None


def create_environment(env_dir: Path, bootstrap: list[str], *, dry_run: bool = False) -> list[str]:
    """创建虚拟环境，返回已执行步骤（命令以列表形式，便于审计与复现）。"""

    is_uv = bool(bootstrap) and Path(bootstrap[0]).name.lower().startswith("uv")
    if is_uv:
        commands = [[*bootstrap, "venv", "--python", "3.13", str(env_dir)], [*bootstrap, "venv", str(env_dir)]]
    else:
        commands = [[*bootstrap, "-m", "venv", str(env_dir)]]
    if dry_run:
        return [" ".join(commands[0])]
    env_dir.parent.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=1800, env=uv_environment(env_dir) if is_uv else None)
        if result.returncode == 0:
            return [" ".join(command)]
        detail = (result.stderr or result.stdout).strip().splitlines()[:3]
        errors.append(f"{' '.join(command)} → {' | '.join(detail)}")
    raise RuntimeError("创建环境失败：" + " ;; ".join(errors) +
                       "（若提示重解析点/不可访问，说明解释器目录被安全软件接管，请用 --python 指向可用解释器）")


def install_mineru(env_dir: Path, bootstrap: list[str], requirement: str, *, extras: tuple[str, ...] = EXTRA_REQUIREMENTS,
                   dry_run: bool = False) -> list[str]:
    """安装 MinerU；uv 与 pip 两种路径都支持。"""

    python = environment_python(env_dir) if env_dir.exists() else predicted_python(env_dir)
    if bootstrap and Path(bootstrap[0]).name.startswith("uv"):
        command = [*bootstrap, "pip", "install", "--python", str(python), requirement, *extras]
    else:
        command = [str(python), "-m", "pip", "install", requirement, *extras]
    if dry_run:
        return [" ".join(command)]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=7200, env=uv_environment(env_dir) if Path(bootstrap[0]).name.lower().startswith("uv") else None)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout).strip().splitlines()[-6:]
        raise RuntimeError("安装 MinerU 失败：" + " | ".join(tail))
    return [" ".join(command)]


def verify_mineru(python: Path, *, timeout: int = 900) -> tuple[bool, str | None]:
    """自检：基础导入 + 真实转换要走的 pipeline 链路。

    只 import mineru/torch 是不够的——MinerU 的 OCR 链路（pipeline_analyze）里
    有未声明的可选依赖（如 six），只有把这层也导入进来才能提前暴露，
    否则会在成员机第一次真实转换时才崩。
    """

    probe = (
        "import mineru, torch\n"
        "import mineru.backend.pipeline.pipeline_analyze as pa\n"
        "print(getattr(mineru, '__version__', 'unknown'), torch.__version__, 'pipeline-ok')\n"
    )
    result = subprocess.run([str(python), "-c", probe], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=timeout)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()[-3:]
        return False, " | ".join(detail) or "自检失败"
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
