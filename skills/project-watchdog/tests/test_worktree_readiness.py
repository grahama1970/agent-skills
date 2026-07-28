"""Fail-closed worktree gate before ticket-repair dispatch (#1045).

Observed 2026-07-28: the registry pointed agent-skills at a worktree on an
unrelated feature branch, 686 commits behind main, 543 modified tracked files,
while a cron lane wrote tracked files into it every few seconds. Dispatching
there authors a repair on the wrong branch, over another lane's uncommitted
edits, and can corrupt a running job.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from watchdog.registry import worktree_readiness  # noqa: E402


def _git(path: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin"},
    )


def _repo(tmp_path: Path, branch: str = "main") -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", branch, ".")
    (repo / "f.txt").write_text("v1\n")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def test_clean_default_branch_is_ready(tmp_path):
    got = worktree_readiness(_repo(tmp_path))
    assert got["ready"] is True
    assert got["reasons"] == []
    assert got["branch"] == "main"


def test_master_also_counts_as_default(tmp_path):
    got = worktree_readiness(_repo(tmp_path, branch="master"))
    assert got["ready"] is True


def test_feature_branch_blocks(tmp_path):
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "battle-adaptive-lineage-goal")
    got = worktree_readiness(repo)
    assert got["ready"] is False
    assert any(r.startswith("branch_is_not_default:") for r in got["reasons"])


def test_dirty_tracked_files_block(tmp_path):
    repo = _repo(tmp_path)
    (repo / "f.txt").write_text("v2\n")
    got = worktree_readiness(repo)
    assert got["ready"] is False
    assert any(r.startswith("tracked_files_dirty:") for r in got["reasons"])
    assert got["dirty_tracked"] == 1
    assert got["dirty_paths"] == ["f.txt"]


def test_untracked_files_alone_do_not_block(tmp_path):
    """Report volume is normal; only tracked edits make a repair unattributable."""
    repo = _repo(tmp_path)
    (repo / "scratch.log").write_text("noise\n")
    got = worktree_readiness(repo)
    assert got["ready"] is True
    assert got["untracked"] == 1


def test_missing_worktree_blocks(tmp_path):
    got = worktree_readiness(tmp_path / "nope")
    assert got["ready"] is False
    assert got["reasons"] == ["worktree_missing"]


def test_non_git_directory_blocks(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    got = worktree_readiness(plain)
    assert got["ready"] is False


def test_both_reasons_reported_together(tmp_path):
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature")
    (repo / "f.txt").write_text("v2\n")
    got = worktree_readiness(repo)
    assert len(got["reasons"]) == 2
