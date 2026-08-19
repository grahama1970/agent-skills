#!/usr/bin/env python3
"""Runtime-artifact safety primitives for the debugger (#1440).

Two fail-closed guards a debugger must pass before it writes or reads a runtime
artifact (request/status/proof), independent of where those artifacts live:

- containment: resolve realpaths and reject a path that escapes the allowed root,
  even when the lexical string looks contained (a symlink inside the root that
  points outside must not be followed to a write outside it);
- runtime lock: an owner(PID)+TTL lock that a crashed writer cannot leave
  permanently held -- a stale lock (dead owner OR expired TTL) is recovered with
  evidence, but an ACTIVE lock (owner alive AND unexpired) is never stolen.

CLI (used by fixtures/runtime-containment.json):

    debugger_runtime_guard.py check-containment <root> <candidate>
    debugger_runtime_guard.py lock-acquire <lockfile> [--ttl N]
    debugger_runtime_guard.py lock-write   <lockfile> --pid P --age-seconds A --ttl N

Exit 0 on success; exit 1 with a reason on a rejected escape or a refused active
lock; exit 2 on usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


class PathEscape(Exception):
    pass


def resolve_within(candidate: str | Path, root: str | Path) -> Path:
    """Return candidate's realpath if it is inside root's realpath, else raise.

    Both sides are resolved with symlinks followed, so lexical containment is not
    trusted: a path that string-matches under root but whose realpath lands
    elsewhere (a symlink escape or ``..`` traversal) is rejected.
    """
    root_real = Path(root).resolve(strict=False)
    cand_real = Path(candidate).resolve(strict=False)
    if cand_real == root_real or root_real in cand_real.parents:
        return cand_real
    raise PathEscape(
        f"path escape: {candidate} resolves to {cand_real}, outside root {root_real}"
    )


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by another user
    return True


def lock_is_stale(lock: dict, now: float) -> tuple[bool, str]:
    """A lock is stale (recoverable) if its owner is dead OR its TTL has expired."""
    pid = int(lock.get("pid", -1))
    created = float(lock.get("created_at", 0.0))
    ttl = float(lock.get("ttl", 0.0))
    if not _pid_alive(pid):
        return True, f"owner pid {pid} is not alive"
    if ttl > 0 and now - created > ttl:
        return True, f"ttl {ttl}s expired ({now - created:.0f}s old) though owner pid {pid} is alive"
    return False, f"owner pid {pid} is alive and ttl not expired"


def lock_acquire(lock_path: Path, ttl: float, now: float) -> tuple[bool, str]:
    """Acquire the lock, recovering it only on stale evidence. Never steal active."""
    if lock_path.exists():
        try:
            existing = json.loads(lock_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
        stale, why = lock_is_stale(existing, now)
        if not stale:
            return False, f"lock held: {why}"
        reason = f"recovered stale lock ({why})"
    else:
        reason = "acquired free lock"
    lock_path.write_text(
        json.dumps({"pid": os.getpid(), "created_at": now, "ttl": ttl}) + "\n",
        encoding="utf-8",
    )
    return True, reason


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_c = sub.add_parser("check-containment")
    p_c.add_argument("root")
    p_c.add_argument("candidate")

    p_a = sub.add_parser("lock-acquire")
    p_a.add_argument("lockfile", type=Path)
    p_a.add_argument("--ttl", type=float, default=30.0)

    p_w = sub.add_parser("lock-write")
    p_w.add_argument("lockfile", type=Path)
    p_w.add_argument("--pid", type=int, required=True)
    p_w.add_argument("--age-seconds", type=float, default=0.0)
    p_w.add_argument("--ttl", type=float, default=30.0)

    args = parser.parse_args()
    now = time.time()

    if args.cmd == "check-containment":
        try:
            resolved = resolve_within(args.candidate, args.root)
        except PathEscape as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"contained: {resolved}")
        return 0

    if args.cmd == "lock-write":
        # Test helper: plant a lock with a chosen owner/age so recovery is testable.
        args.lockfile.write_text(
            json.dumps({"pid": args.pid, "created_at": now - args.age_seconds, "ttl": args.ttl}) + "\n",
            encoding="utf-8",
        )
        print(f"wrote lock pid={args.pid} age={args.age_seconds}s ttl={args.ttl}s")
        return 0

    if args.cmd == "lock-acquire":
        acquired, reason = lock_acquire(args.lockfile, args.ttl, now)
        if not acquired:
            print(reason, file=sys.stderr)
            return 1
        print(reason)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
