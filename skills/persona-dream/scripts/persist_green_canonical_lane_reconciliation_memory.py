#!/usr/bin/env python3
"""Persist the GREEN_CANONICAL_LANE CI-contract reconciliation to Memory.

Writes a governance record (persona_dream_governance) describing the restore-vs-retire
decision, triage, and final pytest counts, then proves exact reread by _key.
Fail-closed: exact reread mismatch aborts. No paid or live provider calls.
"""
from __future__ import annotations

from pydantic_step_gate import validate_http_json

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

SKILL_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "pipeline-complete"
GOV_COLLECTION = "persona_dream_governance"
RECEIPT_REL = (
    "reports/pipeline-complete/.persona-dream/state/"
    "green_canonical_lane_reconciliation_receipt.v1.json"
)
GOV_KEY = f"persona_dream:{RUN_ID}:green_canonical_lane_ci_contract_reconciliation"
EXACT_FIELDS = ("_key", "schema", "status", "run_id", "receipt_sha256")


def sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def build_gov_doc(sha: str, at: str) -> dict[str, Any]:
    text = (
        "Persona Dream GREEN_CANONICAL_LANE gate CLOSED (2026-07-19): the default pytest suite went from "
        "29 failed / 313 passed to 0 failed / 342 passed, stable across two runs, zero skips. Decision: "
        "RESTORE, not retire. Root cause was incomplete vendoring of the b68bf3d1 (2026-07-11) one-scene "
        "dry-run pipeline harness into skills/persona-dream/: schemas/kling_scene_packet.schema.json was "
        "referenced from day one but never committed; five subagent-contract AGENTS.md files were never "
        "committed; and the work-order writers used REPO=ROOT.parents[1], assuming persona-dream was the "
        "repo root. HANDOFF line 50 documents this dry-run machinery as deliberately preserved and NOT on "
        "the phase-11 live path; phase11_live_request.v1 is a revision/approval-keyed live-activation "
        "abstraction that never references scene_packet, so kling.scene_packet.v1 has no successor to defer "
        "to. Because the affected test files are partially-live, wholesale retirement would have suppressed "
        "currently-green coverage, so no retirement receipt was written. Fixes: (1) authored a faithful "
        "Draft-2020-12 kling_scene_packet.schema.json (value gates stay in the Python validators, not "
        "const-pinned); (2) recreated the omitted fixture PNG and re-locked its sha256 in two receipts; "
        "(3) repointed the writers to skill-owned agents/ and created five real subagent contracts; (4) "
        "corrected the stale PROJECT_KNOWLEDGE header expectation in test_run_sh_read; (5) resynced the "
        "MANIFEST SHA-256 patch-bundle (only the kling schema entry drifted, 4704->4108 bytes; "
        "verify_manifest passes); (6) added ./run.sh test-suite and wired it into sanity.sh as the CI "
        "guard. No revision/rung/qualification gate weakened, no assertion deleted, no paid/live calls."
    )
    return {
        "_key": GOV_KEY,
        "schema": "persona_dream.green_canonical_lane_reconciliation_memory.v1",
        "kind": "persona_dream_governance_audit",
        "record_type": "green_canonical_lane_ci_contract_reconciliation",
        "project": "persona-dream",
        "run_id": RUN_ID,
        "gate": "GREEN_CANONICAL_LANE",
        "status": "PASS_GREEN_CANONICAL_LANE",
        "decision": "restore_not_retire",
        "retirement_receipt": None,
        "receipt_relative_path": RECEIPT_REL,
        "receipt_sha256": sha,
        "baseline_failed": 29,
        "baseline_passed": 313,
        "final_failed": 0,
        "final_passed": 342,
        "final_skipped": 0,
        "runs_confirmed_stable": 2,
        "triage_counts": {
            "restore_omitted_schema": 21,
            "restore_omitted_fixture_media": 2,
            "fix_relocated_agent_contract_path": 7,
            "expectation_drift": 1,
        },
        "ci_guard": "run.sh test-suite (wired into sanity.sh)",
        "memory_write_method": "/upsert",
        "tags": [
            "persona-dream",
            "governance",
            f"run:{RUN_ID}",
            "green-canonical-lane",
            "ci-contract-reconciliation",
            "restore-not-retire",
            "no-paid-call",
        ],
        "retrieval_text": text,
        "observed_at": at,
        "mocked": False,
        "live": True,
        "provider_live": False,
        "paid_call_authorized": False,
        "submitted": False,
        "actual_provider_call_attempts": 0,
    }


def _write_and_reread(client: httpx.Client, collection: str, key: str, document: dict[str, Any]) -> dict[str, Any]:
    client.post("/upsert", json={"collection": collection, "documents": [document]}).raise_for_status()
    reread = client.post("/list", json={"collection": collection, "limit": 2, "filters": {"_key": key}})
    reread.raise_for_status()
    docs = validate_http_json("memory_list", reread.json()).get("documents") or []
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

    receipt_path = SKILL_ROOT / RECEIPT_REL
    sha = sha256_file(receipt_path)
    gov_doc = build_gov_doc(sha, at)

    timeout = httpx.Timeout(30.0, connect=2.0)
    with httpx.Client(base_url=args.memory_base_url, timeout=timeout) as client:
        got = _write_and_reread(client, GOV_COLLECTION, GOV_KEY, gov_doc)

    out = {
        "schema": "persona_dream.green_canonical_lane_reconciliation_memory_receipt.v1",
        "status": "PASS_EXACT_REREAD_GREEN_CANONICAL_LANE",
        "run_id": RUN_ID,
        "collection": GOV_COLLECTION,
        "memory_key": GOV_KEY,
        "semantic_sync_state": got.get("semantic_sync_state"),
        "exact_reread_fields": list(EXACT_FIELDS),
        "receipt_sha256": sha,
        "observed_at": at,
        "mocked": False,
        "live": True,
        "paid_call_authorized": False,
        "submitted": False,
        "actual_provider_call_attempts": 0,
    }
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
