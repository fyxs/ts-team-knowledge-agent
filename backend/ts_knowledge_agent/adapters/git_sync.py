from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SyncResult:
    status: str
    commit: str | None = None
    message: str | None = None


class GitSyncError(RuntimeError):
    pass


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    if result.returncode:
        raise GitSyncError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def prepare_repository(repo: Path) -> SyncResult:
    """Update a clean local clone before the pipeline writes into it."""
    repo = repo.expanduser().resolve()
    if not (repo / ".git").exists():
        return SyncResult("not_initialized", message=str(repo))
    if _git(repo, "status", "--porcelain"):
        return SyncResult("blocked_dirty_worktree")
    _git(repo, "fetch", "origin")
    branch = _git(repo, "branch", "--show-current") or "main"
    try:
        _git(repo, "merge", "--ff-only", f"origin/{branch}")
    except GitSyncError as exc:
        return SyncResult("blocked_conflict", message=str(exc))
    return SyncResult("ready")


def commit_and_push(repo: Path, message: str) -> SyncResult:
    repo = repo.expanduser().resolve()
    if not (repo / ".git").exists():
        return SyncResult("not_initialized", message=str(repo))
    if not _git(repo, "status", "--porcelain"):
        return SyncResult("clean")
    _git(repo, "add", "members")
    if not _git(repo, "diff", "--cached", "--name-only"):
        return SyncResult("clean")
    _git(repo, "commit", "-m", message)
    commit = _git(repo, "rev-parse", "HEAD")
    try:
        _git(repo, "push", "origin", "HEAD")
    except GitSyncError as exc:
        return SyncResult("push_failed", commit=commit, message=str(exc))
    return SyncResult("pushed", commit=commit)

def sync_repository(repo: Path, message: str) -> SyncResult:
    """Commit local member knowledge, rebase on remote changes and push.

    Returns explicit statuses so callers can report without guessing:
    pushed, clean, not_initialized, blocked_conflict, push_failed.
    """
    repo = repo.expanduser().resolve()
    if not (repo / ".git").exists():
        return SyncResult("not_initialized", message=str(repo))
    try:
        if _git(repo, "status", "--porcelain"):
            _git(repo, "add", "members")
            if _git(repo, "diff", "--cached", "--name-only"):
                _git(repo, "commit", "-m", message)
        _git(repo, "fetch", "origin")
    except GitSyncError as exc:
        return SyncResult("push_failed", message=str(exc))

    branch = _git(repo, "branch", "--show-current") or "main"
    try:
        behind = _git(repo, "rev-list", "--count", f"HEAD..origin/{branch}")
    except GitSyncError:
        behind = "0"
    if behind != "0":
        try:
            _git(repo, "rebase", f"origin/{branch}")
        except GitSyncError as exc:
            try:
                _git(repo, "rebase", "--abort")
            except GitSyncError:
                pass
            return SyncResult("blocked_conflict", message=str(exc))

    try:
        ahead = _git(repo, "rev-list", "--count", f"origin/{branch}..HEAD")
    except GitSyncError:
        ahead = "1"
    commit = _git(repo, "rev-parse", "HEAD")
    if ahead == "0":
        return SyncResult("clean", commit=commit)
    try:
        _git(repo, "push", "origin", f"HEAD:refs/heads/{branch}")
    except GitSyncError as exc:
        return SyncResult("push_failed", commit=commit, message=str(exc))
    return SyncResult("pushed", commit=commit)


def pull_repository(repo: Path) -> SyncResult:
    """手动拉取共享知识仓：工作区干净时 fetch，落后则 rebase。"""
    repo = repo.expanduser().resolve()
    if not (repo / ".git").exists():
        return SyncResult("not_initialized", message=str(repo))
    if _git(repo, "status", "--porcelain"):
        return SyncResult("blocked_dirty_worktree", message="local changes must be pushed or reverted first")
    try:
        _git(repo, "fetch", "origin")
    except GitSyncError as exc:
        return SyncResult("pull_failed", message=str(exc))
    branch = _git(repo, "branch", "--show-current") or "main"
    try:
        behind = _git(repo, "rev-list", "--count", f"HEAD..origin/{branch}")
    except GitSyncError:
        behind = "0"
    if behind == "0":
        return SyncResult("up_to_date", commit=_git(repo, "rev-parse", "HEAD"))
    try:
        _git(repo, "rebase", f"origin/{branch}")
    except GitSyncError as exc:
        try:
            _git(repo, "rebase", "--abort")
        except GitSyncError:
            pass
        return SyncResult("blocked_conflict", message=str(exc))
    return SyncResult("pulled", commit=_git(repo, "rev-parse", "HEAD"))


def push_repository(repo: Path, message: str = "Manual sync from the web console") -> SyncResult:
    """手动推送：提交本地成员内容后推送；远端有新提交时先 rebase。"""
    return sync_repository(repo, message)
