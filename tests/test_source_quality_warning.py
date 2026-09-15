from pathlib import Path

from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.repositories.state_store import StateStore
from ts_knowledge_agent.services.converter import ORIGIN_SOURCE, ORIGIN_TOOL, convert_file
from ts_knowledge_agent.services.feedback import list_feedback
from ts_knowledge_agent.services.knowledge_tools import knowledge_status
from ts_knowledge_agent.services.pipeline import run_once

BODY = "补充说明文字用于保证内容长度足够，避免触发过短告警。" * 3

SOURCE_WITH_REPLACEMENT = f"# 源文件带乱码的文档\n\n本文档源文件本身含有替换字符 \ufffd 无法还原。\n{BODY}\n"
CLEAN_SOURCE = f"# 干净的源文档\n\n本文档用于对照，内容不含替换字符。\n{BODY}\n"
BROKEN_TOOL_OUTPUT = f"# 工具产物带乱码\n\n转换输出含有替换字符 \ufffd，说明转换可能有问题。\n{BODY}\n"


class BrokenConverter:
    """模拟转换工具输出了乱码。"""

    def convert(self, source: Path) -> str:
        return BROKEN_TOOL_OUTPUT


def _settings(tmp_path: Path, body: str = SOURCE_WITH_REPLACEMENT) -> Settings:
    source = tmp_path / "source"
    source.mkdir()
    (source / "doc.md").write_text(body, encoding="utf-8")
    settings = Settings("whm", source, tmp_path / "work", tmp_path / "repo", 60)
    settings.working_directory.mkdir(parents=True, exist_ok=True)
    return settings


def _stored(settings: Settings) -> tuple[dict, dict]:
    store = StateStore(settings.shared_knowledge_repository_directory / "data" / "state.sqlite3")
    try:
        sources = {row["relative_path"]: row["status"] for row in store.list_sources()}
        conversions = {row["relative_path"]: row for row in store.list_conversions()}
    finally:
        store.close()
    return sources, conversions


def test_source_derived_quality_issue_is_ingested_with_warning(tmp_path):
    settings = _settings(tmp_path)

    summary = run_once(settings, batch_size=5)

    assert summary.warned == 1
    assert summary.converted == 0
    assert summary.failed == 0
    assert summary.reason_counts.get("source_quality_warning") == 1

    repository = settings.shared_knowledge_repository_directory
    documents = list((repository / "members").rglob("*.md"))
    assert documents, "源文件自带的质量问题不应阻止文档入库"

    sources, conversions = _stored(settings)
    assert sources["doc.md"] == "quality_warned"
    assert conversions["doc.md"]["status"] == "quality_warned"
    assert "replacement" in conversions["doc.md"]["warning_message"]

    records = [record for record in list_feedback(settings.working_directory) if record.category == "source_quality_warning"]
    assert len(records) == 1
    assert records[0].source_issue is True
    assert records[0].adapter_issue is False
    assert records[0].review_status == "open"

    reviews = repository / "members" / "whm" / "reviews.jsonl"
    assert reviews.is_file()
    assert "source_quality_warning" in reviews.read_text(encoding="utf-8")


def test_tool_derived_quality_issue_is_still_blocked(tmp_path):
    settings = _settings(tmp_path, CLEAN_SOURCE)

    summary = run_once(settings, batch_size=5, converter=BrokenConverter())

    assert summary.failed == 1
    assert summary.warned == 0
    assert summary.reason_counts.get("quality_failed") == 1

    repository = settings.shared_knowledge_repository_directory
    assert not list((repository / "members").rglob("*.md")), "转换引入的乱码必须继续拦截"

    sources, conversions = _stored(settings)
    assert sources["doc.md"] == "quality_failed"
    assert conversions["doc.md"]["status"] == "quality_failed"


def test_warned_source_is_not_reprocessed_and_keeps_one_feedback_record(tmp_path):
    settings = _settings(tmp_path)

    first = run_once(settings, batch_size=5)
    second = run_once(settings, batch_size=5)

    assert first.warned == 1
    assert second.warned == 0
    assert second.failed == 0
    assert second.reason_counts.get("unchanged") == 1

    records = [record for record in list_feedback(settings.working_directory) if record.category == "source_quality_warning"]
    assert len(records) == 1, "同一版本不应重复写入反馈记录"


def test_warning_is_reported_separately_from_failures(tmp_path):
    settings = _settings(tmp_path)
    run_once(settings, batch_size=5)

    status = knowledge_status(settings)

    assert status["sources"]["quality_warned"] == 1
    assert status["open_issues"] == 0, "告警不应计入失败"
    assert status["open_warnings"] == 1
    assert status["warnings"][0]["path"] == "doc.md"


def test_conversion_origin_distinguishes_source_from_tool(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    markdown = source / "doc.md"
    markdown.write_text(CLEAN_SOURCE, encoding="utf-8")
    plain = source / "note.txt"
    plain.write_text("纯文本内容，用于验证重解码的来源判定。\n", encoding="utf-8")

    direct = convert_file(markdown, tmp_path / "out" / "doc.md")
    decoded = convert_file(plain, tmp_path / "out" / "note.md")
    generated = convert_file(markdown, tmp_path / "out" / "tool.md", converter=BrokenConverter())

    assert direct.origin == ORIGIN_SOURCE and direct.from_source is True
    assert decoded.origin == ORIGIN_SOURCE and decoded.from_source is True
    assert generated.origin == ORIGIN_TOOL and generated.from_source is False
