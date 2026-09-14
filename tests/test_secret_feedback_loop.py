from pathlib import Path

from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.services.feedback import FeedbackRecord, append_feedback, list_feedback
from ts_knowledge_agent.services.pipeline import run_once
from ts_knowledge_agent.services.registries import export_review_records, write_source_registry

LEAKED = (
    "# leaked doc\n\n"
    "本文档描述某智能体接入方式与调用示例，用于说明集成步骤与注意事项。\n"
    '"apiKey": "sk-live1234567890abc"\n'
)


class CredentialConverter:
    def convert(self, source: Path) -> str:
        return LEAKED


def _feedback_record(output_path: str) -> FeedbackRecord:
    return FeedbackRecord(
        source_relative_path="docs/接入文档.md",
        source_sha256="a" * 64,
        file_type=".md",
        converter="secret-scan",
        converter_version="mineru-3.4.5",
        output_path=output_path,
        category="credential_exposure",
        description="apiKey@L4",
        expected="移除或脱敏凭据后重新转换",
        source_issue=True,
        adapter_issue=False,
        resolution="open",
        review_status="open",
    )


def _settings(tmp_path: Path) -> Settings:
    source = tmp_path / "source"
    source.mkdir()
    (source / "doc.md").write_text("# doc\n", encoding="utf-8")
    settings = Settings("whm", source, tmp_path / "work", tmp_path / "repo", 60)
    settings.working_directory.mkdir(parents=True, exist_ok=True)
    return settings


def test_blocked_secret_writes_one_feedback_record(tmp_path):
    settings = _settings(tmp_path)
    summary = run_once(settings, batch_size=5, converter=CredentialConverter())
    assert summary.reason_counts.get("blocked_secret") == 1
    records = list_feedback(settings.working_directory)
    assert len(records) == 1
    assert records[0].category == "credential_exposure"
    assert records[0].review_status == "open"
    assert "sk-live1234567890abc" not in records[0].description


def test_repeated_block_does_not_duplicate_feedback(tmp_path):
    settings = _settings(tmp_path)
    run_once(settings, batch_size=5, converter=CredentialConverter())
    run_once(settings, batch_size=5, converter=CredentialConverter())
    assert len(list_feedback(settings.working_directory)) == 1


def test_review_export_uses_real_feedback_fields(tmp_path):
    settings = _settings(tmp_path)
    repo = settings.shared_knowledge_repository_directory
    knowledge = repo / "members" / "whm" / "docs" / "接入文档"
    knowledge.mkdir(parents=True, exist_ok=True)
    (knowledge / "接入文档.md").write_text("# 接入文档\n", encoding="utf-8")
    append_feedback(settings.working_directory, _feedback_record(str(knowledge / "接入文档.md")))

    assert export_review_records(settings) == 1
    lines = (repo / "members" / "whm" / "reviews.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    import json

    record = json.loads(lines[0])
    assert record["category"] == "credential_exposure"
    assert record["description"] == "apiKey@L4"
    assert record["knowledge_path"] == "members/whm/docs/接入文档/接入文档.md"
    assert record["member"] == "whm"
    assert record["review_status"] == "open"


def test_review_export_never_leaks_absolute_paths(tmp_path):
    settings = _settings(tmp_path)
    append_feedback(settings.working_directory, _feedback_record(r"C:\Users\86795\secret\doc.md"))
    export_review_records(settings)
    content = (settings.shared_knowledge_repository_directory / "members" / "whm" / "reviews.jsonl").read_text(encoding="utf-8")
    assert "C:\\Users" not in content
    assert "86795" not in content


def test_source_registry_is_idempotent(tmp_path):
    settings = _settings(tmp_path)
    run_once(settings, batch_size=5, converter=CredentialConverter())
    registry = settings.shared_knowledge_repository_directory / "members" / "whm" / "sources.jsonl"
    first = registry.read_text(encoding="utf-8")
    write_source_registry(settings)
    assert registry.read_text(encoding="utf-8") == first
