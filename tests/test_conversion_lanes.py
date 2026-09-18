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


# ---------- 车道（P1）：排序收敛 / 取件过滤 / 独立锁；耗时审计（P2） ----------

import json

from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.services.pipeline import LANE_HEAVY, LANE_LIGHT, plan_batches, run_once
from ts_knowledge_agent.services.scanner import SourceFile

FAKE_MARKDOWN = "# fake\n\n" + "转换占位内容。" * 30


class FakeConverter:
    """替身转换器：任何格式都能产出合格 Markdown，避免测试依赖 MinerU。"""

    def convert(self, source):  # noqa: ANN001 - 与真实转换器同形
        return FAKE_MARKDOWN


def build_settings(tmp_path: Path, source_root: Path) -> Settings:
    return Settings("wanghm", source_root, tmp_path, tmp_path / "repo", 60, "unused")


def prepare_source_root(tmp_path: Path) -> Path:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "note.md").write_text("# note\n\n" + "正文内容。" * 30, encoding="utf-8")
    (source_root / "doc.pdf").write_bytes(b"%PDF-1.4 fake payload")
    return source_root


def test_mixed_types_put_light_sources_first() -> None:
    files = [SourceFile(name, Path(name), 1, 1, name) for name in ("big.pdf", "note.md", "deck.pptx", "plain.txt")]
    batches = plan_batches(files, 2)
    ordered = [item.relative_path for batch in batches for item in batch.files]
    assert ordered == ["note.md", "plain.txt", "big.pdf", "deck.pptx"]


def test_light_lane_touches_only_light_sources(tmp_path: Path) -> None:
    settings = build_settings(tmp_path, prepare_source_root(tmp_path))
    handled: list[str] = []
    run_once(
        settings,
        lane=LANE_LIGHT,
        converter=FakeConverter(),
        on_batch=lambda batch: handled.extend(item.relative_path for item in batch.files),
    )
    assert handled == ["note.md"]


def test_heavy_lane_skips_light_sources(tmp_path: Path) -> None:
    settings = build_settings(tmp_path, prepare_source_root(tmp_path))
    handled: list[str] = []
    summary = run_once(
        settings,
        lane=LANE_HEAVY,
        converter=FakeConverter(),
        on_batch=lambda batch: handled.extend(item.relative_path for item in batch.files),
    )
    assert handled == ["doc.pdf"]
    assert summary.reason_counts.get("deferred_to_other_lane") == 1


def test_light_lane_holds_its_own_lock(tmp_path: Path) -> None:
    """轻量车道必须用自己的锁，绝不能嵌在重活锁里（mis 踩过的坑）。"""

    settings = build_settings(tmp_path, prepare_source_root(tmp_path))
    seen: dict[str, bool] = {}

    def observe(batch) -> None:  # noqa: ANN001
        runtime = tmp_path / "runtime"
        seen["light"] = (runtime / "light.lock").exists()
        seen["run"] = (runtime / "run.lock").exists()

    run_once(settings, lane=LANE_LIGHT, converter=FakeConverter(), on_batch=observe)
    assert seen == {"light": True, "run": False}
    assert not (tmp_path / "runtime" / "light.lock").exists()  # 正常结束后释放


def test_unknown_lane_is_rejected(tmp_path: Path) -> None:
    settings = build_settings(tmp_path, prepare_source_root(tmp_path))
    with pytest.raises(ValueError):
        run_once(settings, lane="fast")


def test_conversion_timing_log_records_each_file(tmp_path: Path) -> None:
    settings = build_settings(tmp_path, prepare_source_root(tmp_path))
    run_once(settings, lane=LANE_LIGHT, converter=FakeConverter())
    log = tmp_path / "logs" / "conversions.jsonl"
    assert log.is_file(), "逐篇耗时审计没有落盘（曾因缺 import 被静默吞掉）"
    records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert records, "日志文件为空"
    assert records[-1]["source_name"] == "note.md"
    assert records[-1]["status"] == "ok"
    assert isinstance(records[-1]["seconds"], (int, float))

def test_failed_conversion_is_audited(tmp_path):
    """失败/超时也必须写审计：那是判断"卡住"与"在跑"的主要依据。"""

    from ts_knowledge_agent.config import Settings
    from ts_knowledge_agent.services.pipeline import run_once
    import json

    source_root = tmp_path / "source"; repo = tmp_path / "repo"
    source_root.mkdir()
    (source_root / "boom.pdf").write_bytes(b"%PDF-1.4 fake")

    settings = Settings("wanghm", source_root, tmp_path, repo, 60, "unused")

    class Exploding:
        def convert(self, source):
            raise TimeoutError("MinerU conversion timed out after 3600s")

    summary = run_once(settings, batch_size=5, converter=Exploding())
    assert summary.failed == 1

    audit = tmp_path / "logs" / "conversions.jsonl"
    assert audit.is_file(), "失败轮次也必须落审计日志"
    records = [json.loads(l) for l in audit.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert records and records[-1]["status"] == "failed:TimeoutError"
    assert records[-1]["source_name"] == "boom.pdf"
    assert "seconds" in records[-1] and records[-1]["seconds"] >= 0

def test_queue_rank_defers_known_slow_documents() -> None:
    """已知很慢的大文档必须排在中小文档之后 —— 否则整轮被它堵死。"""

    from ts_knowledge_agent.services.pipeline import queue_rank
    from ts_knowledge_agent.services.scanner import SourceFile
    from pathlib import Path as _Path

    def src(name: str) -> SourceFile:
        return SourceFile(name, _Path(name), 1, 1, name)

    fast, slow, light = src("a.pdf"), src("big.pdf"), src("note.md")
    estimates = {"big.pdf": 3600.0}

    ranks = {s.relative_path: queue_rank(s, estimates, 600, 20)[0] for s in (fast, slow, light)}
    assert ranks["note.md"] == 0, "轻量文档最前"
    assert ranks["a.pdf"] == 1, "普通重活居中"
    assert ranks["big.pdf"] == 3, "实测慢文档排最后"

    ordered = sorted((light, slow, fast), key=lambda s: queue_rank(s, estimates, 600, 20))
    assert [s.relative_path for s in ordered] == ["note.md", "a.pdf", "big.pdf"]


def test_queue_rank_defers_oversized_first_time_documents(tmp_path) -> None:
    """没有历史、但体积超大的重活文档同样后置（阈值可关）。"""

    from ts_knowledge_agent.services.pipeline import queue_rank
    from ts_knowledge_agent.services.scanner import SourceFile

    big = tmp_path / "huge.pdf"
    big.write_bytes(b"x" * (25 * 1024 * 1024))
    small = tmp_path / "small.pdf"
    small.write_bytes(b"x" * 1024)

    big_src = SourceFile("huge.pdf", big, 1, 1, "huge.pdf")
    small_src = SourceFile("small.pdf", small, 1, 1, "small.pdf")

    assert queue_rank(big_src, {}, 600, 20)[0] == 2
    assert queue_rank(small_src, {}, 600, 20)[0] == 1
    # 关闭体积后置时退回普通重活
    assert queue_rank(big_src, {}, 600, 0)[0] == 1
    # 关掉慢文档后置时也退回普通重活
    assert queue_rank(big_src, {"huge.pdf": 9999.0}, 0, 0)[0] == 1


def test_slow_source_estimates_reads_audit_log(tmp_path) -> None:
    """历史耗时来自逐篇审计；损坏行与缺字段必须被忽略而不是报错。"""

    import json

    from ts_knowledge_agent.services.pipeline import slow_source_estimates

    logs = tmp_path / "logs"; logs.mkdir()
    (logs / "conversions.jsonl").write_text(
        "\n".join([
            json.dumps({"relative_path": "a.pdf", "seconds": 12.5, "status": "ok"}),
            json.dumps({"relative_path": "a.pdf", "seconds": 30.0, "status": "ok"}),
            json.dumps({"source_name": "no-relative.pdf", "seconds": 99.0}),
            "{ 坏行",
            json.dumps({"relative_path": "b.pdf", "seconds": "7"}),
        ]),
        encoding="utf-8",
    )

    estimates = slow_source_estimates(tmp_path)
    assert estimates["a.pdf"] == 30.0, "同名取最大耗时"
    assert estimates["b.pdf"] == 7.0
    assert "no-relative.pdf" not in estimates


def test_slow_source_estimates_without_audit_file(tmp_path) -> None:
    from ts_knowledge_agent.services.pipeline import slow_source_estimates

    assert slow_source_estimates(tmp_path) == {}
