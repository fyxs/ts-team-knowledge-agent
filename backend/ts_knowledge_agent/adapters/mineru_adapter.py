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
    def __init__(self, python: str | Path | None, timeout_seconds: int = 3600):
        if not python:
            raise ValueError("MinerU Python interpreter must be configured explicitly")
        self.python = Path(python)
        self.timeout_seconds = timeout_seconds
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
        script.write_text('from pathlib import Path\nimport sys\nfrom mineru.cli.common import do_parse, read_fn\n\ndef main():\n    source = Path(sys.argv[1])\n    out = Path(sys.argv[2])\n    suffix = source.suffix.lower()\n    payload = source.read_bytes() if suffix in {".xls", ".xlsx", ".doc", ".docx", ".ppt", ".pptx"} else read_fn(source)\n    do_parse(str(out), [source.stem], [payload], ["ch"], backend="pipeline", f_dump_md=True, f_dump_middle_json=False, f_dump_model_output=False, f_dump_orig_pdf=False, f_dump_content_list=False, f_draw_layout_bbox=False, f_draw_span_bbox=False, client_side_output_generation=False)\n\nif __name__ == "__main__":\n    main()\n', encoding="utf-8")
        try:
            process = subprocess.Popen(
                [str(self.python), str(script), str(source), str(work / "output")],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                encoding="utf-8", errors="replace",
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
