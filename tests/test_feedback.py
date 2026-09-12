from ts_knowledge_agent.services.feedback import FeedbackRecord, append_feedback, list_feedback


def test_feedback_record_is_appended_and_read_back(tmp_path):
    record = FeedbackRecord(
        source_relative_path="docs/a.pdf",
        source_sha256="a" * 64,
        file_type=".pdf",
        converter="MinerU",
        converter_version="3.4.5",
        output_path="members/whm/docs/a/a.md",
        category="missing_content",
        description="第二页内容缺失",
        expected="应保留第二页正文",
        source_issue=False,
        adapter_issue=True,
        resolution="open",
        review_status="open",
    )
    path = append_feedback(tmp_path, record)
    rows = list_feedback(tmp_path)
    assert path == tmp_path / "feedback" / "records.jsonl"
    assert len(rows) == 1
    assert rows[0] == record


def test_feedback_rejects_invalid_sha256(tmp_path):
    record = FeedbackRecord(
        source_relative_path="a.md", source_sha256="bad", file_type=".md",
        converter="direct-copy", converter_version="1", output_path="a.md",
        category="other", description="x", expected="y", source_issue=True,
        adapter_issue=False, resolution="open", review_status="open",
    )
    try:
        append_feedback(tmp_path, record)
    except ValueError as exc:
        assert "sha256" in str(exc)
    else:
        raise AssertionError("invalid SHA-256 was accepted")
