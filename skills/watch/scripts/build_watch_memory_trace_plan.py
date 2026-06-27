#!/usr/bin/env python3
"""Build a planned Watch memory trace/evidence-case payload.

This command does not write Qdrant, Arango, or memory records. It creates the
bounded planned payload that a later memory pipeline step can apply and prove
with recall.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from watch_reference_hydration import build_memory_trace_plan, load_json, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", required=True)
    parser.add_argument("--observations", required=True, help="JSON array or object with observations")
    parser.add_argument("--identity-evidence", required=True, help="JSON array or object with identity evidence records")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    asset = load_json(args.asset)
    observations_raw = load_json(args.observations)
    evidence_raw = load_json(args.identity_evidence)
    observations = observations_raw.get("observations", observations_raw) if isinstance(observations_raw, dict) else observations_raw
    evidence = evidence_raw.get("identity_evidence", evidence_raw) if isinstance(evidence_raw, dict) else evidence_raw
    plan = build_memory_trace_plan(asset, observations, evidence)
    write_json(args.out, plan)
    print("watch_memory_trace_plan_ok", len(plan["records"]))
    print("write_status", plan["write_status"])
    print("recall_proof_required", plan["recall_proof_required"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
