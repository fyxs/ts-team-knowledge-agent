from __future__ import annotations
import json,time,traceback
from collections.abc import Callable
from datetime import datetime,timezone
from pathlib import Path
from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.services.pipeline import RunSummary, run_once

def _run_result(error: str | None) -> str:
    """运行结果标签：ok / locked（被其它运行占用）/ failed。"""

    if not error:
        return "ok"
    return "locked" if "already active" in error else "failed"


def _write_run_report(settings: Settings, summary: RunSummary, started: str, ended: str, duration: float, error: str|None=None, lane: str = "all")->Path:
    path=settings.working_directory/"logs"/"runs.jsonl"; path.parent.mkdir(parents=True,exist_ok=True)
    record={"started_at":started,"lane":lane,"finished_at":ended,"duration_seconds":round(duration,3),"scanned":summary.scanned,"queued":summary.queued,"batches":summary.batches,"converted":summary.converted,"warned":summary.warned,"skipped":summary.skipped,"failed":summary.failed,"missing":summary.missing,"indexed":summary.indexed,"sync_status":summary.sync_status,"reason_counts":summary.reason_counts,"result":_run_result(error),"error":error}
    with path.open("a",encoding="utf-8") as f: f.write(json.dumps(record,ensure_ascii=False)+"\n")
    return path

def run_once_with_report(settings: Settings, *, sync: bool = False, batch_size: int = 25,
                          lane: str = "all") -> RunSummary:
    started_dt = datetime.now(timezone.utc)
    started = started_dt.isoformat()
    started_perf = time.perf_counter()
    try:
        summary = run_once(settings, sync=sync, batch_size=batch_size, lane=lane)
        error = None
    except Exception as exc:
        ended = datetime.now(timezone.utc).isoformat()
        fallback = RunSummary(0, failed=1, reason_counts={"run_once_error": 1})
        _write_run_report(settings, fallback, started, ended, time.perf_counter() - started_perf, f"{type(exc).__name__}: {exc}", lane=lane)
        raise
    ended = datetime.now(timezone.utc).isoformat()
    _write_run_report(settings, summary, started, ended, time.perf_counter() - started_perf, error, lane=lane)
    return summary


def _default_run(settings: Settings) -> RunSummary:
    return run_once(settings, sync=settings.sync_on_schedule)


def run_scheduler(settings: Settings, run: Callable[[Settings],RunSummary]|None=None, sleep: Callable[[float],None]=time.sleep, max_runs: int|None=None)->int:
    run = run or _default_run
    completed=0; exit_code=0
    while max_runs is None or completed<max_runs:
        started_dt=datetime.now(timezone.utc); started=started_dt.isoformat(); t=time.perf_counter()
        try: summary=run(settings); error=None
        except Exception as exc:
            summary=RunSummary(0,failed=1,reason_counts={"scheduler_error":1}); error=f"{type(exc).__name__}: {exc}"; exit_code=1
        ended=datetime.now(timezone.utc).isoformat(); _write_run_report(settings,summary,started,ended,time.perf_counter()-t,error)
        completed+=1
        if summary.failed or error: exit_code=1
        if max_runs is None or completed<max_runs: sleep(settings.scan_interval_minutes*60)
    return exit_code


LANE_REPORT_MATCH = {
    "all": frozenset({"all"}),
    "light": frozenset({"all", "light"}),
    "heavy": frozenset({"all", "heavy"}),
}
"""车道到期判断：哪几种轮次算作"该车道刚跑过"。

全车道轮次（all）两类活都做，因此对 light/heavy 都算数；
反之轻量轮次不算重活跑过，全车道轮次也只由全车道计时 ——
否则每 5 分钟的轻量轮次会把主任务与重活永远判成"刚跑过"。
历史记录没有 lane 字段时按 all 处理。
"""


def last_run_started_at(working_directory: Path, lane: str = "all") -> datetime | None:
    """读取运行报告里最近一轮的开始时间；按车道过滤（默认任意车道）。"""
    report = Path(working_directory) / "logs" / "runs.jsonl"
    if not report.is_file():
        return None
    wanted = LANE_REPORT_MATCH.get(lane, LANE_REPORT_MATCH["all"])
    for line in reversed(report.read_text(encoding="utf-8", errors="replace").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (payload.get("lane") or "all") not in wanted:
            continue
        raw = payload.get("started_at")
        if not raw:
            continue
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            continue
    return None


def is_scan_due(settings: Settings, now: datetime | None = None, lane: str = "all") -> bool:
    """按配置的扫描间隔判断本轮是否该执行；无历史记录时视为到期。

    lane 决定看哪一类轮次的历史：轻量车道与重活车道各自独立计时，
    否则轻量的高频轮次会把重活永远判成"刚跑过"。
    """
    last = last_run_started_at(settings.working_directory, lane=lane)
    if last is None:
        return True
    current = now or datetime.now(timezone.utc)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    elapsed_minutes = (current - last).total_seconds() / 60.0
    return elapsed_minutes >= float(settings.scan_interval_minutes)
