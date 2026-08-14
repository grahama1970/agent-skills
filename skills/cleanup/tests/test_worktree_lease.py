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


def _push_main(repo: Path) -> None:
    subprocess.run(["git", "-C", str(repo), "push", "-q", "origin", "HEAD:main"], check=True)


def test_unmerged_work_is_surfaced(repo: Path) -> None:
    """Refusing to delete stranded work is useless if nothing surfaces it."""
    from worktree_lease import unmerged_report

    wt = _add_worktree(repo, "stranded")
    _git(wt, "config", "user.email", "t@t")
    _git(wt, "config", "user.name", "t")
    (wt / "work.py").write_text("value\n")
    subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(wt), "commit", "-qm", "stranded work"], check=True)

    report = unmerged_report(repo)
    paths = {row["path"] for row in report["worktrees"]}
    assert str(wt) in paths
    assert report["stranded_commits"] >= 1


def test_archive_recovers_committed_and_uncommitted_work(repo: Path, tmp_path: Path) -> None:
    """The only question that matters: does the work come back?"""
    from worktree_lease import archive_worktree

    wt = _add_worktree(repo, "archiveme")
    _git(wt, "config", "user.email", "t@t")
    _git(wt, "config", "user.name", "t")
    (wt / "committed.py").write_text("kept = 1\n")
    subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(wt), "commit", "-qm", "committed"], check=True)
    (wt / "uncommitted.py").write_text("also_kept = 2\n")

    receipt = archive_worktree(repo, wt, apply=True, archive_root=tmp_path / "dep")
    assert receipt["outcome"] == "archived"
    assert receipt["bundle_verified"] is True
    assert receipt["wip_commit_created"] is True
    assert not wt.exists(), "the worktree should be unregistered after archiving"

    subprocess.run(
        ["git", "-C", str(repo), "fetch", "-q", receipt["manifest"]["bundle"],
         "archiveme:recovered/archiveme"],
        check=True,
    )
    assert "kept = 1" in _git(repo, "show", "recovered/archiveme:committed.py")
    assert "also_kept = 2" in _git(repo, "show", "recovered/archiveme:uncommitted.py")


def test_the_bundle_is_restorable_by_branch_name(repo: Path, tmp_path: Path) -> None:
    """A range ending in HEAD records no ref: it verifies and cannot be fetched."""
    from worktree_lease import archive_worktree

    wt = _add_worktree(repo, "named")
    _git(wt, "config", "user.email", "t@t")
    _git(wt, "config", "user.name", "t")
    (wt / "x.py").write_text("1\n")
    subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(wt), "commit", "-qm", "c"], check=True)

    receipt = archive_worktree(repo, wt, apply=True, archive_root=tmp_path / "dep")
    assert receipt["manifest"]["restorable_by_name"] is True
    out = subprocess.run(
        ["git", "bundle", "list-heads", receipt["manifest"]["bundle"]],
        capture_output=True, text=True, check=False,
    ).stdout
    assert "named" in out, f"bundle records no named ref: {out!r}"


def test_a_preview_archive_moves_nothing(repo: Path, tmp_path: Path) -> None:
    from worktree_lease import archive_worktree

    wt = _add_worktree(repo, "previewarch")
    receipt = archive_worktree(repo, wt, apply=False, archive_root=tmp_path / "dep")
    assert receipt["outcome"] == "planned"
    assert receipt["applied"] is False
    assert wt.exists()
    assert not (tmp_path / "dep").exists()
