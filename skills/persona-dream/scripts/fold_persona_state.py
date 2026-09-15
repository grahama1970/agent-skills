#!/usr/bin/env python3
"""Independent persona-state fold for the C0/C1 experiment.

Reads ONLY: the hash-frozen baseline capsule plus every accepted
persona_state_delta record reread live from Memory for the persona+scope.
It never imports the admission module and never trusts in-memory state: each
delta doc is reread by exact _key and hash-cited, and VALIDATED against the
frozen contract (schema, record_type, arm/scope, finite numbers,
after == before + delta, per-cycle and cumulative bounds, canonical identity
classes, recomputed idempotency key). Any violation is
BLOCKED_FOLD_INVALID_ACCEPTED_DELTA — the fold never clamps or repairs
persisted evidence.

Arm isolation: an unscoped fold (no --arm) fails closed when the reread delta
set spans more than one experiment arm; scoped folds require explicit --arm.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from c0c1_frozen import (
    COLLECTION,
    FROZEN_BASELINE_SHA256,
    load_verified_baseline,
    validate_delta_doc,
)

FOLD_SCHEMA = "persona_dream.persona_state_fold.v1"


def _sha(payload: Any) -> str:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(data).hexdigest()


def run(args: argparse.Namespace) -> dict[str, Any]:
    baseline, baseline_sha = load_verified_baseline(Path(args.baseline))
    admission = baseline.get("admission") or {}
    state = dict(baseline.get("baseline_state") or {})

    if args.persona != baseline.get("persona"):
        raise SystemExit(f"BLOCKED_C0C1_CAPSULE_PERSONA: {args.persona!r} != capsule {baseline.get('persona')!r}")
    if args.user and args.user != baseline.get("user"):
        raise SystemExit(f"BLOCKED_C0C1_CAPSULE_USER: {args.user!r} != capsule {baseline.get('user')!r}")

    timeout = httpx.Timeout(30.0, connect=2.0)
    citations: list[dict[str, Any]] = []
    with httpx.Client(base_url=args.memory_base_url.rstrip("/"), timeout=timeout) as client:
        resp = client.post("/list", json={"collection": COLLECTION, "limit": 500, "filters": {"record_type": "persona_state_delta"}})
        resp.raise_for_status()
        docs = resp.json().get("documents") or []
        all_deltas = [d for d in docs
                      if str(d.get("persona_id") or "") == args.persona
                      and (not args.user or str(d.get("user_id") or "") == args.user)]
        # FOLD_EXPLICIT_ARM_ISOLATION: an unscoped fold must not silently
        # combine branchy arm histories.
        if args.arm is None:
            arms = sorted({str(d.get("arm") or "") for d in all_deltas})
            if len(arms) > 1:
                raise SystemExit(f"BLOCKED_FOLD_CROSS_ARM: delta set spans arms {arms}; pass --arm explicitly")
        deltas = [d for d in all_deltas
                  if (args.arm is None or str(d.get("arm") or "") == args.arm)]
        deltas.sort(key=lambda d: (str(d.get("accepted_at") or ""), str(d.get("_key") or "")))
        for d in deltas:
            # Independent exact reread of the delta doc itself.
            key = str(d.get("_key") or "")
            rresp = client.post("/list", json={"collection": COLLECTION, "limit": 2, "filters": {"_key": key}})
            rresp.raise_for_status()
            reread = rresp.json().get("documents") or []
            if len(reread) != 1:
                raise SystemExit(f"BLOCKED_FOLD_DELTA_REREAD_COUNT {key}: {len(reread)}")
            d = reread[0]
            # FOLD_VALIDATE_DONT_REPAIR: every accepted delta must satisfy the
            # frozen contract; violations BLOCK, they are never repaired.
            violation = validate_delta_doc(d, baseline)
            if violation:
                raise SystemExit(f"BLOCKED_FOLD_INVALID_ACCEPTED_DELTA {key}: {violation}")
            if args.arm is not None and str(d.get("arm") or "") != args.arm:
                raise SystemExit(f"BLOCKED_FOLD_INVALID_ACCEPTED_DELTA {key}: arm {d.get('arm')!r} != {args.arm!r}")
            if args.user and str(d.get("user_id") or "") != args.user:
                raise SystemExit(f"BLOCKED_FOLD_INVALID_ACCEPTED_DELTA {key}: user mismatch")
            axis = str(d.get("axis") or "")
            if axis not in state:
                raise SystemExit(f"BLOCKED_FOLD_UNKNOWN_AXIS {key}: {axis!r}")
            before = float(d.get("before"))
            if abs(state[axis] - before) > 1e-9:
                raise SystemExit(f"BLOCKED_FOLD_CONFLICT {key}: folded {state[axis]} != delta.before {before}")
            after = float(d.get("after"))
            state[axis] = round(after, 6)
            citations.append({"_key": key, "document_sha256": _sha(d), "axis": axis, "delta": d.get("delta")})

    receipt = {
        "schema": FOLD_SCHEMA,
        "status": "PASS_PERSONA_STATE_FOLDED",
        "persona_id": args.persona,
        "user_id": args.user,
        "arm": args.arm,
        "baseline_version": baseline.get("schema"),
        "baseline_sha256": baseline_sha,
        "current_state": state,
        "delta_citations": citations,
        "delta_count": len(citations),
        "equals_baseline": citations == [] and state == baseline.get("baseline_state"),
        "mocked": False,
        "live": True,
        "failed_gates": [],
    }
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--persona", required=True)
    ap.add_argument("--user", default="")
    ap.add_argument("--arm", default=None, help="fold only deltas admitted under this experiment arm (arm-scoped linear history); unscoped folds BLOCK on cross-arm delta sets")
    ap.add_argument("--baseline", type=Path, default=Path(__file__).resolve().parents[1] / "contracts" / "c0c1_baseline.json")
    ap.add_argument("--output", type=Path)
    ap.add_argument("--receipt", type=Path)
    ap.add_argument("--memory-base-url", default="http://127.0.0.1:8601")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    receipt = run(args)
    for path in (args.output, args.receipt):
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(f"{receipt['status']} state={receipt['current_state']} deltas={receipt['delta_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
