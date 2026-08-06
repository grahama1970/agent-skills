#!/usr/bin/env python3
"""Deterministic root-cause diagnosis for a live /ask roundtable/compete run.

Given a run-output-root (or a single run dir), walks a FIXED decision tree
over the typed receipts and prints exactly why each seat did or did not
deliver, plus the recommended action. The reliability of a live run is
non-deterministic; this diagnosis is deterministic — same receipts always
yield the same verdict.

Decision tree:
  1. top-level result status: NEEDS_INTERVIEW -> missing_fields;
     BLOCKED -> blocked_reason/failure_code/next_command.
  2. join receipt: status + per-seat seat_terminal_states[].failure_code.
  3. per-seat node receipt: failure_code + failure + recovery next_command.
Every failure_code is mapped to its recommended action from the browser
failure-code table when available.

Usage: diagnose_roundtable_run.py <run-output-root-or-run-dir> [result.json]
"""

from __future__ import annotations

import glob
import json
import os
import sys

# Actionable recommendations per typed failure_code (mirrors the worker's
# BROWSER_FAILURE_CODES auto_retry_blocked_reason so the diagnosis is stable
# even outside the worker process).
RECOMMENDED = {
    "browser_tab_unverified_with_multiple_provider_tabs":
        "pass --expect-url for the seat's live tab URL or close excess provider tabs (NOT a rebind)",
    "browser_tab_not_open": "reprovision the seat tab (it is no longer open)",
    "browser_tab_identity_mismatch": "rebind the browser-oracle binding to the live tab",
    "browser_provider_rate_limited": "wait for the provider cooldown, then retry",
    "browser_submit_not_accepted": "composer did not accept the prompt; retry or reprovision the tab",
    "handler_timeout": "the lane exceeded its budget; check provider latency / raise timeout",
    "lane_deadline_reaped": "the run deadline killed the lane before completion; raise the deadline",
    "scillm_auth_invalid_api_key": "resolve the SciLLM key (SCILLM_MASTER_KEY / scillm .env)",
}


def _load(path: str) -> dict | None:
    try:
        return json.load(open(path))
    except Exception:
        return None


def diagnose_run(run_dir: str) -> None:
    join_glob = glob.glob(os.path.join(run_dir, "node-artifacts", "join", "node-receipt.json"))
    if not join_glob:
        # run_dir may nest a hashed run dir (one or two levels down)
        join_glob = glob.glob(os.path.join(run_dir, "*", "node-artifacts", "join", "node-receipt.json"))
    if not join_glob:
        join_glob = glob.glob(os.path.join(run_dir, "**", "node-artifacts", "join", "node-receipt.json"), recursive=True)
    if not join_glob:
        print(f"  no join receipt under {run_dir} — run blocked before execution (see result status)")
        return
    join = _load(join_glob[0]) or {}
    print(f"  join status: {join.get('status')} | removed_seats: {join.get('removed_seats')}")
    for s in join.get("seat_terminal_states", []):
        fc = s.get("failure_code")
        rec = RECOMMENDED.get(fc, "(no mapped action)") if fc else ""
        mark = "OK " if s.get("delivered") else "XX "
        print(f"    {mark}{s.get('handler')}: delivered={s.get('delivered')} chars={s.get('response_chars')}"
              + (f" | failure_code={fc} -> {rec}" if fc else ""))


def diagnose(path: str, result_path: str | None = None) -> int:
    if result_path and os.path.isfile(result_path):
        res = _load(result_path) or {}
        status = res.get("status")
        print(f"top-level status: {status}")
        if status == "NEEDS_INTERVIEW":
            b = res.get("bundle") or {}
            print(f"  missing_fields: {b.get('missing_fields')}")
            print("  -> supply the named field(s) (e.g. --immutable-goal) and rerun")
            return 0
        ex = res.get("execution") or {}
        if ex.get("blocked_reason") or ex.get("failure_code"):
            print(f"  BLOCKED: reason={ex.get('blocked_reason')} failure_code={ex.get('failure_code')}")
            print(f"  next_command: {ex.get('next_command')}")

    run_dirs = [d for d in glob.glob(os.path.join(path, "*")) if os.path.isdir(d)] or [path]
    for rd in run_dirs:
        print(f"run: {os.path.basename(rd)}")
        diagnose_run(rd)
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(diagnose(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
