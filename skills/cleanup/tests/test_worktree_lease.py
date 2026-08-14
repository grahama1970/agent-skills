"""A worktree reaper is judged by what it refuses to delete.

182 worktrees accumulated because three skills create them and none removes
them. The fix is only safe if every refusal below holds: the expensive mistake
is deleting an unpushed day of work, not leaving a directory around.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from worktree_lease import (  # noqa: E402
    DEFAULT_TTL_SECONDS,
    inspect_worktree,
    reap,
    register,
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real repository with a real remote, so unpushed work is detectable."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)
    work = tmp_path / "repo"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True)
    subprocess.run(["git", "-C", str(work), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(work), "config", "user.name", "t"], check=True)
    (work / "seed.txt").write_text("seed\n")
    subprocess.run(["git", "-C", str(work), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(work), "commit", "-qm", "seed"], check=True)
    subprocess.run(["git", "-C", str(work), "push", "-q", "origin", "HEAD:main"], check=True)
    subprocess.run(["git", "-C", str(work), "branch", "-q", "-M", "main"], check=True)
    subprocess.run(["git", "-C", str(work), "branch", "-q", "--set-upstream-to", "origin/main"], check=False)
    return work


@pytest.fixture
def registry(tmp_path: Path) -> Path:
    return tmp_path / "leases.jsonl"


def _add_worktree(repo: Path, name: str) -> Path:
    path = repo.parent / name
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", "-b", name, str(path)], check=True)
    return path


def _dead_pid() -> int:
    pid = 999_000
    while True:
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, OSError):
            return pid
        pid += 1


def test_a_clean_landed_expired_worktree_is_reclaimed(repo: Path, registry: Path) -> None:
    wt = _add_worktree(repo, "done")
    register(wt, purpose="test", owner_pid=_dead_pid(), ttl_seconds=1, registry=registry)
    receipt = reap(repo, apply=True, registry=registry, now=time.time() + 10_000)
    assert [r["path"] for r in receipt["removed"]] == [str(wt.resolve())]
    assert not wt.exists()


def test_a_live_owner_is_never_reclaimed(repo: Path, registry: Path) -> None:
    """PID alive means work in flight."""
    wt = _add_worktree(repo, "live")
    register(wt, purpose="test", owner_pid=os.getpid(), ttl_seconds=0, registry=registry)
    receipt = reap(repo, apply=True, registry=registry, now=time.time() + 10_000)
    assert receipt["removed"] == []
    assert any("alive" in k["reason"] for k in receipt["kept"])
    assert wt.exists()


def test_a_dirty_worktree_is_never_reclaimed(repo: Path, registry: Path) -> None:
    """Uncommitted changes are the work."""
    wt = _add_worktree(repo, "dirty")
    (wt / "scratch.txt").write_text("in progress\n")
    register(wt, purpose="test", owner_pid=_dead_pid(), ttl_seconds=1, registry=registry)
    receipt = reap(repo, apply=True, registry=registry, now=time.time() + 10_000)
    assert receipt["removed"] == []
    assert any("dirty" in k["reason"] for k in receipt["kept"])
    assert wt.exists()


def test_unpushed_commits_are_never_reclaimed(repo: Path, registry: Path) -> None:
    """A clean tree can still hold hours of committed, unpushed work."""
    wt = _add_worktree(repo, "unpushed")
    (wt / "real.txt").write_text("real work\n")
    subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(wt), "commit", "-qm", "real work"], check=True)
    register(wt, purpose="test", owner_pid=_dead_pid(), ttl_seconds=1, registry=registry)

    receipt = reap(repo, apply=True, registry=registry, now=time.time() + 10_000)
    assert receipt["removed"] == []
    assert any("unpushed" in k["reason"] or "landed" in k["reason"] for k in receipt["kept"])
    assert wt.exists()


def test_a_worktree_inside_its_ttl_is_left_alone(repo: Path, registry: Path) -> None:
    """A job between steps looks identical to one that finished."""
    wt = _add_worktree(repo, "young")
    register(wt, purpose="test", owner_pid=_dead_pid(), ttl_seconds=DEFAULT_TTL_SECONDS, registry=registry)
    receipt = reap(repo, apply=True, registry=registry)
    assert receipt["removed"] == []
    assert any("within ttl" in k["reason"] for k in receipt["kept"])


def test_an_unregistered_worktree_is_reported_never_removed(repo: Path, registry: Path) -> None:
    """Unknown owner: guessing is how another lane loses a day."""
    wt = _add_worktree(repo, "orphan")
    receipt = reap(repo, apply=True, registry=registry, now=time.time() + 10_000)
    assert receipt["removed"] == []
    assert str(wt.resolve()) in receipt["unregistered"]
    assert wt.exists()


def test_the_primary_checkout_is_never_a_candidate(repo: Path, registry: Path) -> None:
    receipt = reap(repo, apply=True, registry=registry, now=time.time() + 10_000)
    assert any(k["reason"] == "primary checkout" for k in receipt["kept"])


def test_a_preview_removes_nothing(repo: Path, registry: Path) -> None:
    wt = _add_worktree(repo, "preview")
    register(wt, purpose="test", owner_pid=_dead_pid(), ttl_seconds=1, registry=registry)
    receipt = reap(repo, apply=False, registry=registry, now=time.time() + 10_000)
    assert [r["path"] for r in receipt["removed"]] == [str(wt.resolve())]
    assert receipt["removed"][0]["applied"] is False
    assert wt.exists(), "a preview must not delete"


def test_a_vanished_directory_is_reclaimable(repo: Path, registry: Path) -> None:
    state = inspect_worktree(repo, repo.parent / "never-existed")
    assert state["reclaimable"] is True


def test_registration_survives_for_a_later_reaper(tmp_path: Path) -> None:
    registry = tmp_path / "leases.jsonl"
    register(tmp_path / "wt", purpose="ticket-123", owner_pid=4242, ttl_seconds=99, registry=registry)
    entry = json.loads(registry.read_text(encoding="utf-8").splitlines()[-1])
    assert entry["purpose"] == "ticket-123"
    assert entry["owner_pid"] == 4242


def test_an_unwritable_registry_never_fails_the_caller(tmp_path: Path) -> None:
    """The work that needed the worktree must not die because logging failed."""
    entry = register(tmp_path / "wt", purpose="p", registry=tmp_path / "nope" / "x" / "leases.jsonl")
    assert entry["path"].endswith("/wt")
