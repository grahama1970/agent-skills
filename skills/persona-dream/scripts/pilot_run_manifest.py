#!/usr/bin/env python3
"""Pilot run manifest: hash-record the full phase policy BEFORE execution.

Protocol v2 precondition: "run manifest hash-records the full phase policy
before execution." This tool freezes, in one receipt:

- the protocol file (with addendum) and the R1/R2 selection receipt
- both producer contracts
- every pipeline script the pilot's arms and metrics will execute
- the model/budget policy (defaults, 1 retry, failure -> run invalid)
- the fixed run order R1-C, R1-F, R2-F, R2-C

and computes one manifest sha256 over the sorted (path, sha) list plus the
policy block. Any later drift in any listed file invalidates the run
(verify mode recomputes and compares).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FROZEN_FILES = [
    "contracts/pilot_c_vs_f_frozen_protocol.v2.md",
    "contracts/pilot_r1_r2_selection_addendum.v1.json",
    "contracts/pilot_producer_contract_C.v1.md",
    "contracts/pilot_producer_contract_F.v1.md",
    "scripts/pilot_select_root_sets.py",
    "scripts/pilot_producer_blinding.py",
    "scripts/pilot_metrics.py",
    "scripts/pilot_m5_presentation.py",
    "scripts/pilot_run_manifest.py",
    "scripts/phase13_self_interpretation.py",
    "scripts/phase14_tom_validation.py",
    "scripts/phase15_dream_persistence.py",
    "scripts/tau_text_reasoning_adapter.py",
]

POLICY = {
    "run_order": ["R1-C", "R1-F", "R2-F", "R2-C"],
    "model_policy": "Tau default models and sampling settings, recorded per-call in tau receipts",
    "retry_policy": "at most 1 retry per model call; persistent failure -> run invalid, not patched",
    "budget_rule": "C receives the same number of Tau model calls as F's phase-13/14 stages",
    "render_boundary": "no paid render calls; F's visual artifact is the storyboard frames if no non-paid renderer exists at run time",
    "attrition_rule": "disqualified pair replaced via the same frozen selection script; disqualified pair published as exploratory",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> tuple[dict, list[str]]:
    entries = []
    missing = []
    for rel in FROZEN_FILES:
        path = ROOT / rel
        if not path.exists():
            missing.append(rel)
            continue
        entries.append({"path": rel, "sha256": sha256_file(path)})
    basis = json.dumps({"files": sorted(entries, key=lambda e: e["path"]),
                        "policy": POLICY}, sort_keys=True)
    manifest = {
        "schema": "persona_dream.pilot_run_manifest.v1",
        "files": entries,
        "policy": POLICY,
        "manifest_sha256": hashlib.sha256(basis.encode()).hexdigest(),
    }
    return manifest, missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path,
                        default=ROOT / "contracts/pilot_run_manifest.v1.json")
    parser.add_argument("--verify", action="store_true",
                        help="recompute and compare against the written manifest")
    args = parser.parse_args()

    manifest, missing = build()
    if missing:
        print(f"BLOCKED_PILOT_MANIFEST_FILES_MISSING: {missing}", file=sys.stderr)
        return 2

    if args.verify:
        if not args.out.exists():
            print("BLOCKED_PILOT_MANIFEST_NOT_WRITTEN", file=sys.stderr)
            return 2
        stored = json.loads(args.out.read_text())
        if stored["manifest_sha256"] != manifest["manifest_sha256"]:
            drift = [e["path"] for e in manifest["files"]
                     if e not in stored["files"]]
            print(f"BLOCKED_PILOT_MANIFEST_DRIFT: {drift}", file=sys.stderr)
            return 1
        print(json.dumps({"verified": True,
                          "manifest_sha256": stored["manifest_sha256"]}))
        return 0

    manifest["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    args.out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"written": str(args.out),
                      "files": len(manifest["files"]),
                      "manifest_sha256": manifest["manifest_sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
