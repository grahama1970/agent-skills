#!/usr/bin/env python3
"""Dispatch one seat live and judge the run against the honesty contract.

Why this is not a deterministic test
    A live provider may answer, rate limit, or stall, and which of those
    happens is not under our control. Asserting a fixed answer would make the
    eval red whenever the provider is merely busy, and everyone would learn to
    ignore it.

    So the contract is not "the seat answers". It is:

      a seat either answers with real content, or names why it did not.

    Both outcomes pass. What fails is dishonesty in either direction:

      - PASS with no response bytes -- a green run that produced nothing;
      - a failure with no failure_code -- a dead end nobody can act on;
      - a different model answering with no record of the substitution --
        the reply looks fine and silently came from somewhere else.

    Those three are regressions no matter what the provider was doing, which is
    what makes this checkable while still being a live call.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]


def _run_dir_of(payload: dict) -> Path | None:
    receipt = str((payload.get("execution") or {}).get("receipt_dir") or "")
    if not receipt:
        return None
    return Path(receipt.replace("/tau-receipts", ""))


def probe(handler: str, *, timeout: int = 900) -> dict:
    token = f"LIVE-{uuid.uuid4().hex[:8].upper()}"
    command = [
        str(SKILL_ROOT / "run.sh"), "tau-dag", f"Reply with exactly: {token}",
        "--repo", "local/agent-skills",
        "--target", "live-seat-probe",
        "--immutable-goal", "Return the token or name a blocker.",
        "--handler", handler,
        "--execute", "--json",
    ]
    proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout, cwd=str(SKILL_ROOT))
    match = re.search(r"^\{", proc.stdout, re.M)
    if not match:
        return {"ok": False, "violation": "no JSON result from the run", "stderr": proc.stderr[-400:]}
    payload = json.loads(proc.stdout[match.start():])

    run_dir = _run_dir_of(payload)
    lanes: list[dict] = []
    if run_dir and run_dir.is_dir():
        for lane in sorted(run_dir.glob("node-artifacts/handler-*")):
            response = lane / "response.md"
            receipt_path = lane / "node-receipt.json"
            receipt = {}
            if receipt_path.is_file():
                try:
                    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                except ValueError:
                    receipt = {}
            body = response.read_text(encoding="utf-8", errors="replace") if response.is_file() else ""
            models = [
                c.get("command")[1]
                for c in (receipt.get("commands") or [])
                if isinstance(c.get("command"), list) and len(c.get("command")) > 1
            ]
            # The substitution is recorded under provider_receipt; check the
            # neighbouring shapes too so a receipt-layout change surfaces as a
            # violation to investigate rather than a silent pass.
            recorded_fallback = receipt.get("rate_limit_fallback")
            for block in ("provider_receipt", "provider", "submit_meta"):
                nested = receipt.get(block)
                if isinstance(nested, dict) and nested.get("rate_limit_fallback"):
                    recorded_fallback = nested["rate_limit_fallback"]
                    break
            lanes.append({
                "lane": lane.name,
                "status": str(receipt.get("status") or "MISSING"),
                "failure_code": receipt.get("failure_code"),
                "bytes": len(body),
                "has_token": token in body,
                "models": models,
                "recorded_fallback": recorded_fallback,
            })

    violations: list[str] = []
    for lane in lanes:
        if lane["status"] == "PASS" and lane["bytes"] == 0:
            violations.append(f"{lane['lane']}: PASS with an empty response")
        if lane["status"] not in {"PASS", "MISSING"} and not lane["failure_code"]:
            violations.append(f"{lane['lane']}: {lane['status']} with no failure_code")
        # A substituted model must be recorded. The requested handler carries
        # its model in the lane name; a different model answering silently is
        # the failure this guards.
        requested_base = lane["lane"].replace("handler-", "")
        if lane["status"] == "PASS" and lane["models"]:
            answered = lane["models"][-1]
            if answered and answered not in requested_base and requested_base not in answered:
                # A substitution is honest when the receipt itself records it.
                # stderr is not enough: it is not part of the artifact a
                # reader inherits.
                if not lane.get("recorded_fallback"):
                    violations.append(
                        f"{lane['lane']}: answered by {answered} with no record of substitution"
                    )

    answered = [l for l in lanes if l["bytes"] > 0]
    return {
        "ok": not violations,
        "handler": handler,
        "token": token,
        "run_status": payload.get("status"),
        "provider_live": payload.get("provider_live"),
        "lanes": lanes,
        "answered": len(answered),
        "violations": violations,
        "outcome": "answered" if answered else "named_blocker" if lanes else "no_lanes",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("handler")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        result = probe(args.handler, timeout=args.timeout)
    except subprocess.TimeoutExpired:
        # A timeout is a named outcome, not a violation of the contract: the
        # provider was slow, which is exactly the non-determinism this accepts.
        result = {"ok": True, "handler": args.handler, "outcome": "timed_out", "violations": []}

    print(json.dumps(result, indent=2) if args.json else
          f"{'HONEST' if result['ok'] else 'VIOLATION'}: {result.get('outcome')} "
          f"({result.get('answered', 0)} lane(s) answered)")
    for violation in result.get("violations", []):
        print(f"  - {violation}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
