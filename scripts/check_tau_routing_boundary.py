#!/usr/bin/env python3
"""Tau-only model-routing boundary — deterministic static enforcement check.

Operator architecture rule (P1, external review 2026-07-19):

    Only ``/tau`` may reach ``/scillm``.

Persona-dream and watch code must never POST to the scillm proxy directly for
model inference. They must route through a sanctioned Tau node:

  * TEXT / QRA reasoning -> ``skills/persona-dream/scripts/tau_text_reasoning_adapter.py``
    (which subprocesses ``tau_coding.persona_dream_text_reasoning_agent``), and
  * IMAGE / VLM review   -> the Tau panel-reviewer route
    (``tau_coding.persona_dream_panel_agent``), or a frame-shaped Tau VLM node.

This script is a *deterministic* static scan (no LLM, no network). It walks
every ``*.py`` file under ``skills/persona-dream`` and ``skills/watch`` and flags
lines that talk to the scillm proxy transport directly:

  * the scillm proxy host:port (``localhost:4001`` / ``127.0.0.1:4001``),
  * the scillm-internal route prefix (``/v1/scillm/...``),
  * a scillm ``/v1/chat/completions`` POST (excluding non-scillm hosts such as
    ``chutes.ai``, ``opencode.ai/zen`` and ``*.test`` mock hosts).

Enforcement model (baseline / ratchet):

  * ALLOWLIST  — sanctioned files that legitimately name scillm (the Tau adapter,
    boundary-guard sanity scripts, this checker). These never fail.
  * TEMPORARY_DEBT — the known, pre-existing direct-scillm callers enrolled at
    the time this boundary was introduced. They are reported prominently but do
    not fail the default gate, so the check can be wired green today while the
    live migrations land. Marked with a justification + owning P1.
  * Anything else with a direct-scillm line is a HARD FAILURE.

So: the check PASSES on the current tree (all sites are allowlisted or enrolled
as debt), and FAILS the instant a *new* un-sanctioned direct-scillm call appears
(e.g. reverting one of the phase13/phase14 Tau migrations back to a direct POST).
Run with ``--strict`` to also fail on any remaining TEMPORARY_DEBT (use once the
debt is paid down to enforce a zero-direct-scillm tree).

Exit code: 0 when clean (no un-sanctioned violations; and no debt under
``--strict``), 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = ["skills/persona-dream", "skills/watch"]
SKIP_DIRS = {".venv", ".pytest_cache", "__pycache__", "node_modules", ".ruff_cache", ".git"}

# Line-level signals that a line reaches the scillm proxy transport directly.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"localhost:4001|127\.0\.0\.1:4001"), "scillm_proxy_hostport"),
    (re.compile(r"/v1/scillm/"), "scillm_proxy_path"),
    (re.compile(r"/v1/chat/completions"), "scillm_chat_completions"),
]
# Hosts that are explicitly NOT the scillm proxy (allowed external / mock hosts).
_NOT_SCILLM = re.compile(r"chutes\.ai|opencode\.ai/zen|\.test/|watch-scillm\.test|example\.invalid")
# Inline per-line escape hatch for a documented, sanctioned reference.
_INLINE_ALLOW = re.compile(r"#\s*tau-routing:allow")

# ---------------------------------------------------------------------------
# ALLOWLIST — sanctioned files. These name scillm legitimately and never fail.
#
# The Tau-only rule governs MODEL ROUTING: persona-dream/watch must not use the
# scillm proxy to obtain model inference for pipeline output. Two categories of
# file legitimately name the scillm transport WITHOUT being model-routing callers
# and are permanently allowlisted:
#
#   1. The sanctioned Tau adapters + this checker (they route THROUGH Tau, or
#      only reference scillm tokens as detection patterns).
#   2. DIAGNOSTICS that probe the scillm *service* rather than route pipeline
#      inference through it:
#        * a service-health / model-inventory probe hitting /v1/scillm/health and
#          /v1/scillm/models is an ops liveness check, not model routing;
#        * a loopback-only transport-contract proof whose PURPOSE is to verify the
#          scillm proxy's own transport/concurrency behavior (exactly N loopback
#          calls, is_loopback-enforced) is testing the transport itself — routing
#          it through Tau would defeat the proof;
#        * a boundary-guard sanity that asserts SCILLM_BASE_URL is local does not
#          itself perform inference.
#      None of these are imported or invoked by a live pipeline lane.
# ---------------------------------------------------------------------------
ALLOWLIST: dict[str, str] = {
    "scripts/check_tau_routing_boundary.py":
        "this static checker itself references scillm tokens as detection patterns",
    "skills/persona-dream/scripts/tau_text_reasoning_adapter.py":
        "sanctioned persona-dream -> Tau text-reasoning dispatch adapter (routes THROUGH Tau)",
    "skills/persona-dream/scripts/sanity_scillm_subagent_loop.py":
        "boundary-guard sanity: asserts SCILLM_BASE_URL is local; does not itself bypass Tau for inference",
    "skills/persona-dream/scripts/sanity_scillm_loop_negative_tests.py":
        "negative-test harness for the scillm loop guard (uses example.invalid); no live inference",
    # --- DIAGNOSTICS (category 2 above): probe the service, not model routing ---
    "skills/persona-dream/scripts/persona_dream.py":
        "DIAGNOSTIC: CLI backend-readiness probe hits /v1/scillm/health + /v1/scillm/models for an ops "
        "liveness/model-inventory report only; it does NOT obtain pipeline model inference from scillm. "
        "Probing a service's health endpoint is not model routing. Not a live-lane inference caller.",
    "skills/persona-dream/scripts/medium_loop_dag_smoke.py":
        "DIAGNOSTIC: loopback-only transport-contract proof ladder. Makes exactly 1-2 is_loopback-enforced "
        "calls purely to verify the scillm proxy's own transport/concurrency (as_completed) semantics, not "
        "to produce pipeline artifacts. Routing this through Tau would defeat the transport proof. "
        "Not imported or wired into any live lane / run.sh / sanity path.",
}

# ---------------------------------------------------------------------------
# TEMPORARY_DEBT — pre-existing direct-scillm callers known at boundary rollout.
# Each is a real violation of the Tau-only rule, enrolled so the gate can be
# wired green while live migrations land. Owning item: P1 Tau-only routing
# boundary (external review 2026-07-19). Removing an entry here (or migrating the
# file) that still POSTs to scillm turns it back into a HARD FAILURE.
# ---------------------------------------------------------------------------
TEMPORARY_DEBT: dict[str, str] = {
    # --- watch VLM/QRA/audio (the review's named violation) ---
    "skills/watch/scripts/qra.py":
        "TEMPORARY_DEBT: watch posts VLM frame descriptions + QRA + audio to scillm directly; "
        "needs Tau text node (text/QRA) + frame-shaped Tau VLM node (image). P1 routing boundary.",
    "skills/watch/scripts/config.py":
        "TEMPORARY_DEBT: defines WATCH_SCILLM_API_BASE / proxy-key that authorize qra.py's direct call. "
        "Retire when qra.py routes through Tau. P1 routing boundary.",
    # NOTE: the experimental 'rung' ladder (rung0/1/2/4/5/8/17/18/21/22) and
    # dreamer_sequential_runner.py were RETIRED (git rm) on 2026-07-19 as
    # superseded one-off scillm transport experiments with no live imports.
    # See reports/pipeline-complete/.persona-dream/rung_ladder_retirement_receipt.v1.json.
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iter_py_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        files.append(path)
    return files


def scan(repo_root: Path) -> dict[str, list[dict[str, Any]]]:
    """Return {relpath: [ {line, kind, snippet}, ... ]} for direct-scillm lines."""
    hits: dict[str, list[dict[str, Any]]] = {}
    for rel_root in SCAN_ROOTS:
        root = repo_root / rel_root
        if not root.exists():
            continue
        for path in _iter_py_files(root):
            rel = str(path.relative_to(repo_root))
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines, 1):
                if _INLINE_ALLOW.search(line):
                    continue
                for pat, kind in _PATTERNS:
                    if not pat.search(line):
                        continue
                    if kind == "scillm_chat_completions" and _NOT_SCILLM.search(line):
                        continue
                    hits.setdefault(rel, []).append(
                        {"line": i, "kind": kind, "snippet": line.strip()[:120]}
                    )
                    break
    return hits


def evaluate(hits: dict[str, list[dict[str, Any]]], *, strict: bool) -> dict[str, Any]:
    allowed: dict[str, Any] = {}
    debt: dict[str, Any] = {}
    violations: dict[str, Any] = {}
    for rel, file_hits in sorted(hits.items()):
        if rel in ALLOWLIST:
            allowed[rel] = {"reason": ALLOWLIST[rel], "hits": file_hits}
        elif rel in TEMPORARY_DEBT:
            debt[rel] = {"reason": TEMPORARY_DEBT[rel], "hits": file_hits}
        else:
            violations[rel] = {"hits": file_hits}

    # An allowlist/debt entry for a file that no longer has any direct-scillm line
    # is stale — surface it so the registry stays honest.
    stale_debt = sorted(f for f in TEMPORARY_DEBT if f not in hits)
    stale_allow = sorted(
        f for f in ALLOWLIST if f not in hits and f != "scripts/check_tau_routing_boundary.py"
    )

    failed = bool(violations) or (strict and bool(debt))
    return {
        "schema": "persona_dream.tau_routing_boundary_check.v1",
        "created_at": _now_iso(),
        "rule": "only /tau may reach /scillm",
        "strict": strict,
        "status": "FAIL" if failed else "PASS",
        "counts": {
            "hard_violations": len(violations),
            "temporary_debt": len(debt),
            "sanctioned_allowlisted": len(allowed),
            "stale_debt_entries": len(stale_debt),
            "stale_allow_entries": len(stale_allow),
        },
        "hard_violations": violations,
        "temporary_debt": debt,
        "sanctioned_allowlisted": allowed,
        "stale_debt_entries": stale_debt,
        "stale_allow_entries": stale_allow,
    }


def _print_human(result: dict[str, Any]) -> None:
    c = result["counts"]
    print(f"Tau-only routing boundary check  [{result['status']}]  (strict={result['strict']})")
    print(f"  rule: {result['rule']}")
    print(
        f"  hard_violations={c['hard_violations']}  temporary_debt={c['temporary_debt']}  "
        f"sanctioned={c['sanctioned_allowlisted']}  stale_debt={c['stale_debt_entries']}"
    )
    if result["hard_violations"]:
        print("\n  HARD VIOLATIONS (un-sanctioned direct scillm access — MUST route via Tau):")
        for rel, info in result["hard_violations"].items():
            for h in info["hits"]:
                print(f"    FAIL  {rel}:{h['line']} [{h['kind']}] {h['snippet']}")
    if result["stale_debt_entries"]:
        print("\n  STALE DEBT (registry lists a file that no longer calls scillm — migrate/remove entry):")
        for rel in result["stale_debt_entries"]:
            print(f"    STALE {rel}")
    if result["temporary_debt"] and not result["hard_violations"]:
        print(f"\n  TEMPORARY_DEBT ({c['temporary_debt']} pre-existing callers enrolled, not yet migrated):")
        for rel in result["temporary_debt"]:
            print(f"    debt  {rel}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--strict", action="store_true", help="Also fail on remaining TEMPORARY_DEBT.")
    parser.add_argument("--json", action="store_true", help="Emit the JSON receipt to stdout.")
    parser.add_argument("--receipt-out", type=Path, default=None, help="Write the JSON receipt here.")
    args = parser.parse_args(argv)

    hits = scan(args.repo_root.resolve())
    result = evaluate(hits, strict=args.strict)

    if args.receipt_out:
        args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
        args.receipt_out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        _print_human(result)

    return 1 if result["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
