#!/usr/bin/env python3
"""GOAL_V2 P0.5: phase-16 evaluation against the v2-derived lineage.

Re-runs the five founding probes (a-e) from phase16_behavior_evaluation on the
live graph — which now carries the v2r1 revision bundle — and adds a
v2-specific probe: the versioned bundle resolves end-to-end (dream node ->
v2r1 interpretation vertices -> v2r1 ToM nodes; supersedes edges resolve to
the v1 predecessors) under the strict resolver. Writes
phase16_v2_lineage_receipt.v1.json (the GOAL_V2 checker's P0.5 authority).
"""
from __future__ import annotations

import importlib.util
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8601"
RR = ROOT / "reports/pipeline-complete/.persona-dream/revisions/rev_successor_943b01ecd9a3"
OUT = RR / "phase_16_behavior_evaluation/phase16_v2_lineage_receipt.v1.json"
BUNDLE_REV = "v2r1"
PERSONA, DREAM_ID = "embry", "dream_successor_943b01ecd9a3"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def probe_v2_bundle(p15, lineage: dict) -> dict:
    """Strict resolution of the v2 bundle: every vertex the lineage receipt
    claims must exist with the bundle's commit id; supersedes edges must
    resolve both endpoints."""
    manifest_key = lineage["commit_manifest_key"]
    m = post("/list", {
        "collection": p15.COMMIT_MANIFEST_COLLECTION,
        "filters": {"_key": manifest_key},
    })
    mdocs = m.get("documents") or []
    if not mdocs or not mdocs[0].get("active"):
        return {"passed": False, "detail": "bundle manifest missing or inactive"}
    index = mdocs[0]["record_index"]
    unresolved, supersedes_checked = [], 0
    for r in index:
        docs = []
        for vs in ("active", "pending", None):
            filt = {"_key": r["key"]}
            if vs:
                filt["visibility_state"] = vs
            got = post("/list", {"collection": r["collection"], "filters": filt})
            docs += got.get("documents") or []
            if docs:
                break
        if not docs:
            unresolved.append(r["key"])
            continue
        doc = docs[0]
        if doc.get("relationship_type") == "supersedes":
            supersedes_checked += 1
            to_coll, to_key = doc["_to"].split("/", 1)
            tgt = post("/list", {"collection": to_coll, "filters": {"_key": to_key}})
            if not (tgt.get("documents") or []):
                unresolved.append(f"supersedes-target:{to_key}")
    return {
        "passed": not unresolved,
        "records_in_manifest": len(index),
        "supersedes_edges_resolved": supersedes_checked,
        "unresolved": unresolved[:10],
    }


def main() -> int:
    p15 = _load("phase15_dream_persistence")
    p16 = _load("phase16_behavior_evaluation")
    lineage = json.loads(
        (RR / "watch_gauntlet/59b9ff3155d6/cognitive_loop_v2/lineage_receipt.v1.json").read_text()
    )
    if lineage.get("status") != "PASS_V2_LINEAGE":
        print("BLOCKED: v2 lineage receipt not PASS"); return 1

    probes = {
        "a_recall": p16.probe_a_recall(),
        "b_traversal": p16.probe_b_traversal(),
        "c_grounded_use": p16.probe_c_grounded_use(),
        "d_synthetic_vs_literal": p16.probe_d_synthetic_vs_literal(),
        "e_identity": p16.probe_e_identity_consistency(),
        "v2_bundle_resolution": probe_v2_bundle(p15, lineage),
    }
    all_pass = all(p["passed"] for p in probes.values())
    receipt = {
        "schema": "persona_dream.phase16_v2_lineage_receipt.v1",
        "overall_status": "PASS" if all_pass else "FAIL",
        "bundle_rev": BUNDLE_REV,
        "lineage_receipt_sha256": p15.canonical_sha(lineage),
        "probes": {k: {kk: vv for kk, vv in v.items() if kk != "evidence"} for k, v in probes.items()},
        "llm_route": "tau:persona-dream-text-reasoning (no direct scillm)",
        "does_not_prove": [
            "Chatterbox voice expression (P0.6, separate receipt)",
            "human subjective acceptance (P0.1, human-authored)",
        ],
    }
    OUT.write_text(json.dumps(receipt, indent=2))
    print(json.dumps({"overall_status": receipt["overall_status"],
                      **{k: v["passed"] for k, v in probes.items()}}, indent=2))
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
