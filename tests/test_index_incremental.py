"""索引增量：未变更文档不重写，缩短写锁窗口（并发时 database is locked 的直接诱因）。"""

from pathlib import Path

import pytest

from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.services import indexing


def make_settings(tmp_path: Path) -> Settings:
    return Settings("whm", tmp_path / "source", tmp_path / "work", tmp_path / "repo", 60)


def test_index_skips_unchanged_documents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(tmp_path)
    docs = settings.shared_knowledge_repository_directory / "members" / "whm" / "a"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "a.md").write_text("# A\n\n正文\n", encoding="utf-8")
    (docs / "b.md").write_text("# B\n\n正文\n", encoding="utf-8")

    calls: list[str] = []
    original = indexing.SearchStore.upsert

    def counting(self, path, *args, **kwargs):
        calls.append(path)
        return original(self, path, *args, **kwargs)

    monkeypatch.setattr(indexing.SearchStore, "upsert", counting)

    assert indexing.index_converted(settings) == 2
    assert len(calls) == 2

    calls.clear()
    assert indexing.index_converted(settings) == 2
    assert calls == [], "内容未变更时不应重写索引（每轮 700+ 次写入是锁冲突的来源）"

    (docs / "a.md").write_text("# A\n\n正文改了\n", encoding="utf-8")
    calls.clear()
    indexing.index_converted(settings)
    assert len(calls) == 1, "只有变更过的文档才重写"
    assert calls[0].endswith("a.md")
