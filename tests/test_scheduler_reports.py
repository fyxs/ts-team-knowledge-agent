import json
from pathlib import Path
from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.services.pipeline import RunSummary
from ts_knowledge_agent.services.scheduler import run_once_with_report, run_scheduler

def test_scheduler_writes_jsonl_on_failed_run(tmp_path):
    settings=Settings("x",Path("."),tmp_path,tmp_path,1)
    calls=[]
    result=run_scheduler(settings,lambda _: (calls.append(1) or RunSummary(1,failed=1,reason_counts={"quality_failed":1})),lambda _: None,max_runs=2)
    assert result == 1
    assert len(calls)==2
    lines=(tmp_path/"logs"/"runs.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines)==2
    assert json.loads(lines[0])["reason_counts"]["quality_failed"]==1


def test_run_once_with_report_writes_jsonl(tmp_path, monkeypatch):
    settings = Settings("x", Path("."), tmp_path, tmp_path, 1)
    expected = RunSummary(3, queued=1, converted=1, skipped=1, indexed=1)
    monkeypatch.setattr("ts_knowledge_agent.services.scheduler.run_once", lambda *args, **kwargs: expected)
    result = run_once_with_report(settings)
    assert result is expected
    lines = (tmp_path / "logs" / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["scanned"] == 3
    assert record["converted"] == 1
