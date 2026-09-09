from pathlib import Path
from ts_knowledge_agent.repositories.state_store import StateStore
from ts_knowledge_agent.services.scanner import SourceFile

def source(path, sha):
    return SourceFile(path, Path(path), 1, 1, sha, True)

def test_conversion_reason_lifecycle(tmp_path):
    store=StateStore(tmp_path/"state.sqlite3"); s=source("a.txt","one")
    assert store.conversion_reason(s)=="new_source"
    out=tmp_path/"a.md"; out.write_text("ok",encoding="utf-8")
    store.record_conversion("a.txt","one",out,"test","converted",reason="new_source")
    assert store.conversion_reason(s)=="unchanged"
    assert store.conversion_reason(source("a.txt","two"))=="source_changed"
    out.unlink(); assert store.conversion_reason(s)=="output_missing"
    store.record_conversion("a.txt","one",out,"test","failed_retryable","error",reason="output_missing")
    assert store.conversion_reason(s)=="previous_failed"
    store.close()
