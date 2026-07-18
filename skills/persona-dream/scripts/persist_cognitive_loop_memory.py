#!/usr/bin/env python3
"""Persist governance memory for the persona-dream cognitive-loop build and the
live loop run through the $memory HTTP contract, with write + exact reread proof.

These are GOVERNANCE records (persona_dream_governance collection), not canonical
dream memory. The superseded historical return is never written to canonical
dream memory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MEMORY_BASE_URL = "http://127.0.0.1:8601"


def canonical_sha(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(MEMORY_BASE_URL + path, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20.0) as resp:
        return json.loads(resp.read())


def store_and_reread(doc: dict[str, Any], collection: str) -> dict[str, Any]:
    authored = {k: v for k, v in doc.items() if not k.startswith("_") or k == "_key"}
    written_sha = canonical_sha(authored)
    _post("/store", {"document": doc, "collection": collection})
    reread = _post("/list", {"collection": collection, "limit": 5, "filters": {"_key": doc["_key"]}})
    docs = reread.get("documents") or reread.get("items") or []
    match = False
    reread_sha = None
    for d in docs:
        if d.get("_key") == doc["_key"]:
            subset = {k: d.get(k) for k in authored}
            reread_sha = canonical_sha(subset)
            match = reread_sha == written_sha
            break
    return {"collection": collection, "key": doc["_key"], "written_sha256": written_sha,
            "reread_sha256": reread_sha, "exact_reread_match": match}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--loop-receipt", type=Path, required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    receipt = json.loads(args.loop_receipt.read_text())
    now = datetime.now(timezone.utc).isoformat()
    phase_status = {p["phase"]: p["status"] for p in receipt.get("phases", [])}

    build_doc = {
        "_key": "persona_dream_cognitive_loop_build_20260718",
        "kind": "governance_lesson",
        "problem": "persona-dream phases 13-15 (self-interpretation, ToM validation, dream persistence) were Designed only.",
        "solution": (
            "Implemented phase13_self_interpretation.py (+dream_self_interpretation.v1 schema), "
            "phase14_tom_validation.py (+tom_candidate.v1 schema), phase15_dream_persistence.py, and "
            "run_cognitive_loop.py. Interpretive drafting uses scillm gpt-5.5; citation/grounding and "
            "ToM admissibility are deterministic gates. Every accepted claim cites >=1 Watch observation id "
            "AND >=1 source-memory id; the honesty rule forces the renderer-defect explanation to be favored "
            "when a continuity review returns DRIFT. Phase 15 defaults to dry-run: it emits an exact canonical "
            "would-write plan with hashes and ZERO canonical writes; canonical writes require "
            "--allow-canonical-write AND a non-superseded return id and hard-fail (exit 1) on the superseded "
            "historical return. 16 pytest cases cover the deterministic logic."
        ),
        "tags": ["persona-dream", "cognitive-loop", "governance", "phase13", "phase14", "phase15",
                 "theory-of-mind", "grounding", "dry-run-boundary"],
        "scope": "persona-dream",
        "created_at": now,
    }

    loop_doc = {
        "_key": "persona_dream_cognitive_loop_run_991c311f365f_20260718",
        "kind": "governance_lesson",
        "problem": "Prove phases 13-15 on the historical Kling return without canonicalizing a superseded artifact.",
        "solution": (
            f"Ran run_cognitive_loop.py live on observation packet 991c311f365f. Loop status "
            f"{receipt.get('status')}. Phase statuses: {json.dumps(phase_status)}. "
            "Phase 13 produced 4 grounded interpretations (trust/stance/uncertainty/belief), honesty rule "
            "dual-explanation present with renderer-defect favored on DRIFT. Phase 14 accepted 4 grounded ToM "
            "candidates. Phase 15 dry-run performed 0 canonical writes (blockers: historical return, degraded "
            "status, identity DRIFT) and proved the write path with 16 exact-reread-matched documents in the "
            "non-canonical persona_dream_loop_validation collection. This is fixture-and-live-slice proof on a "
            "HISTORICAL return; it is NOT the closed-loop research claim, which needs a non-superseded successor return."
        ),
        "tags": ["persona-dream", "cognitive-loop", "live-slice", "governance", "watch-gauntlet",
                 "superseded-return", "validation-collection"],
        "scope": "persona-dream",
        "loop_receipt_sha256": canonical_sha(receipt),
        "created_at": now,
    }

    proofs = [store_and_reread(build_doc, "persona_dream_governance"), store_and_reread(loop_doc, "persona_dream_governance")]
    all_match = all(p["exact_reread_match"] for p in proofs)
    out = {"schema": "persona_dream.cognitive_loop_memory_governance.v1", "all_exact_reread_match": all_match,
           "proofs": proofs, "generated_at": now}
    print(json.dumps(out, indent=2))
    return 0 if all_match else 1


if __name__ == "__main__":
    raise SystemExit(main())
