from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


def find_markdown(root: Path) -> Path:
    files = sorted(root.rglob("*.md"))
    if len(files) != 1:
        raise RuntimeError(f"expected exactly one MinerU markdown output, found {len(files)}")
    return files[0]


class MinerUConverter:
    def __init__(self, python: str | Path | None):
        if not python:
            raise ValueError("MinerU Python interpreter must be configured explicitly")
        self.python = Path(python)
        if not self.python.is_file():
            raise FileNotFoundError(f"MinerU Python interpreter does not exist: {self.python}")

    def convert_to(self, source: Path, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="mineru-") as temp:
            work = Path(temp)
            self._run(source, work)
            markdown = find_markdown(work / "output")
            shutil.copy2(markdown, output)
            images = markdown.parent / "images"
            if images.is_dir():
                shutil.copytree(images, output.parent / "images", dirs_exist_ok=True)

    def _run(self, source: Path, work: Path) -> None:
        script = work / "run.py"
        script.write_text(
            "from pathlib import Path\n"
            "from mineru.cli.common import do_parse, read_fn\n"
            "import sys\n"
            "source=Path(sys.argv[1])\n"
            "out=Path(sys.argv[2])\n"
            "suffix=source.suffix.lower()\n"
            "if suffix in {'.xls', '.xlsx', '.doc', '.docx', '.ppt', '.pptx'}:\n"
            "    do_parse(str(out), [source.stem], [source.read_bytes()], ['ch'], backend='pipeline', f_dump_md=True, f_dump_middle_json=False, f_dump_model_output=False, f_dump_orig_pdf=False, f_dump_content_list=False, f_draw_layout_bbox=False, f_draw_span_bbox=False, client_side_output_generation=False)\n"
            "else:\n"
            "    do_parse(str(out), [source.stem], [read_fn(source)], ['ch'], backend='pipeline', f_dump_md=True, f_dump_middle_json=False, f_dump_model_output=False, f_dump_orig_pdf=False, f_dump_content_list=False, f_draw_layout_bbox=False, f_draw_span_bbox=False, client_side_output_generation=False)\n",
            encoding="utf-8",
        )
        result = subprocess.run([str(self.python), str(script), str(source), str(work / "output")], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        if result.returncode:
            details = (result.stderr or result.stdout)[-4000:]
            raise RuntimeError("MinerU failed: " + details)