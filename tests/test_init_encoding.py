from __future__ import annotations


def test_init_reports_encoding_problem_without_misleading_exit(monkeypatch, tmp_path, capsys):
    """读文件时的 UnicodeDecodeError 曾被当成业务错误：初始化其实成功，退出码却是 2。

    这里锁住正确行为：报明文告警、继续完成初始化、退出码为 0。
    """
    # 注意：ts_knowledge_agent.cli 包重导出了函数 main，"import ...cli.main as x" 拿到的是函数而不是模块，必须用 import_module。
    from importlib import import_module

    cli_main = import_module("ts_knowledge_agent.cli.main")

    def boom(settings):
        raise UnicodeDecodeError("utf-8", b"\xa3", 22, 23, "invalid start byte")

    monkeypatch.setattr(cli_main, "initialize_working_directory", boom)
    monkeypatch.setattr(
        cli_main, "ensure_member_space",
        lambda *args, **kwargs: {"knowledge": "k", "governance": "g"},
    )

    code = cli_main.main([
        "init",
        "--working-directory", str(tmp_path),
        "--personal-workspace", "whm",
        "--shared-source-directory", str(tmp_path / "src"),
        "--skip-model-setup",
        "--skip-scheduled-tasks",
    ])

    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err
    assert "UTF-8" in captured.out
    assert "usage:" not in captured.out
