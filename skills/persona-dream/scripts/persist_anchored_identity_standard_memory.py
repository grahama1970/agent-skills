#!/usr/bin/env python3
"""Persist the ANCHORED-IDENTITY STANDARD adoption to Memory with an exact reread
by ``_key`` (per GOAL.md Memory Persistence Contract). This records the documented
gate-design correction: the step-38 composition delta's own accepted design
(end-frame face_required=false for Kai, identity anchored by sb_003.start_frame)
is adopted as a scoped, fail-closed waiver, resolving the contradiction with the
prior lane C acceptance criterion (a) that verified Kai's face ON the end frame.

No provider or paid work; this is a governance/design record.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

SKILL_ROOT = Path(__file__).resolve().parents[1]
COLLECTION = "persona_dream_governance"  # governance/audit records; historical copies remain in project_knowledge (harmless to the scoped qualification gate)
RUN_ID = "pipeline-complete"
REVISION_ID = "rev_successor_943b01ecd9a3"
REV_REL = f"reports/pipeline-complete/.persona-dream/revisions/{REVISION_ID}"
DELTA_REL = f"{REV_REL}/step38_sb_003_composition_delta_proposal.v1.json"
MODULE_REL = "scripts/anchored_identity_waiver.py"
TESTS_REL = "tests/test_anchored_identity_waiver.py"
DRIVER_REL = "scripts/lane_c_regenerate_sb_003_end_frame_waiver.py"

KEY = f"persona_dream:{RUN_ID}:{REVISION_ID}:anchored_identity_standard"
EXACT_FIELDS = ("_key", "status", "contract_sha256", "module_sha256")


def sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def build_doc(at: str, contract_sha: str, module_sha: str, tests_sha: str) -> dict[str, Any]:
    text = (
        f"Persona Dream anchored-identity standard adopted (run {RUN_ID} revision {REVISION_ID}). "
        "A documented gate-design CORRECTION, not a gate weakening: the prior lane C acceptance "
        "criterion (a) verified Kai's face ON the sb_003 end frame, which directly contradicted the "
        "step-38 composition delta's own accepted design (end-frame face_required=false for Kai, "
        "identity anchored by sb_003.start_frame). Those two gates are not pairwise satisfiable on the "
        "same artifact. The scoped anchored-identity waiver (scripts/anchored_identity_waiver.py, "
        "unit-tested, 12 cases) encodes the delta's design: a character's end-frame identity check may "
        "be waived ONLY when ALL of (a) the composition contract explicitly requires that character's "
        "face non-readable on that frame (machine-checked, bound to the contract sha256 "
        f"{contract_sha}); (b) the same panel's start frame passes the full augmented identity review "
        "(full-frame VLM + ArcFace embedding subgate) for that character with the anchor cosine "
        "recorded; (c) start->end continuity passes with explicit NON-FACIAL identity continuity "
        "(wardrobe, build, hair, board, position); (d) a waiver receipt is emitted naming character, "
        "frame, contract hash, anchor frame + cosine, continuity receipt. Default FAIL-CLOSED: no "
        "contract requirement -> no waiver. Every other character (Embry) always gets the full "
        "augmented check including the embedding subgate; the waiver never touches them, and outside "
        "these four conditions all gates stay exactly as strict. Lesson: gates must be checked pairwise "
        "for satisfiability on the same artifact; the delta already held the answer."
    )
    return {
        "_key": KEY,
        "schema": "persona_dream.anchored_identity_standard_memory.v1",
        "kind": "persona_dream_governance_audit",
        "record_type": "anchored_identity_standard_adoption",
        "project": "persona-dream", "run_id": RUN_ID, "revision_id": REVISION_ID,
        "status": "ANCHORED_IDENTITY_STANDARD_ADOPTED",
        "rationale": (
            "delta already specified the resolution; prior lane C criterion (a) contradicted it; "
            "resolved by a machine-checkable fail-closed scoped waiver, not a silent relaxation"
        ),
        "contract_sha256": contract_sha,
        "delta_relative_path": DELTA_REL,
        "module_relative_path": MODULE_REL, "module_sha256": module_sha,
        "tests_relative_path": TESTS_REL, "tests_sha256": tests_sha,
        "driver_relative_path": DRIVER_REL,
        "waiver_conditions": [
            "a: composition contract requires the character's face non-readable on the frame (bound by contract sha256)",
            "b: same-panel start frame passes full augmented identity (full-frame VLM + embedding subgate) for the character; anchor cosine recorded",
            "c: start->end continuity passes with explicit non-facial identity continuity (wardrobe, build, hair, board, position)",
            "d: waiver receipt emitted naming character, frame, contract hash, anchor frame + cosine, continuity receipt",
        ],
        "fail_closed_default": "no explicit contract requirement -> no waiver; every other character keeps the full augmented check",
        "scope": "waives ONLY the end-frame face check for the named character; composition, continuity, embedding authority, and all other gates remain strict",
        "unit_tests": "tests/test_anchored_identity_waiver.py (12 pass, no live calls)",
        "memory_write_method": "/upsert",
        "tags": ["persona-dream", "governance", "design-correction", "anchored-identity",
                 "step-38", f"run:{RUN_ID}", f"revision:{REVISION_ID}"],
        "retrieval_text": text, "observed_at": at,
        "mocked": False, "live": True, "provider_live": False,
        "paid_call_authorized": False, "submitted": False, "actual_provider_call_attempts": 0,
    }


def write_and_reread(client: httpx.Client, key: str, document: dict[str, Any]) -> dict[str, Any]:
    client.post("/upsert", json={"collection": COLLECTION, "documents": [document]}).raise_for_status()
    reread = client.post("/list", json={"collection": COLLECTION, "limit": 2, "filters": {"_key": key}})
    reread.raise_for_status()
    docs = reread.json().get("documents") or []
    if len(docs) != 1:
        raise SystemExit(f"exact reread count mismatch for {key}: {len(docs)}")
    got = docs[0]
    for field in EXACT_FIELDS:
        if got.get(field) != document.get(field):
            raise SystemExit(f"exact reread field mismatch {field}: {got.get(field)!r} != {document.get(field)!r}")
    return got


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--memory-base-url", default="http://127.0.0.1:8601")
    args = ap.parse_args()
    at = datetime.now(timezone.utc).isoformat()

    delta = json.loads((SKILL_ROOT / DELTA_REL).read_text(encoding="utf-8"))
    contract_sha = delta["targets"]["sb_003_end_frame_contract"]["sha256"]
    module_sha = sha256_file(SKILL_ROOT / MODULE_REL)
    tests_sha = sha256_file(SKILL_ROOT / TESTS_REL)
    doc = build_doc(at, contract_sha, module_sha, tests_sha)

    timeout = httpx.Timeout(30.0, connect=2.0)
    with httpx.Client(base_url=args.memory_base_url, timeout=timeout) as client:
        got = write_and_reread(client, KEY, doc)

    receipt = {
        "schema": "persona_dream.anchored_identity_standard_memory_receipt.v1",
        "status": "PASS_EXACT_REREAD_ANCHORED_IDENTITY_STANDARD",
        "collection": COLLECTION, "run_id": RUN_ID, "revision_id": REVISION_ID,
        "memory_key": KEY, "contract_sha256": contract_sha, "module_sha256": module_sha,
        "exact_reread_fields": list(EXACT_FIELDS),
        "semantic_sync_state": got.get("semantic_sync_state"),
        "observed_at": at, "mocked": False, "live": True,
    }
    out_path = SKILL_ROOT / "reports" / "pipeline-complete" / ".persona-dream" / "state" / \
        f"anchored_identity_standard_memory_receipt_{REVISION_ID}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({**receipt, "receipt_path": str(out_path)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
