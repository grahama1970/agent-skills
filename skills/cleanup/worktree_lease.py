#!/usr/bin/env python3
"""Worktrees as leases that expire, not artifacts that accumulate.

Purpose
    Three skills in this repo run ``git worktree add``. None of them ever runs
    ``git worktree remove``. Creation is automated and reclamation is manual,
    which is a ratchet: 182 registered worktrees, 8 of them created today. The
    existing tooling classifies and audits but deletes nothing, so the audit
    only reports a number that can never go down on its own.

    A worktree becomes a lease: whoever creates it records who owns it, why,
    and for how long. A reaper later reclaims the ones whose owner is gone and
    whose work is safely landed.

    The reaper's rules are all refusals, because the expensive mistake here is
    deleting someone's unpushed work, not leaving a directory around:

    - A live owner is never touched. PID alive means work in flight.
    - A dirty tree is never removed. Uncommitted changes are the work.
    - Commits not reachable from the remote are never removed. A clean tree can
      still hold hours of committed, unpushed work.
    - Inside the TTL is never touched, even when idle -- a job between steps
      looks identical to one that finished.
    - An UNREGISTERED worktree is reported, never auto-removed. We do not know
      who owns it, and guessing is how another lane loses a day.

Inputs
    The repository path and the lease registry.

Outputs
    ``register()`` records a lease. ``reap()`` returns a receipt naming every
    worktree removed, kept, and the reason for each.

Failure modes
    Any git command that fails leaves the worktree in place and records the
    error. The reaper degrades toward keeping things.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCHEMA = "cleanup.worktree_lease.v1"
REGISTRY = Path(os.environ.get("WORKTREE_LEASE_REGISTRY", Path.home() / ".cleanup" / "worktree-leases.jsonl"))

# Long enough that a slow multi-step job is never mistaken for a finished one.
DEFAULT_TTL_SECONDS = 6 * 3600


def _git(repo: Path, *args: str, timeout: float = 60.0) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", str(exc)
    return completed.returncode, completed.stdout, completed.stderr


def register(
    worktree: Path | str,
    *,
    purpose: str,
    owner_pid: int | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    registry: Path | None = None,
) -> dict[str, Any]:
    """Record a worktree lease. Called by whoever creates the worktree."""
    entry = {
        "schema": SCHEMA,
        "path": str(Path(worktree).resolve()),
        "purpose": purpose,
        "owner_pid": int(owner_pid if owner_pid is not None else os.getpid()),
        "created_at": time.time(),
        "ttl_seconds": int(ttl_seconds),
    }
    target = registry or REGISTRY
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError as exc:
        # A registry write must never fail the work that needed the worktree.
        entry["registry_error"] = str(exc)
    return entry


def _load_leases(registry: Path | None = None) -> dict[str, dict[str, Any]]:
    target = registry or REGISTRY
    leases: dict[str, dict[str, Any]] = {}
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return leases
    for line in lines:
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("path"):
            leases[str(entry["path"])] = entry  # last write wins
    return leases


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OSError, TypeError, ValueError):
        return True
    return True


def registered_worktrees(repo: Path) -> list[Path]:
    code, out, _ = _git(repo, "worktree", "list", "--porcelain")
    if code != 0:
        return []
    paths: list[Path] = []
    for line in out.splitlines():
        if line.startswith("worktree "):
            paths.append(Path(line[len("worktree "):].strip()))
    return paths


def inspect_worktree(repo: Path, worktree: Path) -> dict[str, Any]:
    """Everything the reaper needs to decide, gathered in one place."""
    state: dict[str, Any] = {"path": str(worktree), "exists": worktree.is_dir()}
    if not state["exists"]:
        state["reclaimable"] = True
        state["reason"] = "directory is gone; only the registration remains"
        return state

    code, out, _ = _git(worktree, "status", "--porcelain")
    if code != 0:
        state.update(reclaimable=False, reason="git status failed; refusing to guess")
        return state
    state["dirty"] = bool(out.strip())
    state["dirty_files"] = len([l for l in out.splitlines() if l.strip()])

    # Committed-but-unpushed work is invisible to `status` and is exactly what
    # must never be deleted.
    code, out, _ = _git(worktree, "log", "--oneline", "@{upstream}..HEAD")
    if code == 0:
        state["unpushed_commits"] = len([l for l in out.splitlines() if l.strip()])
    else:
        code2, out2, _ = _git(worktree, "log", "--oneline", "origin/main..HEAD")
        state["unpushed_commits"] = (
            len([l for l in out2.splitlines() if l.strip()]) if code2 == 0 else None
        )

    code, branch, _ = _git(worktree, "branch", "--show-current")
    state["branch"] = branch.strip()
    return state


def reap(
    repo: Path | str = ".",
    *,
    apply: bool = False,
    registry: Path | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Reclaim expired, abandoned, safely-landed worktrees.

    Every decision defaults to keeping. Removing a worktree that still holds
    work is unrecoverable in a way that leaving one is not.
    """
    repo_path = Path(repo).resolve()
    current = time.time() if now is None else now
    leases = _load_leases(registry)
    primary = repo_path

    removed: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []

    for worktree in registered_worktrees(repo_path):
        resolved = str(worktree.resolve()) if worktree.exists() else str(worktree)
        if Path(resolved) == primary:
            kept.append({"path": resolved, "reason": "primary checkout"})
            continue

        lease = leases.get(resolved)
        if lease is None:
            # Unknown owner: report it, never reclaim it. Guessing here is how
            # another lane loses a day of work.
            kept.append({"path": resolved, "reason": "unregistered; owner unknown", "unregistered": True})
            continue

        owner = lease.get("owner_pid")
        if isinstance(owner, int) and _pid_alive(owner):
            kept.append({"path": resolved, "reason": f"owner pid {owner} alive"})
            continue

        age = current - float(lease.get("created_at") or 0)
        ttl = int(lease.get("ttl_seconds") or DEFAULT_TTL_SECONDS)
        if age < ttl:
            kept.append({"path": resolved, "reason": f"within ttl ({int(age)}s of {ttl}s)"})
            continue

        state = inspect_worktree(repo_path, Path(resolved))
        if state.get("dirty"):
            kept.append({"path": resolved, "reason": f"dirty: {state['dirty_files']} file(s)"})
            continue
        unpushed = state.get("unpushed_commits")
        if unpushed is None:
            kept.append({"path": resolved, "reason": "could not prove commits are landed"})
            continue
        if unpushed > 0:
            kept.append({"path": resolved, "reason": f"{unpushed} unpushed commit(s)"})
            continue

        entry = {
            "path": resolved,
            "purpose": lease.get("purpose"),
            "age_seconds": int(age),
            "branch": state.get("branch"),
            "applied": False,
        }
        if apply:
            code, _, err = _git(repo_path, "worktree", "remove", "--force", resolved)
            entry["applied"] = code == 0
            if code != 0:
                entry["error"] = err.strip()[:200]
                kept.append({"path": resolved, "reason": f"remove failed: {entry['error']}"})
                continue
        removed.append(entry)

    if apply and removed:
        _git(repo_path, "worktree", "prune")

    return {
        "schema": "cleanup.worktree_reap.v1",
        "repo": str(repo_path),
        "apply": bool(apply),
        "removed": removed,
        "kept": kept,
        "registered_total": len(registered_worktrees(repo_path)),
        "unregistered": [k["path"] for k in kept if k.get("unregistered")],
    }


def assess_unregistered(repo: Path | str = ".", *, min_age_days: int = 14) -> dict[str, Any]:
    """Evidence for the existing backlog, which the reaper will not touch.

    The 181 worktrees that predate leasing have no recorded owner, so the
    reaper refuses them forever. That is correct and also useless on its own,
    so this produces the evidence a human needs: which are provably safe --
    clean tree, every commit reachable from the remote, old enough that no job
    is plausibly still using them -- and which are not, with the reason.

    It never deletes. The output is a decision aid, not an action.
    """
    repo_path = Path(repo).resolve()
    leases = _load_leases()
    cutoff = min_age_days * 86400
    now = time.time()

    safe: list[dict[str, Any]] = []
    unsafe: list[dict[str, Any]] = []

    for worktree in registered_worktrees(repo_path):
        resolved = worktree.resolve() if worktree.exists() else worktree
        if resolved == repo_path or str(resolved) in leases:
            continue
        state = inspect_worktree(repo_path, resolved)
        row = {"path": str(resolved), "branch": state.get("branch")}

        if not state.get("exists"):
            row["reason"] = "directory gone; registration is a ghost"
            safe.append(row)
            continue
        if state.get("dirty"):
            row["reason"] = f"dirty: {state.get('dirty_files')} file(s)"
            unsafe.append(row)
            continue
        unpushed = state.get("unpushed_commits")
        if unpushed is None:
            row["reason"] = "cannot prove commits are landed"
            unsafe.append(row)
            continue
        if unpushed > 0:
            row["reason"] = f"{unpushed} unpushed commit(s)"
            unsafe.append(row)
            continue
        try:
            age = now - resolved.stat().st_mtime
        except OSError:
            age = 0
        if age < cutoff:
            row["reason"] = f"only {int(age / 86400)}d old"
            unsafe.append(row)
            continue
        row["reason"] = f"clean, landed, {int(age / 86400)}d idle"
        row["age_days"] = int(age / 86400)
        safe.append(row)

    return {
        "schema": "cleanup.worktree_backlog.v1",
        "repo": str(repo_path),
        "min_age_days": min_age_days,
        "provably_safe": safe,
        "keep": unsafe,
        "note": "advisory only; nothing is removed. Unregistered worktrees have no recorded owner.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--apply", action="store_true", help="Actually remove; default is a preview.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--register", help="Register a worktree path instead of reaping.")
    parser.add_argument("--purpose", default="unspecified")
    parser.add_argument("--ttl-seconds", type=int, default=DEFAULT_TTL_SECONDS)
    parser.add_argument("--assess-backlog", action="store_true", help="Classify pre-existing unregistered worktrees.")
    parser.add_argument("--min-age-days", type=int, default=14)
    args = parser.parse_args(argv)

    if args.assess_backlog:
        report = assess_unregistered(args.repo, min_age_days=args.min_age_days)
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0
        print(f"provably safe to remove: {len(report['provably_safe'])}")
        print(f"must keep:               {len(report['keep'])}")
        for row in report["keep"][:10]:
            print(f"  keep {row['path']}  ({row['reason']})")
        return 0

    if args.register:
        entry = register(args.register, purpose=args.purpose, ttl_seconds=args.ttl_seconds)
        print(json.dumps(entry, indent=2, sort_keys=True) if args.json else f"registered {entry['path']}")
        return 0

    receipt = reap(args.repo, apply=args.apply)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    verb = "removed" if args.apply else "would remove"
    print(f"{verb} {len(receipt['removed'])} of {receipt['registered_total']} registered worktrees")
    for entry in receipt["removed"]:
        print(f"  - {entry['path']}  ({entry['purpose']}, {entry['age_seconds']}s old)")
    if receipt["unregistered"]:
        print(f"  {len(receipt['unregistered'])} unregistered worktree(s) reported, never auto-removed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
