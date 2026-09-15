"""本地 Web 服务的启动、停止、重启与状态查询。

Windows 上通过 PowerShell 查监听端口的进程；启动时以分离进程方式拉起
`ts-team-kb serve`，退出父进程后服务仍然存活。
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

DEFAULT_WEB_PORT = 8088
HEALTH_TIMEOUT_SECONDS = 6


@dataclass(frozen=True)
class ServiceStatus:
    port: int
    listening: bool
    pid: int | None
    health: str | None
    detail: str | None = None

    def to_dict(self) -> dict:
        return asdict_status(self)


def asdict_status(status: ServiceStatus) -> dict:
    return {
        "port": status.port,
        "listening": status.listening,
        "pid": status.pid,
        "health": status.health,
        "detail": status.detail,
    }


def listening_pid(port: int = DEFAULT_WEB_PORT) -> int | None:
    """返回监听指定端口的进程号；没有监听时返回 None。"""

    if platform.system() == "Windows":
        script = (
            f"$c = Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | "
            "Select-Object -First 1 -ExpandProperty OwningProcess; if ($c) { $c }"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )
        value = (result.stdout or "").strip()
        return int(value) if value.isdigit() else None

    for command in (["lsof", "-t", f"-i:{port}", "-s", "TCP:LISTEN"], ["fuser", f"{port}/tcp"]):
        try:
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=False)
        except FileNotFoundError:
            continue
        tokens = (result.stdout or "").split()
        if tokens and tokens[0].isdigit():
            return int(tokens[0])
    return None


def health_of(port: int = DEFAULT_WEB_PORT) -> str | None:
    """探测 /health；不可达时返回 None。"""

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=HEALTH_TIMEOUT_SECONDS) as response:
            return "ok" if response.status == 200 else f"http_{response.status}"
    except (urllib.error.URLError, OSError, ValueError):
        return None


def service_status(port: int = DEFAULT_WEB_PORT) -> ServiceStatus:
    pid = listening_pid(port)
    if pid is None:
        return ServiceStatus(port=port, listening=False, pid=None, health=None, detail="not_running")
    return ServiceStatus(port=port, listening=True, pid=pid, health=health_of(port), detail="listening")


def _cli_executable() -> str:
    candidate = Path(sys.executable).with_name("ts-team-kb.exe" if platform.system() == "Windows" else "ts-team-kb")
    return str(candidate) if candidate.is_file() else sys.executable


def launcher_path(settings, port: int = DEFAULT_WEB_PORT) -> Path:
    """工作目录下的服务启动器路径。"""

    return Path(settings.working_directory) / f"run-api-{port}.cmd"


def write_launcher(settings, config_path: Path, port: int = DEFAULT_WEB_PORT) -> Path:
    """写入服务启动器（ANSI 编码，兼容中文路径）。"""

    project_root = Path(__file__).resolve().parents[3]
    path = launcher_path(settings, port)
    path.parent.mkdir(parents=True, exist_ok=True)
    log_path = Path(settings.working_directory) / "logs" / "api.log"
    lines = [
        "@echo off",
        f'set "PYTHONPATH={project_root / "backend"}"',
        f'set "TS_KB_CONFIG={config_path}"',
        f'cd /d "{settings.working_directory}"',
        f'"{_cli_executable()}" serve --host 0.0.0.0 --port {port} >> "{log_path}" 2>&1',
    ]
    path.write_text("\r\n".join(lines) + "\r\n", encoding="mbcs" if platform.system() == "Windows" else "utf-8")
    return path


def start_service(settings, config_path: Path | None = None, port: int = DEFAULT_WEB_PORT) -> tuple[bool, str]:
    """启动服务；已在运行时直接返回成功。

    Windows 上通过 WMI 创建进程，避免 SSH/父进程退出时被一并回收。
    """

    existing = listening_pid(port)
    if existing is not None:
        return True, f"already_running pid={existing}"

    Path(settings.working_directory, "logs").mkdir(parents=True, exist_ok=True)
    if config_path is None:
        config_path = Path(settings.working_directory) / "ts-kb.json"
    launcher = write_launcher(settings, Path(config_path), port)

    if platform.system() == "Windows":
        wmi_command = f'cmd.exe /c ""{launcher}""'
        script = "([wmiclass]'Win32_Process').Create('" + wmi_command.replace("'", "''") + "') | Out-Null"
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )
        if result.returncode != 0:
            return False, f"start_failed: {(result.stderr or '').strip()[:200]}"
    else:
        with (Path(settings.working_directory) / "logs" / "api.log").open("a", encoding="utf-8") as handle:
            subprocess.Popen([str(launcher)], stdout=handle, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, start_new_session=True)

    for _ in range(20):
        time.sleep(1)
        pid = listening_pid(port)
        if pid is not None:
            return True, f"started pid={pid}"
    return False, "start_timeout (check logs/api.log)"


def stop_service(port: int = DEFAULT_WEB_PORT) -> tuple[bool, str]:
    """停止占用端口的服务进程。"""

    pid = listening_pid(port)
    if pid is None:
        return True, "not_running"

    if platform.system() == "Windows":
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", f"Stop-Process -Id {pid} -Force"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )
        if result.returncode != 0:
            return False, f"stop_failed {pid}: {(result.stderr or '').strip()[:200]}"
    else:
        result = subprocess.run(["kill", "-TERM", str(pid)], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return False, f"stop_failed {pid}"

    for _ in range(15):
        time.sleep(1)
        if listening_pid(port) is None:
            return True, f"stopped pid={pid}"
    return False, f"stop_timeout pid={pid}"


def restart_service(settings, config_path: Path | None = None, port: int = DEFAULT_WEB_PORT) -> tuple[bool, str]:
    stopped_ok, stopped_detail = stop_service(port)
    if not stopped_ok:
        return False, stopped_detail
    started_ok, started_detail = start_service(settings, config_path=config_path, port=port)
    return started_ok, f"{stopped_detail}; {started_detail}"
