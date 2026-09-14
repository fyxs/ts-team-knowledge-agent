import subprocess
from pathlib import Path

from ts_knowledge_agent.adapters.git_sync import sync_repository


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    )
    return result.stdout.strip()


def _make_remote(tmp_path: Path) -> Path:
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(bare)], capture_output=True, check=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", str(bare), str(seed)], capture_output=True, check=True)
    (seed / "README.md").write_text("# kb\n", encoding="utf-8")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-m", "init")
    _git(seed, "push", "origin", "main")
    return bare


def _clone(bare: Path, dest: Path) -> Path:
    subprocess.run(["git", "clone", str(bare), str(dest)], capture_output=True, check=True)
    return dest


def _write_member(repo: Path, name: str, body: str) -> None:
    target = repo / "members" / "whm"
    target.mkdir(parents=True, exist_ok=True)
    (target / name).write_text(body, encoding="utf-8")


def test_sync_pushes_new_member_content(tmp_path):
    bare = _make_remote(tmp_path)
    work = _clone(bare, tmp_path / "work")
    _write_member(work, "note.md", "# note\n")

    result = sync_repository(work, "sync knowledge")

    assert result.status == "pushed"
    remote_log = subprocess.run(
        ["git", "--git-dir", str(bare), "log", "--oneline", "main"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout
    assert "sync knowledge" in remote_log


def test_sync_reports_clean_without_changes(tmp_path):
    bare = _make_remote(tmp_path)
    work = _clone(bare, tmp_path / "work")
    assert sync_repository(work, "noop").status == "clean"


def test_sync_rebases_when_remote_moved_ahead(tmp_path):
    bare = _make_remote(tmp_path)
    first = _clone(bare, tmp_path / "first")
    second = _clone(bare, tmp_path / "second")

    _write_member(first, "remote.md", "# remote\n")
    _git(first, "add", "-A")
    _git(first, "commit", "-m", "remote change")
    _git(first, "push", "origin", "main")

    _write_member(second, "local.md", "# local\n")
    result = sync_repository(second, "local change")

    assert result.status == "pushed"
    history = _git(second, "log", "--oneline")
    assert "remote change" in history
    assert "local change" in history


def test_sync_blocks_on_conflict(tmp_path):
    bare = _make_remote(tmp_path)
    first = _clone(bare, tmp_path / "first")
    second = _clone(bare, tmp_path / "second")

    _write_member(first, "same.md", "# from first\n")
    _git(first, "add", "-A")
    _git(first, "commit", "-m", "first change")
    _git(first, "push", "origin", "main")

    _write_member(second, "same.md", "# from second\n")
    result = sync_repository(second, "second change")

    assert result.status == "blocked_conflict"
