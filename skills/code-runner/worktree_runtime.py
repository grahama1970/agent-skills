"""Disposable git worktree support for code-runner.

This module is intentionally dependency-light and avoids ``@dataclass``.  Some
callers load plugin modules with ``importlib.util.module_from_spec`` without
first registering the module in ``sys.modules``; Python's dataclasses module can
crash in that situation while resolving annotations.  The small value objects
below are plain classes for that reason.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from types import TracebackType
from typing import Iterable


DEFAULT_WORKTREE_ROOT = Path(tempfile.gettempdir()) / "code-runner-worktrees"


class WorktreeRuntimeError(RuntimeError):
    """Raised when a disposable worktree cannot be created or cleaned up."""


class WorktreeInfo:
    """Description of a disposable git worktree."""

    def __init__(
        self,
        path: Path,
        branch: str,
        base_ref: str,
        repo_root: Path,
        base_commit: str | None = None,
    ) -> None:
        self.path = path.resolve()
        self.branch = branch
        self.base_ref = base_ref
        self.base_commit = base_commit or base_ref
        self.repo_root = repo_root.resolve()

    def __repr__(self) -> str:
        return (
            "WorktreeInfo("
            f"path={self.path!r}, branch={self.branch!r}, "
            f"base_ref={self.base_ref!r}, base_commit={self.base_commit!r}, "
            f"repo_root={self.repo_root!r})"
        )


def _run_git(args: list[str], cwd: Path, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the completed process."""

    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(cwd), text=True, capture_output=True, timeout=timeout
        )
    except FileNotFoundError as exc:
        raise WorktreeRuntimeError("git executable was not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise WorktreeRuntimeError(f"git {' '.join(args)} timed out in {cwd}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise WorktreeRuntimeError(f"git {' '.join(args)} failed in {cwd}: {detail}")
    return proc


def repo_root(cwd: str | Path = ".") -> Path:
    """Return the canonical top-level git repository path for ``cwd``.

    Raises ``WorktreeRuntimeError`` with a clear message if ``cwd`` does not
    exist or is not inside a git repository.
    """

    path = Path(cwd).expanduser().resolve()
    if not path.exists():
        raise WorktreeRuntimeError(f"cwd does not exist: {path}")
    try:
        proc = _run_git(["rev-parse", "--show-toplevel"], path)
    except WorktreeRuntimeError as exc:
        raise WorktreeRuntimeError(f"cwd is not inside a git repository: {path}") from exc
    output = proc.stdout.strip()
    if not output:
        raise WorktreeRuntimeError(f"cwd is not inside a git repository: {path}")
    return Path(output).resolve()


def _safe_slug(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in value.strip())
    cleaned = cleaned.strip(".-")
    return cleaned or "run"


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolve_under_repo(root: Path, value: str | Path, *, kind: str, must_exist: bool) -> Path:
    """Resolve ``value`` against ``root`` and reject escapes.

    Existing paths are resolved normally so symlinks cannot point outside the
    repository.  Non-existing paths are resolved as far as possible with
    ``strict=False`` so ``..`` segments are still canonicalized before the
    containment check.
    """

    canonical_root = root.expanduser().resolve()
    raw = Path(value).expanduser()
    candidate = raw if raw.is_absolute() else canonical_root / raw
    if must_exist and not candidate.exists():
        raise WorktreeRuntimeError(f"{kind} does not exist: {value}")
    try:
        resolved = candidate.resolve(strict=must_exist)
    except FileNotFoundError:
        raise WorktreeRuntimeError(f"{kind} does not exist: {value}")
    if not _is_relative_to(resolved, canonical_root):
        raise WorktreeRuntimeError(f"{kind} escapes repository root: {value}")
    return resolved


def _relative_repo_path(root: Path, value: str | Path, *, kind: str) -> str:
    canonical_root = root.expanduser().resolve()
    resolved = _resolve_under_repo(canonical_root, value, kind=kind, must_exist=False)
    return resolved.relative_to(canonical_root).as_posix()


def _default_parent_for(task_id: str) -> Path:
    # Keep disposable checkouts under /tmp/code-runner-worktrees/<session-or-task-id>/.
    return (DEFAULT_WORKTREE_ROOT / _safe_slug(task_id)).resolve()


def restore_patch_base_tree(info: WorktreeInfo) -> None:
    """Restore the disposable worktree to its original checkout baseline."""

    _run_git(["reset", "--hard", info.base_commit], info.path, timeout=60)
    _run_git(["clean", "-fd"], info.path, timeout=60)


def changed_path_statuses(info: WorktreeInfo) -> list[tuple[str, str]]:
    """Return git porcelain status and path pairs in the disposable worktree."""

    proc = _run_git(["status", "--porcelain=v1", "-z", "--untracked-files=all"], info.path, timeout=60)
    entries: list[tuple[str, str]] = []
    records = [record for record in proc.stdout.split("\0") if record]
    index = 0
    while index < len(records):
        record = records[index]
        status = record[:2]
        path = record[3:] if len(record) > 3 else ""
        if status.startswith("R") or status.endswith("R"):
            index += 1
            if index < len(records):
                path = records[index]
        if path:
            entries.append((status, path))
        index += 1
    return sorted(set(entries), key=lambda item: item[1])


def changed_paths(info: WorktreeInfo) -> list[str]:
    """Return all changed paths in the disposable worktree."""

    return sorted({path for _status, path in changed_path_statuses(info)})


def remove_untracked_paths(info: WorktreeInfo, paths: Iterable[str]) -> None:
    """Remove selected untracked paths from the disposable worktree."""

    selected = sorted({path for path in paths if path and not Path(path).is_absolute() and ".." not in Path(path).parts})
    if selected:
        _run_git(["clean", "-fd", "--", *selected], info.path, timeout=60)


def paths_within_allowlist(paths: Iterable[str], allowlist_paths: Iterable[str | Path]) -> tuple[bool, list[str]]:
    """Return whether changed paths are fully covered by the allowlist."""

    allowed = [str(path).rstrip("/") for path in allowlist_paths]
    violations: list[str] = []
    for path in paths:
        if not any(path == item or path.startswith(f"{item}/") for item in allowed):
            violations.append(path)
    return not violations, violations


def dirty_paths_for_allowlist(cwd: str | Path, allowlist_paths: Iterable[str | Path]) -> list[str]:
    """Return source worktree dirty paths that overlap the write allowlist."""

    root = repo_root(cwd)
    rel_paths = [_relative_repo_path(root, path, kind="allowlist path") for path in allowlist_paths]
    if not rel_paths:
        return []
    proc = _run_git(
        ["status", "--porcelain=v1", "-z", "--untracked-files=all", "--", *rel_paths],
        root,
        timeout=60,
    )
    dirty: list[str] = []
    records = [record for record in proc.stdout.split("\0") if record]
    index = 0
    while index < len(records):
        record = records[index]
        status = record[:2]
        path = record[3:] if len(record) > 3 else ""
        if status.startswith("R") or status.endswith("R"):
            index += 1
            if index < len(records):
                path = records[index]
        if path:
            dirty.append(path)
        index += 1
    return dirty


def export_allowlist_patch(
    info: WorktreeInfo,
    allowlist_paths: Iterable[str | Path],
    output_patch: str | Path,
) -> Path:
    """Export a patch containing only changes under ``allowlist_paths``.

    Allowlist paths are canonicalized against the disposable worktree and must
    stay inside it.  The output patch may live outside the repo (for example in a
    durable output_dir) and is never removed by worktree cleanup.
    """

    rel_paths = [_relative_repo_path(info.path, path, kind="allowlist path") for path in allowlist_paths]
    if not rel_paths:
        raise WorktreeRuntimeError("cannot export allowlist patch with an empty allowlist")
    destination = Path(output_patch).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    existing_rel_paths = [path for path in rel_paths if (info.path / path).exists()]
    if existing_rel_paths:
        _run_git(["add", "-N", "--", *existing_rel_paths], info.path, timeout=60)
    proc = _run_git(["diff", "--", *rel_paths], info.path, timeout=60)
    destination.write_text(proc.stdout)
    return destination


def create_disposable_worktree(
    cwd: str | Path = ".",
    *,
    task_id: str = "code-runner",
    base_ref: str = "HEAD",
    parent_dir: str | Path | None = None,
) -> WorktreeInfo:
    """Create an isolated git worktree on a new temporary branch.

    By default, worktrees are created below
    ``/tmp/code-runner-worktrees/<task_id>/`` from the source repo ``HEAD``.
    """

    root = repo_root(cwd)
    slug = _safe_slug(task_id)
    unique = uuid.uuid4().hex[:10]
    branch = f"code-runner/{slug}-{unique}"
    parent = (Path(parent_dir).expanduser() if parent_dir is not None else _default_parent_for(task_id)).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    path = (parent / f"worktree-{unique}").resolve()

    try:
        _run_git(["worktree", "add", "-b", branch, str(path), base_ref], root, timeout=60)
        info = WorktreeInfo(path=path, branch=branch, base_ref=base_ref, repo_root=root)
    except Exception:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        try:
            _run_git(["worktree", "prune"], root, timeout=60)
        except WorktreeRuntimeError:
            pass
        raise

    return info


def remove_disposable_worktree(info: WorktreeInfo, *, force: bool = True) -> None:
    """Remove a disposable worktree and its temporary branch."""

    remove_args = ["worktree", "remove"]
    if force:
        remove_args.append("--force")
    remove_args.append(str(info.path))

    if info.path.exists():
        try:
            _run_git(remove_args, info.repo_root, timeout=60)
        except WorktreeRuntimeError:
            shutil.rmtree(info.path, ignore_errors=True)
            _run_git(["worktree", "prune"], info.repo_root, timeout=60)
            if info.path.exists():
                raise
    else:
        _run_git(["worktree", "prune"], info.repo_root, timeout=60)

    delete_args = ["branch", "-D" if force else "-d", info.branch]
    proc = subprocess.run(
        ["git", *delete_args], cwd=str(info.repo_root), text=True, capture_output=True, timeout=30
    )
    if proc.returncode != 0 and "not found" not in (proc.stderr + proc.stdout).lower():
        detail = (proc.stderr or proc.stdout or "").strip()
        raise WorktreeRuntimeError(f"git {' '.join(delete_args)} failed in {info.repo_root}: {detail}")


def prune_stale_worktrees(
    cwd: str | Path = ".",
    *,
    root_dir: str | Path = DEFAULT_WORKTREE_ROOT,
    max_age_seconds: int = 24 * 60 * 60,
) -> list[Path]:
    """Prune stale /tmp worktrees and git worktree metadata."""

    git_root = repo_root(cwd)
    root = Path(root_dir).expanduser().resolve()
    removed: list[Path] = []
    now = time.time()
    if root.exists():
        for child in root.iterdir():
            if not child.is_dir():
                continue
            resolved = child.resolve()
            if not _is_relative_to(resolved, root):
                continue
            try:
                age = now - resolved.stat().st_mtime
            except OSError:
                continue
            if age >= max_age_seconds:
                shutil.rmtree(resolved, ignore_errors=True)
                if not resolved.exists():
                    removed.append(resolved)
    _run_git(["worktree", "prune"], git_root, timeout=60)
    return removed


prune_disposable_worktrees = prune_stale_worktrees


class DisposableWorktreeRuntime:
    """Context manager that owns a temporary git worktree."""

    def __init__(
        self,
        cwd: str | Path = ".",
        *,
        task_id: str = "code-runner",
        base_ref: str = "HEAD",
        parent_dir: str | Path | None = None,
        allowlist_paths: Iterable[str | Path] | None = None,
        export_patch_path: str | Path | None = None,
    ) -> None:
        self.cwd = Path(cwd)
        self.task_id = task_id
        self.base_ref = base_ref
        self.parent_dir = Path(parent_dir) if parent_dir is not None else None
        self.allowlist_paths = list(allowlist_paths or [])
        self.export_patch_path = Path(export_patch_path) if export_patch_path is not None else None
        self.info: WorktreeInfo | None = None
        self.exported_patch: Path | None = None

    @property
    def path(self) -> Path:
        if self.info is None:
            raise WorktreeRuntimeError("worktree has not been created yet")
        return self.info.path

    @property
    def branch(self) -> str:
        if self.info is None:
            raise WorktreeRuntimeError("worktree has not been created yet")
        return self.info.branch

    def __enter__(self) -> "DisposableWorktreeRuntime":
        self.info = create_disposable_worktree(
            self.cwd,
            task_id=self.task_id,
            base_ref=self.base_ref,
            parent_dir=self.parent_dir,
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        try:
            if exc_type is None and self.export_patch_path is not None:
                self.export_patch(self.export_patch_path, self.allowlist_paths)
        finally:
            self.cleanup()
        return False

    def export_patch(
        self,
        output_patch: str | Path,
        allowlist_paths: Iterable[str | Path] | None = None,
    ) -> Path:
        if self.info is None:
            raise WorktreeRuntimeError("worktree has not been created yet")
        paths = list(self.allowlist_paths if allowlist_paths is None else allowlist_paths)
        self.exported_patch = export_allowlist_patch(self.info, paths, output_patch)
        return self.exported_patch

    def cleanup(self) -> None:
        if self.info is not None:
            remove_disposable_worktree(self.info)
            self.info = None


def disposable_worktree(
    cwd: str | Path = ".",
    *,
    task_id: str = "code-runner",
    base_ref: str = "HEAD",
    parent_dir: str | Path | None = None,
    allowlist_paths: Iterable[str | Path] | None = None,
    export_patch_path: str | Path | None = None,
) -> DisposableWorktreeRuntime:
    """Return a context manager for a disposable git worktree."""

    return DisposableWorktreeRuntime(
        cwd,
        task_id=task_id,
        base_ref=base_ref,
        parent_dir=parent_dir,
        allowlist_paths=allowlist_paths,
        export_patch_path=export_patch_path,
    )
