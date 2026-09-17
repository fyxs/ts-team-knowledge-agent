"""转换快慢车道：轻量类型优先，避免新加的 md/txt 被大文件堵在队列后面。"""

from pathlib import Path

import pytest

from ts_knowledge_agent.services.converter import HEAVY_SUFFIXES, conversion_cost_class


@pytest.mark.parametrize('name', ['a.md', 'note.txt', 'table.xlsx'])
def test_light_files_are_class_zero(name: str) -> None:
    assert conversion_cost_class(Path(name)) == 0


@pytest.mark.parametrize('name', ['doc.pdf', 'doc.docx', 'legacy.doc', 'deck.pptx', 'legacy.ppt'])
def test_mineru_files_are_class_one(name: str) -> None:
    assert conversion_cost_class(Path(name)) == 1


def test_suffix_match_is_case_insensitive() -> None:
    assert conversion_cost_class(Path('REPORT.PDF')) == 1


def test_heavy_set_matches_cost_class() -> None:
    for suffix in HEAVY_SUFFIXES:
        assert conversion_cost_class(Path(f'x{suffix}')) == 1


def test_sorting_puts_light_first() -> None:
    files = [Path('a.pdf'), Path('b.md'), Path('c.pptx'), Path('d.txt')]
    ordered = sorted(files, key=conversion_cost_class)
    assert [p.suffix for p in ordered] == ['.md', '.txt', '.pdf', '.pptx']
