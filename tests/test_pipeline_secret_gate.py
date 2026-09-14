from pathlib import Path

from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.repositories.state_store import StateStore
from ts_knowledge_agent.services.pipeline import run_once

LEAKY_BODY = (
    "# leaked document\n\n"
    "This document records an internal integration example. " * 3
    + '\n"apiKey": "sk-live1234567890abcdef"\n'
)

CLEAN_BODY = (
    "# clean document\n\n"
    "This document records clean internal knowledge with enough detail. " * 3
    + "\n"
)


class CredentialConverter:
    def convert(self, source: Path) -> str:
        return LEAKY_BODY


class CleanConverter:
    def convert(self, source: Path) -> str:
        return CLEAN_BODY


def _settings(tmp_path: Path) -> Settings:
    source = tmp_path / "source"
    source.mkdir()
    (source / "doc.md").write_text("# doc\n", encoding="utf-8")
    settings = Settings("whm", source, tmp_path / "work", tmp_path / "repo", 60)
    settings.working_directory.mkdir(parents=True, exist_ok=True)
    return settings


def test_pipeline_blocks_credentials_before_shared_repository(tmp_path):
    settings = _settings(tmp_path)

    summary = run_once(settings, batch_size=5, converter=CredentialConverter())

    assert summary.converted == 0
    assert summary.failed == 1
    assert summary.reason_counts.get("blocked_secret") == 1

    repository = settings.shared_knowledge_repository_directory
    assert not list((repository / "members").rglob("*.md")), "credential output must not stay in the shared repository"

    quarantined = list((settings.working_directory / "quarantine").rglob("*.md"))
    assert quarantined, "blocked output must be quarantined for human review"

    store = StateStore(repository / "data" / "state.sqlite3")
    try:
        statuses = {row["relative_path"]: row["status"] for row in store.list_sources()}
        conversions = {row["relative_path"]: row["status"] for row in store.list_conversions()}
    finally:
        store.close()
    assert statuses["doc.md"] == "blocked_secret"
    assert conversions["doc.md"] == "blocked_secret"


def test_pipeline_sync_is_blocked_when_credentials_were_found(tmp_path):
    settings = _settings(tmp_path)

    summary = run_once(settings, sync=True, batch_size=5, converter=CredentialConverter())

    assert summary.sync_status == "blocked_secret"


def test_pipeline_allows_clean_content(tmp_path):
    settings = _settings(tmp_path)

    summary = run_once(settings, batch_size=5, converter=CleanConverter())

    assert summary.converted == 1
    assert summary.failed == 0
    assert not (settings.working_directory / "quarantine").exists()
