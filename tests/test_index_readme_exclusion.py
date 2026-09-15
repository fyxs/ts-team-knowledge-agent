from pathlib import Path

from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.services.indexing import index_converted


def _settings(tmp_path: Path) -> Settings:
    repo = tmp_path / "repo"
    (repo / "members").mkdir(parents=True, exist_ok=True)
    (repo / "members" / "README.md").write_text("# 成员空间\n\n说明文件。\n", encoding="utf-8")
    nested = repo / "members" / "whm" / "文档"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / "README.md").write_text("# 我的说明\n\n成员自己的文档。\n", encoding="utf-8")
    source = tmp_path / "source"
    source.mkdir()
    settings = Settings("whm", source, tmp_path / "work", repo, 60)
    settings.working_directory.mkdir(parents=True, exist_ok=True)
    return settings


def test_index_skips_members_root_readme_but_keeps_nested(tmp_path):
    settings = _settings(tmp_path)
    index_converted(settings)

    from ts_knowledge_agent.services.knowledge_tools import knowledge_list

    paths = {item["path"] for item in knowledge_list(settings)}
    assert "members/README.md" not in paths
    assert "members/whm/文档/README.md" in paths
