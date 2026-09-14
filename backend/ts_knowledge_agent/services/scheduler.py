from __future__ import annotations
import json,time,traceback
from collections.abc import Callable
from datetime import datetime,timezone
from pathlib import Path
from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.services.pipeline import RunSummary, run_once

def _write_run_report(settings: Settings, summary: RunSummary, started: str, ended: str, duration: float, error: str|None=None)->Path:
    path=settings.working_directory/"logs"/"runs.jsonl"; path.parent.mkdir(parents=True,exist_ok=True)
    record={"started_at":started,"finished_at":ended,"duration_seconds":round(duration,3),"scanned":summary.scanned,"queued":summary.queued,"batches":summary.batches,"converted":summary.converted,"skipped":summary.skipped,"failed":summary.failed,"missing":summary.missing,"indexed":summary.indexed,"sync_status":summary.sync_status,"reason_counts":summary.reason_counts,"error":error}
    with path.open("a",encoding="utf-8") as f: f.write(json.dumps(record,ensure_ascii=False)+"\n")
    return path

def run_once_with_report(settings: Settings, *, sync: bool = False, batch_size: int = 25) -> RunSummary:
    started_dt = datetime.now(timezone.utc)
    started = started_dt.isoformat()
    started_perf = time.perf_counter()
    try:
        summary = run_once(settings, sync=sync, batch_size=batch_size)
        error = None
    except Exception as exc:
        ended = datetime.now(timezone.utc).isoformat()
        fallback = RunSummary(0, failed=1, reason_counts={"run_once_error": 1})
        _write_run_report(settings, fallback, started, ended, time.perf_counter() - started_perf, f"{type(exc).__name__}: {exc}")
        raise
    ended = datetime.now(timezone.utc).isoformat()
    _write_run_report(settings, summary, started, ended, time.perf_counter() - started_perf, error)
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
