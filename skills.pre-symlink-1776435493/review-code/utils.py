"""Common utility functions for code-review skill.

Contains:
- Path formatting helpers
- List formatting helpers
- Git context gathering
- Workspace creation
"""
from __future__ import annotations

import re
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from rich.console import Console

# Handle both import modes
try:
    from .config import SCRIPT_DIR, get_timeout
except ImportError:
    from config import SCRIPT_DIR, get_timeout

# Rich console for styled output
console = Console(stderr=True)


def format_paths(paths: list[str]) -> str:
    """Format paths as markdown list."""
    if not paths:
        return "  - (to be determined)"
    return "\n".join(f"  - `{p}`" for p in paths)


def format_numbered_list(items: list[str], prefix: str = "") -> str:
    """Format items as numbered markdown sections."""
    if not items:
        return "1. (to be specified)"
    result = []
    for i, item in enumerate(items, 1):
        result.append(f"### {i}. {prefix}{item.split(':')[0] if ':' in item else item}\n\n{item}")
    return "\n\n".join(result)


def format_bullet_list(items: list[str]) -> str:
    """Format items as bullet list."""
    if not items:
        return "- (to be specified)"
    return "\n".join(f"- {item}" for item in items)


def format_numbered_steps(items: list[str]) -> str:
    """Format items as numbered steps."""
    if not items:
        return "1. (to be specified)"
    return "\n".join(f"{i}. {item}" for i, item in enumerate(items, 1))


def get_effective_dirs(add_dir: Optional[list[str]], workspace: Optional[list[str]]) -> Optional[list[str]]:
    """Determine effective directories, defaulting to "." if none provided.

    If workspace is provided, this function returns None, as workspace handling
    will create a temporary directory and pass it later.
    """
    if workspace:
        # workspace is handled by a context manager that calls this later
        return None

    dirs = add_dir or []
    if not dirs:
        # Default to current directory if no directories or workspace provided
        dirs = ["."]

    # Safety Check: Warn if we are reviewing the skill's own directory
    skill_dir = SCRIPT_DIR
    cwd = Path.cwd().resolve()

    if cwd == skill_dir and "." in dirs:
        console.print("[yellow]Warning: You are running code-review from the skill's own directory.[/yellow]")
        console.print("[yellow]If this is not intentional, it may result in the skill reviewing its own source code.[/yellow]")
        console.print("[yellow]To review a different project, cd into that project's directory first.[/yellow]\n")

    return dirs


# Directories excluded from workspace copies — these are large, rebuildable,
# and have caused 1TB+ /tmp bloat incidents (2026-03-04, 2026-03-05).
_WORKSPACE_EXCLUDE_DIRS = {
    ".git", ".venv", "node_modules", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "models", ".tox", ".eggs",
    "dist", "build", ".next", ".nuxt", ".turbo",
}

# Max total workspace size in bytes (10GB). Aborts copy if exceeded.
_WORKSPACE_MAX_BYTES = 10 * 1024 * 1024 * 1024


def _copytree_filtered(src: Path, dest: Path, size_counter: list[int]) -> None:
    """Copy directory tree excluding large rebuildable dirs and tracking size."""
    dest.mkdir(parents=True, exist_ok=True)
    for entry in os.scandir(src):
        if entry.name in _WORKSPACE_EXCLUDE_DIRS:
            continue
        target = dest / entry.name
        if entry.is_dir(follow_symlinks=False):
            _copytree_filtered(Path(entry.path), target, size_counter)
        elif entry.is_file(follow_symlinks=False):
            size_counter[0] += entry.stat().st_size
            if size_counter[0] > _WORKSPACE_MAX_BYTES:
                raise RuntimeError(
                    f"Workspace exceeded {_WORKSPACE_MAX_BYTES // (1024**3)}GB limit — aborting copy"
                )
            shutil.copy2(entry.path, target)


@contextmanager
def create_workspace(paths: list[Path], base_dir: Optional[Path] = None) -> Generator[Path, None, None]:
    """Create a temporary workspace with copies of specified paths.

    Copies files/directories to a temp location so providers can access
    uncommitted local files without requiring git commits.

    Excludes .git, .venv, node_modules, models, and other large rebuildable
    directories to prevent /tmp bloat. Aborts if total size exceeds 10GB.

    Args:
        paths: List of file/directory paths to copy
        base_dir: Base directory for relative path preservation (default: cwd)

    Yields:
        Path to the temporary workspace directory

    Example:
        with create_workspace([Path("src/"), Path("tests/")]) as workspace:
            # workspace contains copies of src/ and tests/
            run_provider(add_dir=workspace)
        # workspace is automatically cleaned up
    """
    base = base_dir or Path.cwd()
    workspace = Path(tempfile.mkdtemp(prefix="code-review-workspace-"))
    size_counter = [0]  # mutable counter for nested tracking

    try:
        console.print(f"[dim]Creating workspace: {workspace}[/dim]")
        for path in paths:
            path = Path(path).resolve()  # Resolve to absolute path first
            if not path.exists():
                console.print(f"[yellow]Warning: Path not found, skipping: {path}[/yellow]")
                continue

            # Preserve relative path structure
            try:
                rel_path = path.relative_to(base.resolve())
            except ValueError:
                # Out-of-tree path: use sanitized absolute path to avoid collisions
                # e.g., /home/user/foo.py -> _external/home/user/foo.py
                sanitized = str(path).lstrip("/").replace("/", "_")
                rel_path = Path("_external") / sanitized
                console.print(f"[yellow]Note: {path} is outside workspace base, using {rel_path}[/yellow]")

            dest = workspace / rel_path

            if path.is_dir():
                _copytree_filtered(path, dest, size_counter)
                size_mb = size_counter[0] / (1024 * 1024)
                console.print(f"[dim]  Copied dir: {path} -> {dest} ({size_mb:.0f}MB cumulative)[/dim]")
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)
                console.print(f"[dim]  Copied file: {path} -> {dest}[/dim]")

        yield workspace

    finally:
        # Cleanup
        console.print(f"[dim]Cleaning up workspace: {workspace}[/dim]")
        shutil.rmtree(workspace, ignore_errors=True)


def check_git_status(repo_dir: Optional[Path] = None) -> dict:
    """Check git status for uncommitted/unpushed changes."""
    cwd = str(repo_dir) if repo_dir else None
    result = {
        "has_uncommitted": False,
        "has_unpushed": False,
        "current_branch": None,
        "remote_branch": None,
    }

    try:
        # Get current branch
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, cwd=cwd, timeout=get_timeout()
        )
        if branch_result.returncode == 0:
            result["current_branch"] = branch_result.stdout.strip()

        # Check for uncommitted changes
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=cwd, timeout=get_timeout()
        )
        if status_result.returncode == 0 and status_result.stdout.strip():
            result["has_uncommitted"] = True

        # Get remote tracking branch first (needed for unpushed check)
        remote_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            capture_output=True, text=True, cwd=cwd, timeout=get_timeout()
        )
        if remote_result.returncode == 0:
            result["remote_branch"] = remote_result.stdout.strip()
            # Use machine-readable count instead of parsing git log output
            unpushed_result = subprocess.run(
                ["git", "rev-list", "--count", "@{u}.."],
                capture_output=True, text=True, cwd=cwd, timeout=get_timeout()
            )
            if unpushed_result.returncode == 0:
                try:
                    if int(unpushed_result.stdout.strip()) > 0:
                        result["has_unpushed"] = True
                except ValueError:
                    pass

    except Exception as e:
        if os.environ.get("CODE_REVIEW_DEBUG"):
            console.print(f"[yellow]Git status check warning: {e}[/yellow]")

    return result


def gather_repo_context(repo_dir: Optional[Path] = None) -> dict:
    """Gather context similar to 'assess' skill (git status, files, readmes)."""
    import typer

    cwd = repo_dir or Path.cwd()
    context = {
        "repo": None,
        "branch": None,
        "modified_files": [],
        "context_content": "",
    }

    # Git checks
    try:
        # Remote URL -> Owner/Repo
        res = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, cwd=cwd, timeout=get_timeout()
        )
        if res.returncode == 0:
            url = res.stdout.strip()
            # Parse git@github.com:owner/repo.git or https://github.com/owner/repo
            match = re.search(r'[:/]([\w-]+/[\w-]+)(?:\.git)?$', url)
            if match:
                context["repo"] = match.group(1)

        # Branch
        res = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, cwd=cwd, timeout=get_timeout()
        )
        if res.returncode == 0:
            context["branch"] = res.stdout.strip()

        # Modified files (staged and unstaged)
        res = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, cwd=cwd, timeout=get_timeout()
        )
        if res.returncode == 0 and res.stdout.strip():
            context["modified_files"] = res.stdout.strip().splitlines()

    except Exception as e:
        console.print(f"[yellow]Warning during git check: {e}[/yellow]", stderr=True)

    # File Context
    ctx_file = cwd / "CONTEXT.md"
    readme_file = cwd / "README.md"

    content_parts = []
    if ctx_file.exists():
        content_parts.append(f"## CONTEXT.md\n{ctx_file.read_text()[:2000]}")  # Cap size
    elif readme_file.exists():
        content_parts.append(f"## README.md\n{readme_file.read_text()[:1000]}")

    context["context_content"] = "\n\n".join(content_parts)

    return context
