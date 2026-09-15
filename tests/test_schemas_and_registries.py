import json
from pathlib import Path

from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.repositories.state_store import StateStore
from ts_knowledge_agent.schemas import KnowledgeEntry, ReviewRecord, SourceRegistration, write_schema_files
from ts_knowledge_agent.services.feedback import FeedbackRecord, append_feedback
from ts_knowledge_agent.services.registries import (
    export_review_records,
    knowledge_entries,
    member_root,
    write_knowledge_registry,
    write_source_registry,
)

SHA = "a" * 64


def _settings(tmp_path: Path) -> Settings:
    settings = Settings("whm", tmp_path / "source", tmp_path / "work", tmp_path / "repo", 5)
    settings.working_directory.mkdir(parents=True, exist_ok=True)
    return settings


def _seed_conversion(settings: Settings, relative="文档.pdf", status="converted"):
    store = StateStore(settings.shared_knowledge_repository_directory / "data" / "state.sqlite3")
    try:
        store.connection.execute(
            "INSERT OR REPLACE INTO sources(relative_path,size,mtime_ns,sha256,status) VALUES(?,?,?,?,?)",
            (relative, 1024, 1, SHA, status),
        )
        store.connection.commit()
        output = member_root(settings) / "文档" / "文档.md"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("# 文档\n\n可用的知识内容，长度足够用于质量检查。\n", encoding="utf-8")
        store.record_conversion(relative, SHA, output, "mineru-3.4.5", status)
    finally:
        store.close()


def test_schema_files_describe_every_artifact(tmp_path):
    written = write_schema_files(tmp_path / "schemas")

    names = {path.name for path in written}
    assert names == {"knowledge-entry.schema.json", "source-registration.schema.json", "review-record.schema.json"}
    for path in written:
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["type"] == "object"
        assert schema["properties"]


def test_source_registry_records_match_schema(tmp_path):
    settings = _settings(tmp_path)
    _seed_conversion(settings)

    write_source_registry(settings)

    lines = (member_root(settings) / "sources.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = SourceRegistration(**json.loads(lines[0]))
    assert record.member == "whm"
    assert record.source_relative_path == "文档.pdf"
    assert record.knowledge_path == "members/whm/文档/文档.md"
    assert record.converter == "mineru"
    assert record.converter_version == "3.4.5"
    assert not Path(record.knowledge_path).is_absolute()


def test_knowledge_registry_lists_documents_with_provenance(tmp_path):
    settings = _settings(tmp_path)
    _seed_conversion(settings)

    write_knowledge_registry(settings)

    lines = (member_root(settings) / "knowledge.jsonl").read_text(encoding="utf-8").strip().splitlines()
    entry = KnowledgeEntry(**json.loads(lines[0]))
    assert entry.path == "members/whm/文档/文档.md"
    assert entry.title == "文档"
    assert entry.source_sha256 == SHA
    assert entry.markdown_bytes > 0
    assert knowledge_entries(settings)[0].path == entry.path


def test_review_export_never_leaks_local_absolute_paths(tmp_path):
    settings = _settings(tmp_path)
    outside = tmp_path / "elsewhere" / "doc.md"
    append_feedback(
        settings.working_directory,
        FeedbackRecord(
            source_relative_path="文档.pdf",
            source_sha256=SHA,
            file_type=".pdf",
            converter="secret-scan",
            converter_version="mineru-3.4.5",
            output_path=str(outside),
            category="encoding",
            description="出现替换字符",
            expected="中文可读",
            source_issue=True,
            adapter_issue=False,
            resolution="open",
            review_status="open",
        ),
    )

    export_review_records(settings)

    raw = (member_root(settings) / "reviews.jsonl").read_text(encoding="utf-8")
    assert str(tmp_path) not in raw
    record = ReviewRecord(**json.loads(raw.strip()))
    assert record.knowledge_path == ""
    assert record.category == "encoding"


def test_registry_is_stable_when_nothing_changed(tmp_path):
    settings = _settings(tmp_path)
    _seed_conversion(settings)

    write_source_registry(settings)
    path = member_root(settings) / "sources.jsonl"
    first = path.read_text(encoding="utf-8")
    write_source_registry(settings)

    assert path.read_text(encoding="utf-8") == first
