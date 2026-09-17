"""单独执行 convert 命令时必须把配置里的 MinerU 解释器传给转换器。

回归背景：曾漏传 mineru_python，扫描流水线正常但单独转换必报
「MinerU Python interpreter must be configured explicitly」。
"""

from pathlib import Path
from types import SimpleNamespace

import importlib

from ts_knowledge_agent.config import Settings

# 注意：ts_knowledge_agent.cli 导出的是 main 函数，这里需要的是 cli.main 子模块
cli_main = importlib.import_module("ts_knowledge_agent.cli.main")


def _settings(tmp_path: Path, mineru: Path | None) -> Settings:
    return Settings(
        working_directory=tmp_path,
        shared_source_directory=tmp_path / "source",
        shared_knowledge_repository_directory=tmp_path / "knowledge-base",
        shared_knowledge_repository_url="git@example.invalid:kb.git",
        personal_workspace="tester",
        mineru_python=mineru,
    )


def test_convert_passes_configured_mineru_interpreter(tmp_path, monkeypatch):
    interpreter = tmp_path / "python.exe"
    interpreter.write_bytes(b"x")
    source = tmp_path / "report.pdf"
    source.write_bytes(b"%PDF-1.4")
    captured = {}

    def fake_convert(source_path, output_path, converter=None, mineru_python=None):
        captured["mineru_python"] = mineru_python
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("# ok", encoding="utf-8")
        return SimpleNamespace(output_path=output_path, bytes_written=4)

    monkeypatch.setattr(cli_main, "convert_file", fake_convert)
    monkeypatch.setattr(cli_main.Settings, "from_env", classmethod(lambda cls: _settings(tmp_path, interpreter)))

    code = cli_main.main(["convert", "--file", str(source), "--output", str(tmp_path / "out.md")])

    assert code == 0
    assert captured["mineru_python"] == interpreter


def test_convert_without_mineru_explains_what_to_do(tmp_path, monkeypatch, capsys):
    source = tmp_path / "report.pdf"
    source.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(cli_main.Settings, "from_env", classmethod(lambda cls: _settings(tmp_path, None)))

    code = cli_main.main(["convert", "--file", str(source), "--output", str(tmp_path / "out.md")])

    assert code == 1
    assert "setup-mineru" in capsys.readouterr().out
