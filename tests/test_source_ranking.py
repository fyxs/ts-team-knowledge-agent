"""来源展示规则：按证据强度筛选 + 硬上限，避免"来源数量由搜索次数决定"。"""

import pytest

from ts_knowledge_agent.agent.runtime import rank_sources
from ts_knowledge_agent.config import (
    DEFAULT_SOURCES_MAX_DISPLAY,
    DEFAULT_SOURCES_RELEVANCE_RATIO,
    parse_sources_max_display,
    parse_sources_relevance_ratio,
)


def test_shows_all_when_evidence_is_equal_but_respects_cap() -> None:
    paths = [f"members/whm/doc{i}/doc{i}.md" for i in range(20)]
    evidence = {path: {"hits": 1, "strong": True, "read": False} for path in paths}

    kept = rank_sources(paths, evidence, max_display=8, ratio=0.5)

    assert len(kept) == 8
    assert kept == paths[:8]


def test_drops_sources_weaker_than_ratio_of_best() -> None:
    evidence = {
        "members/whm/strong/strong.md": {"hits": 3, "strong": True, "read": True},   # 8
        "members/whm/mid/mid.md": {"hits": 1, "strong": True, "read": False},        # 3
        "members/whm/weak/weak.md": {"hits": 1, "strong": False, "read": False},     # 1
    }
    kept = rank_sources(list(evidence), evidence, max_display=8, ratio=0.3)

    assert kept == ["members/whm/strong/strong.md", "members/whm/mid/mid.md"]
    assert "members/whm/weak/weak.md" not in kept


def test_opened_document_outranks_single_search_hit() -> None:
    evidence = {
        "members/whm/opened/opened.md": {"hits": 1, "strong": False, "read": True},
        "members/whm/searched/searched.md": {"hits": 1, "strong": True, "read": False},
    }
    kept = rank_sources(list(evidence), evidence, max_display=8, ratio=0.0)

    assert kept == ["members/whm/opened/opened.md", "members/whm/searched/searched.md"]


def test_ties_keep_first_seen_order() -> None:
    paths = ["a.md", "b.md", "c.md"]
    evidence = {path: {"hits": 2, "strong": True, "read": False} for path in paths}

    assert rank_sources(paths, evidence, max_display=3, ratio=0.5) == paths


def test_paths_without_evidence_are_kept_when_everything_is_unknown() -> None:
    paths = ["a.md", "b.md"]

    assert rank_sources(paths, {}, max_display=8, ratio=0.5) == paths


def test_empty_input_returns_empty() -> None:
    assert rank_sources([], {}, max_display=8, ratio=0.5) == []


def test_duplicate_paths_are_merged() -> None:
    evidence = {"a.md": {"hits": 2, "strong": True, "read": False}}

    assert rank_sources(["a.md", "a.md", "b.md"], evidence, max_display=8, ratio=0.0) == ["a.md", "b.md"]


def test_config_parsers_validate() -> None:
    assert parse_sources_max_display(None) == DEFAULT_SOURCES_MAX_DISPLAY
    assert parse_sources_max_display("5") == 5
    assert parse_sources_relevance_ratio(None) == DEFAULT_SOURCES_RELEVANCE_RATIO
    assert parse_sources_relevance_ratio("0.3") == 0.3

    with pytest.raises(ValueError):
        parse_sources_max_display(0)
    with pytest.raises(ValueError):
        parse_sources_relevance_ratio(1.5)
