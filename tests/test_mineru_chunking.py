"""MinerU 分片：并发执行、断点续传、按页范围调用。

这些用例不调用真正的 MinerU：把内嵌 worker 脚本替换成一个「假解析器」，
它按同样的约定产出 markdown + images，并对每次调用留痕，
于是可以断言「哪些页段被跑过」「重跑是否跳过已完成片」。
"""

import sys
from pathlib import Path

import pytest

from ts_knowledge_agent.adapters import mineru_adapter
from ts_knowledge_agent.adapters.mineru_adapter import MinerUConverter, available_memory_mb, resolve_concurrency

FAKE_WORKER = '''
import sys
from pathlib import Path

mode = sys.argv[1]
source = Path(sys.argv[2])

if mode == "pages":
    print(6)
    raise SystemExit(0)

out = Path(sys.argv[3])
start = sys.argv[4] if len(sys.argv) > 4 else ""
end = sys.argv[5] if len(sys.argv) > 5 else ""

target = out / source.stem
(target / "images").mkdir(parents=True, exist_ok=True)
(target / (source.stem + ".md")).write_text("# pages " + start + "-" + end + "\\n", encoding="utf-8")
(target / "images" / ("img_" + (start or "0") + ".png")).write_bytes(b"x")

with (out.parent / "calls.txt").open("a", encoding="utf-8") as handle:
    handle.write((start or "-") + ":" + (end or "-") + "\\n")
'''


@pytest.fixture()
def converter(monkeypatch, tmp_path):
    monkeypatch.setattr(mineru_adapter, "WORKER_SCRIPT", FAKE_WORKER)
    source = tmp_path / "big.pdf"
    source.write_bytes(b"%PDF-1.4")
    return MinerUConverter(sys.executable, timeout_seconds=120, chunk_pages=2, chunk_concurrency=2), source, tmp_path


def test_chunked_conversion_runs_every_page_range(converter) -> None:
    impl, source, tmp_path = converter
    output = tmp_path / "out" / "big.md"
    impl.convert_to(source, output, work_root=tmp_path / "chunks")

    body = output.read_text(encoding="utf-8")
    # 6 页 / 每片 2 页 = 3 片，按页序合并
    assert body.index("0-1") < body.index("2-3") < body.index("4-5")
    call_files = sorted((tmp_path / "chunks").glob("*/part*/calls.txt"))
    assert len(call_files) == 3, f"应有三片各自的调用记录，实际 {len(call_files)}"
    seen = sorted(line for f in call_files for line in f.read_text(encoding="utf-8").split())
    assert seen == ["0:1", "2:3", "4:5"]


def test_chunked_conversion_prefixes_images_per_part(converter) -> None:
    impl, source, tmp_path = converter
    output = tmp_path / "out" / "big.md"
    impl.convert_to(source, output, work_root=tmp_path / "chunks")

    images = sorted(p.name for p in (tmp_path / "out" / "images").iterdir())
    assert len(images) == 3
    assert images == ["part001_img_0.png", "part002_img_2.png", "part003_img_4.png"], images


def test_completed_parts_are_reused_on_rerun(converter) -> None:
    """断点续传：已完成的片不重跑（这是把 5 小时压到 1.5 小时的关键之一）。"""

    impl, source, tmp_path = converter
    out_dir = tmp_path / "out"
    work = tmp_path / "chunks"

    executed: list[tuple[int, int]] = []
    original = impl._run_one_part

    def tracking(source_arg, worker, target, start, end):
        executed.append((start, end))
        return original(source_arg, worker, target, start, end)

    impl._run_one_part = tracking  # type: ignore[method-assign]

    impl.convert_to(source, out_dir / "big.md", work_root=work)
    assert executed == [(0, 1), (2, 3), (4, 5)], executed

    # 模拟「中断后重跑」：删掉最后一片的完成标记
    part3 = sorted(work.glob("*/part003"))[0]
    (part3 / ".done").unlink()
    executed.clear()

    impl.convert_to(source, out_dir / "big.md", work_root=work)
    assert executed == [(4, 5)], f"只应补跑缺失的第 3 片，实际 {executed}"


def test_missing_parts_are_reported_after_retry(converter, monkeypatch) -> None:
    """片跑不出来时必须明确报错，而不是产出残缺的合并结果。"""

    impl, source, tmp_path = converter
    impl.timeout_seconds = 999  # 避免误判

    def always_fail(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(impl, "_run_one_part", always_fail)
    with pytest.raises(RuntimeError) as excinfo:
        impl.convert_to(source, tmp_path / "out" / "big.md", work_root=tmp_path / "chunks")
    assert "分片" in str(excinfo.value) or "chunked" in str(excinfo.value)


def test_small_document_skips_chunking(monkeypatch, tmp_path) -> None:
    """页数不超过分片阈值时走整篇转换（保持既有行为）。"""

    monkeypatch.setattr(mineru_adapter, "WORKER_SCRIPT", FAKE_WORKER)
    source = tmp_path / "small.pdf"
    source.write_bytes(b"%PDF-1.4")
    impl = MinerUConverter(sys.executable, timeout_seconds=120, chunk_pages=100)

    output = tmp_path / "out" / "small.md"
    impl.convert_to(source, output, work_root=tmp_path / "chunks")
    assert output.is_file()
    assert not list((tmp_path / "chunks").glob("*/part001")), "整篇转换不应产生分片目录"


def test_concurrency_respects_memory_and_config() -> None:
    """并发受配置与可用内存双重约束，至少 1。"""

    assert resolve_concurrency(1) >= 1
    assert resolve_concurrency(2) >= 1
    # 显式要很多并发时，也不会超过内存允许的上限
    huge = resolve_concurrency(99)
    assert 1 <= huge <= 99
    if available_memory_mb() > 0:
        assert huge <= max(1, int(available_memory_mb() * 0.7 / 4500))


def test_whole_document_conversion_isolates_from_other_documents(monkeypatch, tmp_path) -> None:
    """整篇转换不得与共享工作区里其它文档的产物混淆。

    回归：work_root 是**所有文档共享**的（converter 传 <工作区>/runtime/mineru-chunks）。
    若整篇转换把产物直接落到 work_root/output/，别的文档产物会混进来，
    find_markdown 的「恰好一个 markdown」断言必然失败 —— 现场表现是
    「产物其实已生成，却被记成 failed 并无限重试、每次烧 5-6 分钟」。
    """

    monkeypatch.setattr(mineru_adapter, "WORKER_SCRIPT", FAKE_WORKER)
    source = tmp_path / "small.pdf"
    source.write_bytes(b"%PDF-1.4")
    impl = MinerUConverter(sys.executable, timeout_seconds=120, chunk_pages=100)

    work_root = tmp_path / "chunks"
    # 预置其它文档遗留的产物，复现「共享目录已被污染」的现场
    for name in ("other-a", "other-b", "other-c"):
        leftover = work_root / "output" / name
        leftover.mkdir(parents=True)
        (leftover / (name + ".md")).write_text("# 别的文档\n", encoding="utf-8")

    output = tmp_path / "out" / "small.md"
    impl.convert_to(source, output, work_root=work_root)

    assert output.is_file(), "共享目录里有其它文档产物时，整篇转换仍应成功"
    body = output.read_text(encoding="utf-8")
    assert body.startswith("# pages"), f"产物应是本次转换的内容，实际是：{body[:40]!r}"


def test_whole_document_conversion_cleans_its_own_work_dir(monkeypatch, tmp_path) -> None:
    """整篇转换没有可续传的单元，成功后应清理自己的工作区。

    否则共享工作区会随文档数无限膨胀（分片才有 .done 断点，整篇没有）。
    """

    monkeypatch.setattr(mineru_adapter, "WORKER_SCRIPT", FAKE_WORKER)
    source = tmp_path / "small.pdf"
    source.write_bytes(b"%PDF-1.4")
    impl = MinerUConverter(sys.executable, timeout_seconds=120, chunk_pages=100)

    work_root = tmp_path / "chunks"
    work_root.mkdir(parents=True)
    before = {p.name for p in work_root.iterdir()}

    impl.convert_to(source, tmp_path / "out" / "small.md", work_root=work_root)

    after = {p.name for p in work_root.iterdir()}
    assert after == before, f"整篇转换应清理自身工作区，实际多出：{sorted(after - before)}"
