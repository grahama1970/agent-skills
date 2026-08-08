"""source_snapshot - helpers.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .git_repo import all_non_git_files, git


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def non_git_file_hashes(repo: Path) -> dict[str, str]:
    return {
        path.relative_to(repo).as_posix(): _sha(path)
        for path in all_non_git_files(repo)
    }


def status_z(repo: Path) -> bytes:
    return subprocess.run(
        [
            "git",
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--ignored=matching",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout


def refs_snapshot(repo: Path) -> str:
    # Excludes reflogs; this captures durable refs and catches leaked temporary branches.
    return git(repo, "show-ref", "--head", check=False).stdout


@dataclass(frozen=True)
class SourceSnapshot:
    head: str
    branch: str
    index_tree: str
    status_z: bytes
    worktree_list: str
    refs: str
    file_hashes: dict[str, str]


def snapshot_source(repo: Path) -> SourceSnapshot:
    return SourceSnapshot(
        head=git(repo, "rev-parse", "HEAD").stdout.strip(),
        branch=git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip(),
        index_tree=git(repo, "write-tree").stdout.strip(),
        status_z=status_z(repo),
        worktree_list=git(repo, "worktree", "list", "--porcelain").stdout,
        refs=refs_snapshot(repo),
        file_hashes=non_git_file_hashes(repo),
    )


def assert_source_snapshot_unchanged(repo: Path, before: SourceSnapshot) -> None:
    after = snapshot_source(repo)
    assert after.head == before.head
    assert after.branch == before.branch
    assert after.index_tree == before.index_tree
    assert after.status_z == before.status_z
    assert after.refs == before.refs
    assert after.file_hashes == before.file_hashes
    assert after.worktree_list == before.worktree_list
