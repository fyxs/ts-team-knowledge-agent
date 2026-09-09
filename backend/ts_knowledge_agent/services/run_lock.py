from __future__ import annotations
import json, os, time
from pathlib import Path

class RunLock:
    def __init__(self, working_directory: Path, stale_seconds: int = 7200) -> None:
        self.path = working_directory / "runtime" / "run.lock"
        self.stale_seconds = stale_seconds
    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"pid": os.getpid(), "created_at": time.time()})
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                age = time.time() - float(data.get("created_at", 0))
            except Exception:
                age = self.stale_seconds + 1
            if age <= self.stale_seconds:
                raise RuntimeError(f"another conversion run is already active: {self.path}")
            self.path.unlink(missing_ok=True)
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        return self
    def __exit__(self, exc_type, exc, tb):
        self.path.unlink(missing_ok=True)
