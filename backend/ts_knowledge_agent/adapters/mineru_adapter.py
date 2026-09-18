from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
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

class MinerUConverter:
    def __init__(self, python: str | Path | None, timeout_seconds: int = 3600, chunk_pages: int = 0,
                 render_timeout_seconds: int = 0, render_threads: int = 3):
        if not python:
            raise ValueError("MinerU Python interpreter must be configured explicitly")
        self.python = Path(python)
        self.timeout_seconds = timeout_seconds
        # 大 PDF 分片页数：0 = 不分片。超大文档（实测 736 页 / 1039 图的 Word 导出稿）
        # 单次超时内跑不完，分片后单片规模可控，失败代价从整篇重来降到单片面重来。
        self.chunk_pages = int(chunk_pages or 0)
        # MinerU 内部的 PDF 页面渲染超时与线程数（环境变量 MINERU_PDF_RENDER_*）。
        # 这一层比我们的整次超时更靠底：渲染卡住时 MinerU 自己会先抛 TimeoutError
        # （实测默认 300 秒，CPU 被别的转换占满时 2 页都渲染不完）。
        # 0 = 不注入，沿用 MinerU 默认。
        self.render_timeout_seconds = int(render_timeout_seconds or 0)
        self.render_threads = int(render_threads or 0)
        if not self.python.is_file():
            raise FileNotFoundError(f"MinerU Python interpreter does not exist: {self.python}")
    def convert_to(self, source: Path, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="mineru-") as temp:
            work = Path(temp)
            self._run(source, work)
            md = find_markdown(work / "output")
            shutil.copy2(md, output)
            images = md.parent / "images"
            if images.is_dir():
                shutil.copytree(images, output.parent / "images", dirs_exist_ok=True)
    def _run(self, source: Path, work: Path) -> None:
        script = work / "run.py"
        script.write_text(
            'from pathlib import Path\n' +
            'import shutil\n' +
            'import sys\n' +
            'import tempfile\n' +
            '\n' +
            'from mineru.cli.common import do_parse, read_fn\n' +
            '\n' +
            'PARSE_KWARGS = dict(\n' +
            '    backend="pipeline",\n' +
            '    f_dump_md=True,\n' +
            '    f_dump_middle_json=False,\n' +
            '    f_dump_model_output=False,\n' +
            '    f_dump_orig_pdf=False,\n' +
            '    f_dump_content_list=False,\n' +
            '    f_draw_layout_bbox=False,\n' +
            '    f_draw_span_bbox=False,\n' +
            '    client_side_output_generation=False,\n' +
            ')\n' +
            '\n' +
            'OFFICE_SUFFIXES = {".xls", ".xlsx", ".doc", ".docx", ".ppt", ".pptx"}\n' +
            '\n' +
            '\n' +
            'def parse_once(out_dir, name, payload, start=None, end=None):\n' +
            '    """解析一次；分片时用 start_page_id/end_page_id 限定页范围（闭区间）。"""\n' +
            '    extra = {}\n' +
            '    if start is not None:\n' +
            '        extra["start_page_id"] = start\n' +
            '    if end is not None:\n' +
            '        extra["end_page_id"] = end\n' +
            '    do_parse(str(out_dir), [name], [payload], ["ch"], **PARSE_KWARGS, **extra)\n' +
            '\n' +
            '\n' +
            'def only_markdown(root):\n' +
            '    found = sorted(Path(root).rglob("*.md"))\n' +
            '    if len(found) != 1:\n' +
            '        raise RuntimeError("expected exactly one markdown per part, found " + str(len(found)))\n' +
            '    return found[0]\n' +
            '\n' +
            '\n' +
            'def pdf_page_count(source):\n' +
            '    """读页数失败（缺 pypdf 等）时返回 None，退化为不分片。"""\n' +
            '    try:\n' +
            '        from pypdf import PdfReader\n' +
            '\n' +
            '        return len(PdfReader(str(source)).pages)\n' +
            '    except Exception:\n' +
            '        return None\n' +
            '\n' +
            '\n' +
            'def merge_parts(parts, document, images_out, prefix_rewrites=()):\n' +
            '    """把各分片的 markdown 与图片合并成一份；图片加片名前缀避免同名覆盖。"""\n' +
            '    merged = []\n' +
            '    for tag, md in parts:\n' +
            '        text = md.read_text(encoding="utf-8")\n' +
            '        part_images = md.parent / "images"\n' +
            '        if part_images.is_dir():\n' +
            '            images_out.mkdir(parents=True, exist_ok=True)\n' +
            '            for item in part_images.iterdir():\n' +
            '                if item.is_file():\n' +
            '                    shutil.copy2(item, images_out / (tag + "_" + item.name))\n' +
            '            for pattern in prefix_rewrites:\n' +
            '                text = text.replace(pattern, pattern.replace("images/", "images/" + tag + "_"))\n' +
            '        merged.append(text.strip())\n' +
            '    (document / (document.name + ".md")).write_text("\\n\\n".join(merged) + "\\n", encoding="utf-8")\n' +
            '\n' +
            '\n' +
            'def main():\n' +
            '    source = Path(sys.argv[1])\n' +
            '    out = Path(sys.argv[2])\n' +
            '    chunk = int(sys.argv[3]) if len(sys.argv) > 3 else 0\n' +
            '    suffix = source.suffix.lower()\n' +
            '    payload = source.read_bytes() if suffix in OFFICE_SUFFIXES else read_fn(source)\n' +
            '\n' +
            '    total = pdf_page_count(source) if (chunk > 0 and suffix == ".pdf") else None\n' +
            '    if not total or total <= chunk:\n' +
            '        parse_once(out, source.stem, payload)\n' +
            '        return\n' +
            '\n' +
            '    document = out / source.stem\n' +
            '    document.mkdir(parents=True, exist_ok=True)\n' +
            '    images_out = document / "images"\n' +
            '    parts = []\n' +
            '    with tempfile.TemporaryDirectory(prefix="mineru-parts-") as workspace:\n' +
            '        for index, start in enumerate(range(0, total, chunk), 1):\n' +
            '            end = min(start + chunk, total)\n' +
            '            tag = "part" + format(index, "03d")\n' +
            '            part_dir = Path(workspace) / tag\n' +
            '            parse_once(part_dir, tag, payload, start=start, end=end - 1)\n' +
            '            parts.append((tag, only_markdown(part_dir)))\n' +
            '        merge_parts(\n' +
            '            parts,\n' +
            '            document,\n' +
            '            images_out,\n' +
            '            prefix_rewrites=("](images/", \'src="images/\'),\n' +
            '        )\n' +
            '    print("chunked_parts=" + str(len(parts)) + " of " + str(total) + " pages")\n' +
            '\n' +
            '\n' +
            'if __name__ == "__main__":\n' +
            '    main()\n', encoding="utf-8")
        try:
            child_env = dict(os.environ)
            if self.render_timeout_seconds > 0:
                child_env["MINERU_PDF_RENDER_TIMEOUT"] = str(self.render_timeout_seconds)
            if self.render_threads > 0:
                child_env["MINERU_PDF_RENDER_THREADS"] = str(self.render_threads)
            process = subprocess.Popen(
                [str(self.python), str(script), str(source), str(work / "output"), str(self.chunk_pages)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                encoding="utf-8", errors="replace", env=child_env,
            )
            try:
                stdout, stderr = process.communicate(timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired:
                terminate_process_tree(process)
                raise TimeoutError(
                    f"MinerU 转换超过 {self.timeout_seconds}s 未完成，已终止其进程树（含 worker）"
                ) from None
            result = subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f"MinerU conversion timed out after {self.timeout_seconds}s: {source}") from exc
        if result.returncode:
            raise RuntimeError("MinerU failed: " + (result.stderr or result.stdout)[-4000:])
