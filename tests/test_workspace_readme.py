from pathlib import Path

from ts_knowledge_agent.config import Settings, initialize_working_directory


def _settings(tmp_path: Path) -> Settings:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True, exist_ok=True)
    source = tmp_path / "source"
    source.mkdir()
    return Settings("whm", source, tmp_path / "work", repo, 60)


def test_init_writes_workspace_readme(tmp_path):
    settings = _settings(tmp_path)
    initialize_working_directory(settings)
    readme = settings.working_directory / "README.md"
    assert readme.is_file()
    text = readme.read_text(encoding="utf-8")
    assert "工作目录" in text
    for item in ("runtime/", "secrets/", "knowledge-base/", "logs/"):
        assert item in text


def test_init_keeps_edited_workspace_readme(tmp_path):
    settings = _settings(tmp_path)
    initialize_working_directory(settings)
    readme = settings.working_directory / "README.md"
    readme.write_text("# 我改过的说明\n", encoding="utf-8")
    initialize_working_directory(settings)
    assert readme.read_text(encoding="utf-8") == "# 我改过的说明\n"
