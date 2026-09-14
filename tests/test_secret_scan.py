from pathlib import Path

from ts_knowledge_agent.services.secret_scan import quarantine_document, scan_text


def test_detects_api_key_and_bearer_token():
    text = '# doc\n\n"apiKey": "sk-live1234567890"\nAuthorization: Bearer abcdefghijklmnop\n'
    result = scan_text(text)
    assert not result.ok
    assert "openai_key" in result.kinds()
    assert "credential_field" in result.kinds()
    assert "bearer_token" in result.kinds()


def test_placeholder_and_redacted_values_are_allowed():
    text = (
        "# doc\n\n"
        '"apiKey": "[REDACTED]"\n'
        "Authorization: Bearer <token>\n"
        "Use the header `Authorization: Bearer <token>` in your request.\n"
    )
    result = scan_text(text)
    assert result.ok, result.summary()


def test_plain_prose_is_allowed():
    text = "# doc\n\nThis document explains password validation rules in a form component.\n"
    assert scan_text(text).ok


def test_quarantine_moves_document_outside_repository(tmp_path):
    repository = tmp_path / "repo"
    document = repository / "members" / "whm" / "doc"
    document.mkdir(parents=True)
    (document / "doc.md").write_text("# secret\n", encoding="utf-8")
    working = tmp_path / "work"
    working.mkdir()

    target = quarantine_document(working, repository, document)

    assert target == working / "quarantine" / "members" / "whm" / "doc"
    assert (target / "doc.md").is_file()
    assert not document.exists()
    assert not (repository / "members" / "whm" / "doc").exists()
