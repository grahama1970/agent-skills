#!/usr/bin/env python3
"""Persist the reviewer calibration negative-control outcome to Memory.

Writes one durable governance record through ``$memory`` and proves an exact
reread by ``_key`` (GOAL.md Memory Persistence Contract: exact reread, not only
semantic recall). Reuses the deterministic hash + httpx pattern already used by
the other persona-dream memory writers (see ``persist_state_clearing_audit_memory.py``).
No provider or paid work; the calibration receipt it persists was produced by
live scillm gpt-5.5 vision calls only.
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
COLLECTION = "project_knowledge"
RUN_ID = "pipeline-complete"
REVISION_ID = "rev_successor_943b01ecd9a3"
RECEIPT_RELPATH = (
    f"reports/pipeline-complete/.persona-dream/revisions/{REVISION_ID}/"
    "reviewer_calibration_receipt.v1.json"
)
MEMORY_KEY = f"persona_dream:{RUN_ID}:{REVISION_ID}:reviewer_calibration_negative_control"

EXACT_FIELDS = (
    "_key",
    "status",
    "calibration_pass",
    "receipt_sha256",
    "known_bad_total",
    "known_bad_failed_as_required",
    "critical_known_bad_passed_count",
)


def sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def build_document(receipt: dict[str, Any], *, receipt_sha: str, observed_at: str) -> dict[str, Any]:
    status = receipt["overall_status"]
    summary = receipt["summary"]
    critical = list(summary.get("critical_known_bad_passed") or [])
    retrieval_text = (
        "Persona Dream reviewer calibration negative-control for run "
        f"{RUN_ID} revision {REVISION_ID}. The SAME Phase C actual-pixel identity reviewer "
        "(phase07_storyboard_tau_node._run_identity_continuity_review, scillm gpt-5.5 image_url, "
        "schema persona_dream.identity_continuity_review.v1) was run against known-bad ground "
        "truth (stale montage-derived Phase 07 frames marked STALE_IDENTITY_SOURCE_SUPERSEDED, "
        "derived from the montage that FAILED identity qualification "
        f"FAIL_IDENTITY_REFERENCE_INCONSISTENT), accepted Phase C positive controls, and a tamper "
        f"case (accepted frame + wrong Embry reference). Outcome {status}: "
        f"{summary['known_bad_failed_as_required']}/{summary['known_bad_total']} known-bad frames "
        "FAILED as required; both positive controls PASSED; the tamper case FAILED (contract IS "
        "reference-grounded). CRITICAL: known-bad frames "
        f"{', '.join(critical) or '(none)'} PASSED identity review — the reviewer's identity "
        "threshold is too coarse (accepts 'adult woman, brown hair, navy top ... closely enough' "
        "without enforcing specific facial identity/age to embry_contact_sheet_v3), so the Phase C "
        "8/8 first-attempt PASS is NOT trustworthy as evidence of specific-identity fidelity. "
        "Result reproduced across two independent live runs. Hardening proposed (specific-identity "
        "gate + age-consistency clause + enumerated facial features), contained to the reviewer "
        "prompt contract, NOT implemented (would invalidate Phase C receipts; human-gated re-review)."
    )
    return {
        "_key": MEMORY_KEY,
        "schema": "persona_dream.reviewer_calibration_memory.v1",
        "kind": "persona_dream_governance_audit",
        "record_type": "reviewer_calibration_negative_control",
        "project": "persona-dream",
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "status": status,
        "calibration_pass": receipt["calibration_pass"],
        "receipt_relative_path": RECEIPT_RELPATH,
        "receipt_sha256": receipt_sha,
        "reviewer_function": receipt["reviewer"]["function"],
        "reviewer_model": receipt["reviewer"]["model"],
        "review_schema": receipt["reviewer"]["review_schema"],
        "known_bad_total": summary["known_bad_total"],
        "known_bad_failed_as_required": summary["known_bad_failed_as_required"],
        "positive_total": summary["positive_total"],
        "positive_passed_as_required": summary["positive_passed_as_required"],
        "tamper_total": summary["tamper_total"],
        "tamper_failed_as_required": summary["tamper_failed_as_required"],
        "critical_known_bad_passed": critical,
        "critical_known_bad_passed_count": len(critical),
        "failure_reasons": receipt.get("failure_reasons", []),
        "proposed_hardening_status": receipt.get("proposed_hardening", {}).get("status"),
        "memory_write_method": "/upsert",
        "claims": receipt.get("claims", {}),
        "tags": [
            "persona-dream",
            "governance",
            "reviewer-calibration",
            "negative-control",
            f"run:{RUN_ID}",
            f"revision:{REVISION_ID}",
            f"verdict:{status.lower()}",
        ],
        "retrieval_text": retrieval_text,
        "observed_at": observed_at,
        "mocked": False,
        "live": True,
        "provider_live": False,
        "paid_call_authorized": False,
        "submitted": False,
        "actual_provider_call_attempts": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-base-url", default="http://127.0.0.1:8601")
    args = parser.parse_args()

    receipt_path = SKILL_ROOT / RECEIPT_RELPATH
    if not receipt_path.is_file():
        raise SystemExit(f"calibration receipt missing: {receipt_path}")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt_sha = sha256_file(receipt_path)
    observed_at = datetime.now(timezone.utc).isoformat()
    document = build_document(receipt, receipt_sha=receipt_sha, observed_at=observed_at)

    timeout = httpx.Timeout(30.0, connect=2.0)
    with httpx.Client(base_url=args.memory_base_url, timeout=timeout) as client:
        write = client.post("/upsert", json={"collection": COLLECTION, "documents": [document]})
        write.raise_for_status()

        reread = client.post(
            "/list",
            json={"collection": COLLECTION, "limit": 2, "filters": {"_key": MEMORY_KEY}},
        )
        reread.raise_for_status()
        observed = reread.json().get("documents") or []
        if len(observed) != 1:
            raise SystemExit(f"exact reread count mismatch for {MEMORY_KEY}: {len(observed)}")
        got = observed[0]
        for field in EXACT_FIELDS:
            if got.get(field) != document.get(field):
                raise SystemExit(
                    f"exact reread field mismatch for {field}: {got.get(field)!r} != {document.get(field)!r}"
                )

    receipt_out = {
        "schema": "persona_dream.reviewer_calibration_memory_receipt.v1",
        "status": "PASS_EXACT_REREAD_REVIEWER_CALIBRATION",
        "collection": COLLECTION,
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "memory_key": MEMORY_KEY,
        "calibration_status": document["status"],
        "receipt_sha256": receipt_sha,
        "exact_reread_count": 1,
        "exact_reread_fields": list(EXACT_FIELDS),
        "semantic_sync_state": got.get("semantic_sync_state"),
        "qdrant_collection": got.get("qdrant_collection"),
        "qdrant_point_id": got.get("qdrant_point_id"),
        "memory_write_method": "/upsert",
        "observed_at": observed_at,
        "mocked": False,
        "live": True,
    }
    receipt_out_path = (
        SKILL_ROOT
        / "reports"
        / "pipeline-complete"
        / ".persona-dream"
        / "state"
        / f"reviewer_calibration_memory_receipt_{REVISION_ID}.json"
    )
    receipt_out_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_out_path.write_text(json.dumps(receipt_out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({**receipt_out, "receipt_path": str(receipt_out_path)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
