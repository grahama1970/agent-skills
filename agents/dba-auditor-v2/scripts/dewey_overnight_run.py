#!/usr/bin/env python3
from __future__ import annotations
"""Compatibility wrapper for Dewey one-issue runs.

Historically this script was a broad overnight loop around
monitor_sparta.py repair-cycle.  That architecture is intentionally removed.
The `start` command now delegates to dewey_issue_worker.py exactly once unless
--repeat is explicitly supplied by an operator.  Cron should prefer
`dewey_issue_worker.py run` directly.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
WORKER = SCRIPT_DIR / "dewey_issue_worker.py"
DEFAULT_SESSION_ROOT = "/mnt/storage12tb/skills/review-db/outputs/dewey-sessions"
DEFAULT_MEMORY_REPO_ROOT = "/home/graham/workspace/experiments/memory"
DEFAULT_AGENT_SKILLS_ROOT = "/home/graham/workspace/experiments/agent-skills"


def run_worker(args: argparse.Namespace) -> int:
    worker_args = [
        sys.executable,
        str(WORKER),
        "run",
        "--run-id",
        args.run_id,
        "--run-root",
        str(args.session_root),
        "--memory-repo-root",
        str(args.memory_repo_root),
        "--agent-skills-root",
        str(args.agent_skills_root),
        "--timeout-s",
        str(args.repair_timeout_s or args.wait_timeout_s),
        "--health-timeout-s",
        str(args.health_json_timeout_s),
        "--bootstrap-limit",
        str(args.embed_batch_limit),
        "--heartbeat-s",
        str(args.worker_poll_s),
        "--json",
    ]
    if args.queue:
        worker_args.extend(["--queue", str(args.queue)])
    if args.apply:
        worker_args.append("--apply")
    if args.no_bootstrap:
        worker_args.append("--no-bootstrap")
    proc = subprocess.run(worker_args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    return int(proc.returncode)


def repeat_worker(args: argparse.Namespace) -> int:
    max_cycles = max(1, int(args.max_cycles))
    last_rc = 0
    receipts: list[dict[str, Any]] = []
    for idx in range(max_cycles):
        rc = run_worker(args)
        last_rc = rc
        receipt_path = Path(args.session_root) / args.run_id / "receipt.json"
        if receipt_path.exists():
            try:
                receipts.append(json.loads(receipt_path.read_text(encoding="utf-8")))
            except Exception:
                pass
        # Stop unless the operator explicitly asked for repeated successful slices.
        if rc != 0 or not args.repeat_until_empty:
            break
    if args.json:
        print(json.dumps({"schema": "dewey.compat_repeat.v1", "cycles": len(receipts), "last_rc": last_rc, "receipts": receipts}, indent=2, sort_keys=True))
    return last_rc


def status(args: argparse.Namespace) -> int:
    cmd = [sys.executable, str(WORKER), "status"]
    if args.queue:
        cmd.extend(["--queue", str(args.queue)])
    cmd.append("--json")
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    return int(proc.returncode)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    start = sub.add_parser("start", help="Compatibility start; runs one Dewey issue by default")
    start.add_argument("--run-id", required=True)
    start.add_argument("--session-root", type=Path, default=Path(DEFAULT_SESSION_ROOT))
    start.add_argument("--memory-repo-root", type=Path, default=Path(DEFAULT_MEMORY_REPO_ROOT))
    start.add_argument("--agent-skills-root", type=Path, default=Path(DEFAULT_AGENT_SKILLS_ROOT))
    start.add_argument("--queue", type=Path)
    start.add_argument("--apply", action="store_true")
    start.add_argument("--no-bootstrap", action="store_true")
    start.add_argument("--max-cycles", type=int, default=1)
    start.add_argument("--repeat", action="store_true", help="Operator-only: allow more than one issue in this process")
    start.add_argument("--repeat-until-empty", action="store_true", help="Operator-only: keep running successful issues up to --max-cycles")
    start.add_argument("--wall-clock-s", type=int, default=43200)  # retained for old callers; not used as a loop budget
    start.add_argument("--wait-timeout-s", type=int, default=7200)
    start.add_argument("--embed-batch-limit", type=int, default=0, help="Compatibility only: optional read-only bootstrap limit; embedding apply lanes are full-scope")
    start.add_argument("--repair-timeout-s", type=int, default=7200)
    start.add_argument("--health-json-timeout-s", type=int, default=300)
    start.add_argument("--health-fix-timeout-s", type=int, default=240)  # accepted but unused; Dewey does not call health --fix
    start.add_argument("--stall-limit", type=int, default=1)  # accepted but unused; one issue exits
    start.add_argument("--worker-poll-s", type=int, default=60)
    start.add_argument("--no-backup", action="store_true")  # accepted; backups are no longer per-run
    start.add_argument("--json", action="store_true")
    start.set_defaults(func=repeat_worker)

    st = sub.add_parser("status")
    st.add_argument("--session-root", type=Path, default=Path(DEFAULT_SESSION_ROOT))
    st.add_argument("--run-id")
    st.add_argument("--queue", type=Path)
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=status)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
