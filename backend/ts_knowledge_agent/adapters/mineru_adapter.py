from __future__ import annotations

import hashlib
import os
import shutil
import signal
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def terminate_process_tree(process) -> None:
    """终止子进程**及其整棵进程树**。

    MinerU 会派生 multiprocessing worker；只杀直接子进程会留下孤儿 worker
    （实测残留 3~6 小时，并卡死后续整轮转换：转换运行一直等它们）。
    """
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, timeout=60)
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except Exception:
        process.kill()
    try:
        process.wait(timeout=15)
    except Exception:
        pass


def find_markdown(root: Path) -> Path:
    files = sorted(root.rglob("*.md"))
    if len(files) != 1:
        raise RuntimeError(f"expected exactly one MinerU markdown output, found {len(files)}")
    return files[0]


WORKER_SCRIPT = '''"""MinerU 单次解析的执行体（由适配器生成，不是项目代码的一部分）。

用法：
    python worker.py pages <source>                      # 输出页数（PDF；其它格式输出 0）
    python worker.py parse <source> <out_dir> [start] [end]   # start/end 为闭区间页码
"""

import sys
from pathlib import Path

from mineru.cli.common import do_parse, read_fn

PARSE_KWARGS = dict(
    backend="pipeline",
    f_dump_md=True,
    f_dump_middle_json=False,
    f_dump_model_output=False,
    f_dump_orig_pdf=False,
    f_dump_content_list=False,
    f_draw_layout_bbox=False,
    f_draw_span_bbox=False,
    client_side_output_generation=False,
)

OFFICE_SUFFIXES = {"xls", "xlsx", "doc", "docx", "ppt", "pptx"}


def pdf_pages(source):
    """页数读取失败（缺 pypdf 等）时返回 0，调用侧会退化为整篇转换。"""

    if source.suffix.lower() != ".pdf":
        return 0
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(source)).pages)
    except Exception:
        return 0


def main():
    mode = sys.argv[1]
    source = Path(sys.argv[2])
    if mode == "pages":
        print(pdf_pages(source))
        return
    out_dir = Path(sys.argv[3])
    extra = {}
    if len(sys.argv) > 4 and sys.argv[4].strip():
        extra["start_page_id"] = int(sys.argv[4])
    if len(sys.argv) > 5 and sys.argv[5].strip():
        extra["end_page_id"] = int(sys.argv[5])
    suffix = source.suffix.lower().lstrip(".")
    payload = source.read_bytes() if suffix in OFFICE_SUFFIXES else read_fn(source)
    do_parse(str(out_dir), [source.stem], [payload], ["ch"], **PARSE_KWARGS, **extra)


if __name__ == "__main__":
    main()
'''


def available_memory_mb() -> int:
    """可用物理内存（MB）；读不到时返回 0（调用侧按保守值处理）。"""

    try:
        if os.name == "nt":
            import ctypes

            class MemoryStatusEx(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            status = MemoryStatusEx()
            status.dwLength = ctypes.sizeof(MemoryStatusEx)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullAvailPhys / 1024 / 1024)
            return 0
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        return 0
    return 0


def resolve_concurrency(requested: int, memory_mb_per_worker: int = 4500) -> int:
    """并发数：受显式配置与可用内存双重约束，至少 1。

    实测单个 MinerU 进程峰值约 3.8GB；这里留出余量（默认按 4.5GB/worker 估算），
    避免为了提速把机器压到换页。
    """

    want = max(1, int(requested or 1))
    available = available_memory_mb()
    if available <= 0:
        return min(want, 2)  # 读不到内存时保守取 2
    allowed = max(1, int(available * 0.7 / memory_mb_per_worker))
    return max(1, min(want, allowed))


class MinerUConverter:
    def __init__(self, python: str | Path | None, timeout_seconds: int = 3600, chunk_pages: int = 0,
                 render_timeout_seconds: int = 0, render_threads: int = 3, chunk_concurrency: int = 2):
        if not python:
            raise ValueError("MinerU Python interpreter must be configured explicitly")
        self.python = Path(python)
        self.timeout_seconds = timeout_seconds
        # 大 PDF 分片页数：0 = 不分片。超大文档（实测 736 页 / 1039 图的 Word 导出稿）
        # 单次超时内跑不完，分片后单片规模可控，失败代价从整篇重来降到单片面重来。
        self.chunk_pages = int(chunk_pages or 0)
        # 分片并发：实测 MinerU 只用 6/20 核，逐片串行浪费机器；并发跑不同页段可成倍缩短总时长。
        # 实际并发还会按可用内存下调（见 resolve_concurrency）。
        self.chunk_concurrency = int(chunk_concurrency or 1)
        # MinerU 内部的 PDF 页面渲染超时与线程数（环境变量 MINERU_PDF_RENDER_*）。
        # 这一层比我们的整次超时更靠底：渲染卡住时 MinerU 自己会先抛 TimeoutError
        # （实测默认 300 秒，CPU 被别的转换占满时 2 页都渲染不完）。
        # 0 = 不注入，沿用 MinerU 默认。
        self.render_timeout_seconds = int(render_timeout_seconds or 0)
        self.render_threads = int(render_threads or 0)
        if not self.python.is_file():
            raise FileNotFoundError(f"MinerU Python interpreter does not exist: {self.python}")

    # ---------- 对外入口 ----------

    def convert_to(self, source: Path, output: Path, work_root: Path | None = None) -> None:
        """转换一个文件。

        work_root 给出时，分片中间产物落在其中并**保留**：中断后重跑只补缺口（断点续传）。
        不传则退化为一次性的临时目录（老行为，整篇重跑）。
        """

        output.parent.mkdir(parents=True, exist_ok=True)
        total = self._page_count(source) if self.chunk_pages > 0 else 0
        if total <= self.chunk_pages:
            # 无需分片：整篇转换（保持既有行为，含临时目录清理）
            work = Path(work_root) if work_root else Path(output.parent / ".mineru-work")
            work.mkdir(parents=True, exist_ok=True)
            self._run_worker("parse", source, work / "output")
            md = find_markdown(work / "output")
            self._publish_single(md, output)
            if work_root is None:
                shutil.rmtree(work, ignore_errors=True)
            return
        self._convert_chunked(source, output, total, Path(work_root) if work_root else output.parent / ".mineru-chunks")

    # ---------- 分片 + 并发 + 续传 ----------

    def _convert_chunked(self, source: Path, output: Path, total_pages: int, work_root: Path) -> None:
        session = work_root / _session_key(source)
        session.mkdir(parents=True, exist_ok=True)
        worker = self._write_worker(session)
        ranges = _page_ranges(total_pages, self.chunk_pages)

        def part_dir(index: int) -> Path:
            return session / f"part{index:03d}"

        pending = [i for i, _ in enumerate(ranges, 1) if not (part_dir(i) / ".done").is_file()]
        concurrency = resolve_concurrency(self.chunk_concurrency)
        if pending:
            self._run_parts_parallel(pending, ranges, source, worker, part_dir, concurrency)

        remaining = [i for i, _ in enumerate(ranges, 1) if not (part_dir(i) / ".done").is_file()]
        if remaining:
            raise RuntimeError(
                "MinerU chunked conversion incomplete: missing parts "
                + ", ".join(str(i) for i in remaining)
                + f"（共 {len(ranges)} 片；已完成 {len(ranges) - len(remaining)} 片，重跑会接着补）"
            )
        self._merge_parts(ranges, part_dir, output)

    def _run_parts_parallel(self, pending, ranges, source, worker, part_dir, concurrency: int) -> None:
        """并发执行未完成的分片；单片失败只记该片，不放弃其他片（下轮补跑）。"""

        failures: list[str] = []
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {}
            for index in pending:
                start, end = ranges[index - 1]
                futures[pool.submit(self._run_one_part, source, worker, part_dir(index), start, end)] = index
            for future in as_completed(futures):
                index = futures[future]
                try:
                    future.result()
                except Exception as exc:  # 单片失败：记录后继续，让其他片跑完
                    failures.append(f"part{index:03d}: {type(exc).__name__}: {exc}")
        if failures and len(failures) == len(pending):
            raise RuntimeError("MinerU 分片全部失败：" + " | ".join(failures[:3]))

    def _run_one_part(self, source: Path, worker: Path, target: Path, start: int, end: int) -> None:
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True, exist_ok=True)
        self._run_worker("parse", source, target / "output", start=start, end=end, script=worker)
        md = find_markdown(target / "output")
        # 归一化落点：partNNN/<name>.md + partNNN/images/*，便于合并与续传判断
        shutil.move(str(md), str(target / md.name))
        images = md.parent / "images"
        if images.is_dir():
            shutil.move(str(images), str(target / "images"))
        shutil.rmtree(target / "output", ignore_errors=True)
        (target / ".done").write_text("ok", encoding="utf-8")

    def _merge_parts(self, ranges, part_dir, output: Path) -> None:
        """按片序合并 markdown；图片统一加片名前缀，避免不同片同名图片互相覆盖。"""

        chunks: list[str] = []
        images_out = output.parent / "images"
        for index, _ in enumerate(ranges, 1):
            target = part_dir(index)
            markdowns = sorted(p for p in target.glob("*.md") if p.name != ".done")
            if not markdowns:
                raise RuntimeError(f"missing markdown for part{index:03d}")
            text = markdowns[0].read_text(encoding="utf-8", errors="replace")
            tag = f"part{index:03d}"
            part_images = target / "images"
            if part_images.is_dir():
                images_out.mkdir(parents=True, exist_ok=True)
                for item in part_images.iterdir():
                    if item.is_file():
                        shutil.copy2(item, images_out / f"{tag}_{item.name}")
                text = text.replace("](images/", f"](images/{tag}_")
                text = text.replace('src="images/', f'src="images/{tag}_')
            chunks.append(text.strip())
        output.write_text("\n\n".join(chunks) + "\n", encoding="utf-8")

    def _publish_single(self, md: Path, output: Path) -> None:
        shutil.copy2(md, output)
        images = md.parent / "images"
        if images.is_dir():
            shutil.copytree(images, output.parent / "images", dirs_exist_ok=True)

    # ---------- 子进程 ----------

    def _page_count(self, source: Path) -> int:
        try:
            result = self._run_worker("pages", source, None, capture=True)
        except Exception:
            return 0
        try:
            return int((result or "").strip().splitlines()[-1])
        except (ValueError, IndexError):
            return 0

    def _write_worker(self, session: Path) -> Path:
        script = session / "mineru_worker.py"
        if not script.is_file() or script.read_text(encoding="utf-8", errors="replace") != WORKER_SCRIPT:
            script.write_text(WORKER_SCRIPT, encoding="utf-8")
        return script

    def _child_env(self) -> dict:
        env = dict(os.environ)
        if self.render_timeout_seconds > 0:
            env["MINERU_PDF_RENDER_TIMEOUT"] = str(self.render_timeout_seconds)
        if self.render_threads > 0:
            env["MINERU_PDF_RENDER_THREADS"] = str(self.render_threads)
        return env

    def _run_worker(self, mode: str, source: Path, out_dir: Path | None, start: int | None = None,
                    end: int | None = None, script: Path | None = None, capture: bool = False):
        """子进程执行 worker：parse 或 pages。返回 stdout（capture=True 时）。"""

        if script is None:
            work = (out_dir or source.parent).parent
            work.mkdir(parents=True, exist_ok=True)
            script = self._write_worker(work)
        args = [str(self.python), str(script), mode, str(source)]
        if out_dir is not None:
            args.append(str(out_dir))
            args.append("" if start is None else str(start))
            args.append("" if end is None else str(end))
        try:
            process = subprocess.Popen(args, stdout=subprocess.PIPE if (capture or out_dir is not None) else None,
                                       stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                                       env=self._child_env())
            try:
                stdout, stderr = process.communicate(timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired:
                terminate_process_tree(process)
                raise TimeoutError(
                    f"MinerU 转换超过 {self.timeout_seconds}s 未完成，已终止其进程树（含 worker）"
                ) from None
        except subprocess.TimeoutExpired as exc:  # pragma: no cover - 兜底
            raise TimeoutError(f"MinerU conversion timed out after {self.timeout_seconds}s: {source}") from exc
        if process.returncode:
            raise RuntimeError("MinerU failed: " + (stderr or stdout or "")[-4000:])
        return stdout if capture else None


def _page_ranges(total: int, chunk: int) -> list[tuple[int, int]]:
    """闭区间页段列表：[(0, chunk-1), (chunk, 2*chunk-1), ...]。"""

    return [(start, min(start + chunk, total) - 1) for start in range(0, total, chunk)]


def _session_key(source: Path) -> str:
    """分片工作区名：路径 + 大小 + mtime，源文件一变就换新会话，避免用到过期分片。"""

    try:
        stat = source.stat()
        seed = f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    except OSError:
        seed = str(source)
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
