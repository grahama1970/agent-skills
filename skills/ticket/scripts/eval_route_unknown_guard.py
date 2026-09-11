#!/usr/bin/env python3
"""#1572 route-unknown-fails-closed guard.

A bogus --route exits 2 naming the route and listing VALID_ROUTES; the
explicit --human-first flag overrides and drafts with route recorded unknown.
Real CLI, no fixture inputs.
"""
import subprocess, sys, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # skills/ticket
CLI = [sys.executable, "scripts/ticket_cli.py"]
PROOF = "cd skills/agentic-evals && ./run.sh run ../ticket/fixtures/agentic_eval.json shows READY"
BASE = ["bug", "route probe guard", "--target", "skills/x", "--route", "totallybogus",
        "--observed", "o", "--expected", "e", "--repro", "r", "--proof", PROOF]


def run(extra):
    return subprocess.run(CLI + BASE + extra, cwd=ROOT, capture_output=True, text=True)


no_flag = run([])
if no_flag.returncode != 2:
    print(f"FAIL: expected exit 2, got {no_flag.returncode}: {no_flag.stderr[-200:]}", file=sys.stderr)
    sys.exit(1)
for needle in ("VALID_ROUTES: ", "totallybogus"):
    if needle not in no_flag.stderr + no_flag.stdout:
        print(f"FAIL: {needle!r} missing from error output", file=sys.stderr)
        sys.exit(1)
hf = run(["--human-first"])
if hf.returncode != 0:
    print(f"FAIL: --human-first variant failed rc={hf.returncode}: {hf.stderr[-200:]}", file=sys.stderr)
    sys.exit(1)
print("ROUTE-GUARD-PASS")
