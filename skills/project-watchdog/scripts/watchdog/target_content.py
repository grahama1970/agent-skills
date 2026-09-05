"""Target-bounded Git observations and private-index publication on primary main.

Local HEAD is descriptive, not the shipped baseline. No shared index, HEAD,
branch, registered worktree, or existing working file is ever changed here.
"""
from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import tempfile
from pathlib import Path

from .primary_models import FileVersion, OwnedTargets, TargetSnapshot, encoded


class ContentConflict(RuntimeError):
    """Retryable scoped contention. Not, by itself, a needs-human decision."""


def git_bytes(root: Path, *args: str, data: bytes | None = None,
              index: Path | None = None, timeout: int = 120) -> bytes:
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_LITERAL_PATHSPECS="1")
    if index is not None:
        env["GIT_INDEX_FILE"] = str(index)
    from . import primary
    result = subprocess.run(["git", "-C", str(root), *args], input=data,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=env, timeout=timeout, check=False,
                            pass_fds=primary.inherited_fds())
    if result.returncode:
        raise ContentConflict(f"git {args[0]} failed: {result.stderr.decode(errors='replace')[:1200]}")
    return result.stdout


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def remote_pin(root: Path) -> str:
    """Resolve live origin/main; fetch objects only, never update a branch/ref."""
    rows = git_bytes(root, "ls-remote", "--exit-code", "origin", "refs/heads/main").decode().splitlines()
    matching = [row.split()[0] for row in rows if len(row.split()) == 2 and row.split()[-1] == "refs/heads/main"]
    if len(matching) != 1:
        raise ContentConflict("origin/main did not resolve to exactly one SHA")
    sha = matching[0]
    try:
        kind = git_bytes(root, "cat-file", "-t", sha).strip()
    except ContentConflict:
        git_bytes(root, "fetch", "--no-tags", "--no-write-fetch-head", "origin", sha)
        kind = git_bytes(root, "cat-file", "-t", sha).strip()
    if kind != b"commit":
        raise ContentConflict("origin/main is not a commit")
    return sha


def remote_entries(root: Path, sha: str, targets: list[str]) -> dict[str, tuple[str, str]]:
    result = {}
    for row in git_bytes(root, "ls-tree", "-r", "-z", sha, "--", *targets).split(b"\0"):
        if not row:
            continue
        metadata, raw_path = row.split(b"\t", 1)
        mode, kind, oid = metadata.decode().split()
        if kind != "blob" or mode not in {"100644", "100755", "120000"}:
            raise ContentConflict("submodule/special target requires its own authority")
        result[os.fsdecode(raw_path)] = (mode, oid)
    return result


def _read_path(root: Path, name: str) -> tuple[FileVersion, bytes]:
    path = root / name
    if not path.parent.resolve().is_relative_to(root):
        raise ContentConflict(f"target traverses a symlinked parent: {name}")
    try:
        before = path.lstat()
    except FileNotFoundError:
        return FileVersion(kind="absent"), b""
    if stat.S_ISLNK(before.st_mode):
        raw, mode, kind = os.fsencode(os.readlink(path)), "120000", "symlink"
    elif stat.S_ISREG(before.st_mode):
        if before.st_nlink != 1:
            raise ContentConflict(f"hard-linked target is not exclusively path-scoped: {name}")
        raw = path.read_bytes()
        mode, kind = ("100755" if before.st_mode & 0o111 else "100644"), "file"
    else:
        raise ContentConflict(f"non-file target cannot be snapshotted: {name}")
    after = path.lstat()
    signature = lambda st: (st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
    if signature(before) != signature(after):
        raise ContentConflict(f"target changed while being read: {name}")
    oid = git_bytes(root, "hash-object", "--stdin", data=raw).decode().strip()
    return FileVersion(kind=kind, oid=oid, sha256=digest(raw), mode=mode), raw


def snapshot(root: Path, targets: list[str], sha: str, backup: Path | None = None) -> TargetSnapshot:
    """Enumerate/hash only literal target paths, plus their remote tombstones."""
    names = set(remote_entries(root, sha, targets))
    names.update(os.fsdecode(p) for p in git_bytes(
        root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *targets
    ).split(b"\0") if p)
    files = {}
    for name in sorted(names):
        version, raw = _read_path(root, name)
        files[name] = version
        if backup is not None and version.kind != "absent":
            backup.mkdir(parents=True, exist_ok=True)
            blob = backup / version.sha256
            try:
                with blob.open("xb") as handle:
                    handle.write(raw)
                    handle.flush()
                    os.fsync(handle.fileno())
            except FileExistsError:
                if digest(blob.read_bytes()) != version.sha256:
                    raise ContentConflict(f"backup digest mismatch: {name}")
    index = {}
    for row in git_bytes(root, "ls-files", "--stage", "-z", "--", *targets).split(b"\0"):
        if row:
            metadata, name = row.split(b"\t", 1)
            mode, oid, stage = metadata.decode().split()
            if stage != "0":
                raise ContentConflict(f"target has unresolved index stages: {os.fsdecode(name)}")
            index[os.fsdecode(name)] = f"{mode} {oid} {stage}"
    return TargetSnapshot(targets=targets, files=files, index_entries=index, remote_sha=sha,
                          head=git_bytes(root, "rev-parse", "HEAD").decode().strip())


def versions(snapshot_: TargetSnapshot) -> dict[str, tuple[str, str]]:
    return {name: (entry.mode, entry.oid) for name, entry in snapshot_.files.items()
            if entry.kind != "absent"}


def classify(root: Path, current: TargetSnapshot, *, repo: str, number: int,
             task_sha256: str, owned: OwnedTargets | None) -> dict[str, str]:
    """Never grant authority from HEAD dirtiness or an operator blanket hash map."""
    remote = remote_entries(root, current.remote_sha, current.targets)
    previous = owned if (owned and owned.repo == repo and owned.issue_number == number
                         and owned.task_sha256 == task_sha256 and owned.targets == current.targets) else None
    result = {}
    for name, version in current.files.items():
        value = None if version.kind == "absent" else (version.mode, version.oid)
        if value == remote.get(name):
            result[name] = "verified_remote_identical"
        elif previous is not None and previous.files.get(name) == version:
            result[name] = "verified_current_task_owned"
        else:
            result[name] = "unowned_target_edit"
    # Staged intent distinct from both the shipped and the observed target bytes
    # cannot be silently consumed. No shared-index change occurs in this module.
    for name, entry in current.index_entries.items():
        mode, oid, _ = entry.split()
        head = remote_entries(root, current.head, [name]).get(name)
        if (mode, oid) not in {head, remote.get(name), versions(current).get(name)}:
            result[name] = "distinct_staged_target_intent"
    return result


def require_unchanged(before: TargetSnapshot, after: TargetSnapshot) -> None:
    if before.files != after.files or before.index_entries != after.index_entries:
        raise ContentConflict("target content/index changed after authorization; preserve and rescan")


def scoped_commit(root: Path, reviewed: TargetSnapshot, parent: str,
                  receipt_dir: Path, message: str) -> str:
    """Build from frozen reviewed blobs, using a private index; never shared add/commit."""
    receipt_dir.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="publication-index-", dir=receipt_dir)
    os.close(fd)
    index = Path(name)
    index.unlink()  # read-tree initializes a private index, not an existing shared one.
    try:
        git_bytes(root, "read-tree", parent, index=index)
        remote = remote_entries(root, parent, reviewed.targets)
        for path in sorted(set(remote) | set(reviewed.files)):
            version = reviewed.files.get(path, FileVersion(kind="absent"))
            if version.kind == "absent":
                git_bytes(root, "update-index", "--force-remove", "--", path, index=index)
            else:
                actual, raw = _read_path(root, path)
                if actual != version:
                    raise ContentConflict(f"reviewed target changed before commit-tree: {path}")
                oid = git_bytes(root, "hash-object", "-w", "--stdin", data=raw).decode().strip()
                if oid != version.oid:
                    raise ContentConflict("written object differs from reviewed bytes")
                git_bytes(root, "update-index", "--add", "--cacheinfo", version.mode, oid, path, index=index)
        tree = git_bytes(root, "write-tree", index=index).decode().strip()
        if tree == git_bytes(root, "rev-parse", f"{parent}^{{tree}}").decode().strip():
            return parent  # Already shipped can be verified; do not require a cosmetic commit.
        commit = git_bytes(root, "commit-tree", tree, "-p", parent,
                           data=(message.rstrip() + "\n").encode()).decode().strip()
        assert_scoped_commit(root, commit, reviewed.targets)
        return commit
    finally:
        # This is an exclusively-created scratch INDEX, never a worktree/file cleanup.
        index.unlink(missing_ok=True)


def assert_scoped_commit(root: Path, commit: str, targets: list[str]) -> list[str]:
    """Attribution is exact for THIS commit, not every concurrent HEAD change."""
    names = [os.fsdecode(p) for p in git_bytes(root, "diff-tree", "--no-commit-id",
             "--name-only", "--no-renames", "-r", "-z", commit).split(b"\0") if p]
    outside = [name for name in names if not any(name == t or name.startswith(t + "/") for t in targets)]
    if outside:
        raise ContentConflict(f"worker-attributable commit contains unauthorized paths: {outside}")
    return names


def publish(root: Path, baseline: TargetSnapshot, reviewed: TargetSnapshot,
            receipt_dir: Path, run_id: str, number: int, *, remote_required: bool) -> str:
    """No force, reset, checkout or rebase. A raced push is retried by durable recovery."""
    now = remote_pin(root)
    old = remote_entries(root, baseline.remote_sha, baseline.targets)
    current = remote_entries(root, now, baseline.targets)
    desired = versions(reviewed)
    if current != old and current != desired:
        raise ContentConflict("origin/main advanced on THIS target since authorization")
    observed = snapshot(root, reviewed.targets, now)
    require_unchanged(reviewed, observed)
    commit = scoped_commit(root, reviewed, now, receipt_dir,
                           f"Resolve ticket #{number}\n\nWatchdog-Run: {run_id}")
    if remote_required and commit != now:
        git_bytes(root, "push", "origin", f"{commit}:refs/heads/main")
        landed = remote_pin(root)
        git_bytes(root, "merge-base", "--is-ancestor", commit, landed)
        if remote_entries(root, landed, reviewed.targets) != desired:
            raise ContentConflict("published target readback differs from reviewed content")
    return commit
