"""Disposable git worktree and source-apply helpers.

The normal runner path edits only a temporary worktree. Source apply is a small
explicit compatibility path for historical complete-task specs.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Iterable


class WorktreeError(RuntimeError):
    """Raised when git worktree operations fail."""


class Worktree:
    """Disposable worktree descriptor."""

    def __init__(self, path: Path, branch: str, repo: Path, base_head: str) -> None:
        self.path = path
        self.branch = branch
        self.repo = repo
        self.base_head = base_head


def run_git(cwd: str | Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run git in cwd."""

    proc = subprocess.run(["git", *args], cwd=Path(cwd), text=True, capture_output=True, timeout=120)
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise WorktreeError(f"git {' '.join(args)} failed in {cwd}: {detail}")
    return proc


def repo_root(cwd: str | Path) -> Path:
    """Return git top-level directory."""

    return Path(run_git(cwd, "rev-parse", "--show-toplevel").stdout.strip()).resolve()


def head(cwd: str | Path) -> str:
    """Return HEAD SHA."""

    return run_git(cwd, "rev-parse", "HEAD").stdout.strip()


def status(cwd: str | Path) -> list[str]:
    """Return porcelain status lines."""

    return run_git(cwd, "status", "--porcelain=v1", "--untracked-files=all").stdout.splitlines()


def safe_slug(value: str) -> str:
    """Create a branch-safe slug."""

    slug = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in value).strip(".-")
    return slug or "task"


def create(cwd: str | Path, task_id: str) -> Worktree:
    """Create a disposable worktree from HEAD."""

    repo = repo_root(cwd)
    base = head(repo)
    unique = uuid.uuid4().hex[:10]
    branch = f"code-runner/{safe_slug(task_id)}-{unique}"
    parent = Path(tempfile.gettempdir()) / "code-runner-worktrees" / safe_slug(task_id)
    parent.mkdir(parents=True, exist_ok=True)
    path = (parent / f"worktree-{unique}").resolve()
    try:
        run_git(repo, "worktree", "add", "-b", branch, str(path), base)
    except Exception:
        shutil.rmtree(path, ignore_errors=True)
        raise
    return Worktree(path, branch, repo, base)


def mirror_dependency_dirs(source: str | Path, destination: str | Path) -> list[str]:
    """Symlink heavyweight dependency dirs into the disposable worktree."""

    source_root = Path(source)
    dest_root = Path(destination)
    mirrored: list[str] = []
    for name in ("node_modules", ".venv"):
        src = source_root / name
        dst = dest_root / name
        if not src.exists() or dst.exists():
            continue
        dst.symlink_to(src, target_is_directory=src.is_dir())
        mirrored.append(name)
    return mirrored


def remove(worktree: Worktree) -> bool:
    """Remove worktree and branch."""

    if worktree.path.exists():
        proc = run_git(worktree.repo, "worktree", "remove", "--force", str(worktree.path), check=False)
        if proc.returncode != 0:
            shutil.rmtree(worktree.path, ignore_errors=True)
            run_git(worktree.repo, "worktree", "prune", check=False)
    run_git(worktree.repo, "branch", "-D", worktree.branch, check=False)
    return not worktree.path.exists()


def changed_paths(cwd: str | Path) -> list[str]:
    """Return changed paths from git status."""

    paths: list[str] = []
    for line in status(cwd):
        if len(line) >= 4:
            paths.append(line[3:])
    return sorted(set(paths))


def path_allowed(path: str, allowlist: Iterable[str]) -> bool:
    """Return true if path is under allowlist."""

    clean = path.rstrip("/")
    return any(clean == item.rstrip("/") or clean.startswith(f"{item.rstrip('/')}/") for item in allowlist)


def all_allowed(paths: Iterable[str], allowlist: Iterable[str]) -> tuple[bool, list[str]]:
    """Validate changed paths against allowlist."""

    violations = [path for path in paths if not path_allowed(path, allowlist)]
    return not violations, violations


def dirty_paths_for_allowlist(cwd: str | Path, allowlist: Iterable[str]) -> list[str]:
    """Return dirty source paths that overlap the allowlist."""

    return [path for path in changed_paths(cwd) if path_allowed(path, allowlist)]


def export_patch(cwd: str | Path, allowlist: list[str], destination: str | Path) -> Path:
    """Export allowlist-scoped patch."""

    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    existing = [path for path in allowlist if (Path(cwd) / path).exists()]
    if existing:
        run_git(cwd, "add", "-N", "--", *existing, check=False)
    proc = run_git(cwd, "diff", "--", *allowlist)
    dest.write_text(proc.stdout)
    return dest


def apply_patch(cwd: str | Path, patch_file: str | Path) -> None:
    """Apply a patch to cwd."""

    if Path(patch_file).read_text().strip():
        run_git(cwd, "apply", "--whitespace=nowarn", str(Path(patch_file).resolve()))


def commit_allowlist(cwd: str | Path, allowlist: list[str], message: str) -> str:
    """Commit only allowlisted paths."""

    run_git(cwd, "add", "--", *allowlist)
    staged = [
        line.split("\t")[-1]
        for line in run_git(cwd, "diff", "--cached", "--name-status").stdout.splitlines()
        if line
    ]
    bad = [path for path in staged if not path_allowed(path, allowlist)]
    if bad:
        raise WorktreeError(f"staged paths outside allowlist: {', '.join(bad)}")
    if not staged:
        return ""
    run_git(cwd, "commit", "-m", message)
    return head(cwd)


def restore_allowlist(cwd: str | Path, allowlist: list[str]) -> None:
    """Restore allowlisted paths after a failed source apply."""

    run_git(cwd, "restore", "--staged", "--", *allowlist, check=False)
    for path in allowlist:
        tracked = run_git(cwd, "ls-tree", "-r", "--name-only", "HEAD", "--", path, check=False)
        if tracked.stdout.strip():
            run_git(cwd, "restore", "--source=HEAD", "--worktree", "--", path, check=False)
        else:
            run_git(cwd, "clean", "-fd", "--", path, check=False)
