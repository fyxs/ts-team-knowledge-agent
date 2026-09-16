"""转换运行锁：同一工作目录同时只允许一次转换运行。

锁文件带 pid、主机名与创建时间。接管条件（按优先级）：

1. 持有进程已不存在（同主机时按 pid 判定）—— 立即接管，并记入 `logs/lock-recoveries.jsonl`
2. 锁龄超过 `stale_seconds`（默认 2 小时，兜底）—— 接管并记录

两者都不满足时视为真实并发运行，抛错阻止本次运行。
"""

from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path


def _pid_alive(pid: int) -> bool:
    """判断同主机上某个 pid 是否仍然存在。"""

    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class RunLock:
    def __init__(self, working_directory: Path, stale_seconds: int = 7200) -> None:
        self.working_directory = Path(working_directory)
        self.path = self.working_directory / "runtime" / "run.lock"
        self.recovery_log = self.working_directory / "logs" / "lock-recoveries.jsonl"
        self.stale_seconds = stale_seconds

    def _read_holder(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _takeover_reason(self, holder: dict) -> str | None:
        pid = int(holder.get("pid") or 0)
        same_host = (holder.get("host") or socket.gethostname()) == socket.gethostname()
        if pid and same_host and not _pid_alive(pid):
            return f"holder pid {pid} is gone"
        age = time.time() - float(holder.get("created_at") or 0)
        if age > self.stale_seconds:
            return f"lock older than {self.stale_seconds}s"
        return None

    def _record_recovery(self, reason: str, holder: dict) -> None:
        self.recovery_log.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "reason": reason,
            "holder_pid": holder.get("pid"),
            "holder_created_at": holder.get("created_at"),
            "taken_by_pid": os.getpid(),
        }
        with self.recovery_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def __enter__(self) -> "RunLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"pid": os.getpid(), "host": socket.gethostname(), "created_at": time.time()},
            ensure_ascii=False,
        )
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            holder = self._read_holder()
            reason = self._takeover_reason(holder)
            if reason is None:
                raise RuntimeError(
                    f"another conversion run is already active: {self.path} (pid={holder.get('pid')})"
                )
            self.path.unlink(missing_ok=True)
            self._record_recovery(reason, holder)
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.path.unlink(missing_ok=True)
