#!/usr/bin/env python3
"""Persist the calibration-v3 (face-crop subgate) + rung-v3 outcome to Memory.

Writes two durable governance records through the memory daemon and proves an
exact reread by ``_key`` per the GOAL.md Memory Persistence Contract (exact
reread, not only semantic recall). Reuses the deterministic hash + httpx pattern
from ``persist_reviewer_calibration_memory.py``.

No provider or paid work; the receipts persisted were produced by live scillm
gpt-5.5 vision calls only.
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
REV_REL = f"reports/pipeline-complete/.persona-dream/revisions/{REVISION_ID}"
CALIB_REL = f"{REV_REL}/reviewer_calibration_receipt.v3.json"
RUNG_REL = f"{REV_REL}/acceptance_rung_receipt.v3.json"
CALIB_KEY = f"persona_dream:{RUN_ID}:{REVISION_ID}:reviewer_calibration_v3_face_crop_subgate"
RUNG_KEY = f"persona_dream:{RUN_ID}:{REVISION_ID}:acceptance_rung_v3"


def sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def build_calibration_doc(receipt: dict[str, Any], *, receipt_sha: str, at: str) -> dict[str, Any]:
    s = receipt["summary"]
    critical = list(s.get("critical_known_bad_passed") or [])
    text = (
        f"Persona Dream reviewer calibration v3 for run {RUN_ID} revision {REVISION_ID}. The identity "
        "reviewer (phase07_storyboard_tau_node._run_identity_continuity_review, scillm gpt-5.5) was "
        "augmented with a MANDATORY face-crop identity subgate (identity_face_crop_subgate.py): zoom "
        "into each required face, crop candidate + up to 3 pose-matched reference views, run a "
        "feature-level face-to-face comparison; full-frame review AND subgate must both PASS; failure "
        "code FAIL_FACE_CROP_IDENTITY_MISMATCH; additive, fail-closed, provenance-free. Live 6-case "
        f"negative control outcome {receipt['overall_status']}: known-bad "
        f"{s['known_bad_failed_as_required']}/{s['known_bad_total']} FAIL, positive "
        f"{s['positive_passed_as_required']}/{s['positive_total']} PASS, tamper "
        f"{s['tamper_failed_as_required']}/{s['tamper_total']} FAIL. After the max 3 subgate-prompt "
        f"revisions the CRITICAL residual is known_bad_sb_001 (subtlest near-look-alike) still PASSing "
        "({}): it is not separably discriminable from genuine positives by gpt-5.5 at face-crop scale, "
        "and borderline crop verdicts are unstable run-to-run (SAME/DIFFERENT/empty verdict on identical "
        "inputs). The subgate mechanism DOES work (under the strict first prompt it FAILED sb_001 via "
        "the crop subgate) and closes the full-frame dilution blind spot for non-marginal mismatches, "
        "but a clean calibration PASS was not achieved. A human adjudication bundle was packaged under "
        "reviewer_calibration_v3/human_adjudication_bundle (side-by-side candidate vs pose-matched v3 "
        "reference crops + one-page questions). Downstream steps (8-frame augmented re-review, lane C "
        "sb_003_end regen, supersession/requalification/rung restoration) remain gated on calibration "
        "PASS and are withheld to avoid papering over an uncalibrated rung."
    ).format(", ".join(critical) or "(none)")
    return {
        "_key": CALIB_KEY,
        "schema": "persona_dream.reviewer_calibration_v3_memory.v1",
        "kind": "persona_dream_governance_audit",
        "record_type": "reviewer_calibration_v3_face_crop_subgate",
        "project": "persona-dream",
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "status": receipt["overall_status"],
        "calibration_pass": receipt["calibration_pass"],
        "receipt_relative_path": CALIB_REL,
        "receipt_sha256": receipt_sha,
        "subgate_module": "scripts/identity_face_crop_subgate.py",
        "subgate_failure_code": "FAIL_FACE_CROP_IDENTITY_MISMATCH",
        "subgate_prompt_revisions_used": 3,
        "known_bad_total": s["known_bad_total"],
        "known_bad_failed_as_required": s["known_bad_failed_as_required"],
        "positive_total": s["positive_total"],
        "positive_passed_as_required": s["positive_passed_as_required"],
        "tamper_total": s["tamper_total"],
        "tamper_failed_as_required": s["tamper_failed_as_required"],
        "critical_known_bad_passed": critical,
        "critical_known_bad_passed_count": len(critical),
        "human_adjudication_bundle": f"{REV_REL}/reviewer_calibration_v3/human_adjudication_bundle",
        "memory_write_method": "/upsert",
        "tags": [
            "persona-dream", "governance", "reviewer-calibration", "face-crop-subgate",
            "negative-control", f"run:{RUN_ID}", f"revision:{REVISION_ID}",
            f"verdict:{receipt['overall_status'].lower()}",
        ],
        "retrieval_text": text,
        "observed_at": at,
        "mocked": False, "live": True, "provider_live": False,
        "paid_call_authorized": False, "submitted": False, "actual_provider_call_attempts": 0,
    }


def build_rung_doc(rung: dict[str, Any], *, rung_sha: str, at: str) -> dict[str, Any]:
    text = (
        f"Persona Dream acceptance rung v3 for run {RUN_ID} revision {REVISION_ID}: "
        f"{rung['status']}. The identity reviewer was augmented with a mandatory, unit-tested "
        "face-crop identity subgate contained to the reviewer path (additive, fail-closed, "
        "provenance-free), closing the full-frame dilution blind spot for non-marginal mismatches. "
        "Calibration v3 did not cleanly PASS after 3 subgate-prompt revisions: the subtlest "
        "near-look-alike known-bad (known_bad_sb_001) remains non-discriminable from genuine "
        "positives at gpt-5.5 face-crop scale with run-to-run instability. Rung restoration is "
        "WITHHELD; a human adjudication bundle is packaged. does_not_prove keeps Kling readiness, "
        "media publication, paid authorization, Kling return, and lip-sync-on-return. Superseded "
        "receipt: acceptance_rung_receipt.v2.json (retain-and-mark; no hand-deletion)."
    )
    return {
        "_key": RUNG_KEY,
        "schema": "persona_dream.acceptance_rung_v3_memory.v1",
        "kind": "persona_dream_governance_audit",
        "record_type": "acceptance_rung_v3",
        "project": "persona-dream",
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "status": rung["status"],
        "supersedes": rung.get("supersedes"),
        "receipt_relative_path": RUNG_REL,
        "receipt_sha256": rung_sha,
        "calibration_v3_status": rung["reviewer_calibration_v3"]["overall_status"],
        "human_adjudication_bundle_status": rung["human_adjudication_bundle"]["status"],
        "deferred_steps": rung["gated_and_deferred"]["deferred_steps"],
        "memory_write_method": "/upsert",
        "tags": [
            "persona-dream", "governance", "acceptance-rung", "blocked-on-calibration",
            f"run:{RUN_ID}", f"revision:{REVISION_ID}", f"status:{rung['status'].lower()}",
        ],
        "retrieval_text": text,
        "observed_at": at,
        "mocked": False, "live": True, "provider_live": False,
        "paid_call_authorized": False, "submitted": False, "actual_provider_call_attempts": 0,
    }


EXACT_FIELDS = ("_key", "status", "receipt_sha256")


def _write_and_reread(client: httpx.Client, key: str, document: dict[str, Any]) -> dict[str, Any]:
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

    calib_path = SKILL_ROOT / CALIB_REL
    rung_path = SKILL_ROOT / RUNG_REL
    for p in (calib_path, rung_path):
        if not p.is_file():
            raise SystemExit(f"missing receipt: {p}")
    calib = json.loads(calib_path.read_text(encoding="utf-8"))
    rung = json.loads(rung_path.read_text(encoding="utf-8"))
    calib_sha = sha256_file(calib_path)
    rung_sha = sha256_file(rung_path)
    at = datetime.now(timezone.utc).isoformat()

    calib_doc = build_calibration_doc(calib, receipt_sha=calib_sha, at=at)
    rung_doc = build_rung_doc(rung, rung_sha=rung_sha, at=at)

    timeout = httpx.Timeout(30.0, connect=2.0)
    with httpx.Client(base_url=args.memory_base_url, timeout=timeout) as client:
        got_calib = _write_and_reread(client, CALIB_KEY, calib_doc)
        got_rung = _write_and_reread(client, RUNG_KEY, rung_doc)

    receipt_out = {
        "schema": "persona_dream.reviewer_calibration_v3_memory_receipt.v1",
        "status": "PASS_EXACT_REREAD_CALIBRATION_V3_AND_RUNG",
        "collection": COLLECTION,
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "records": [
            {"memory_key": CALIB_KEY, "status": calib_doc["status"], "receipt_sha256": calib_sha,
             "semantic_sync_state": got_calib.get("semantic_sync_state")},
            {"memory_key": RUNG_KEY, "status": rung_doc["status"], "receipt_sha256": rung_sha,
             "semantic_sync_state": got_rung.get("semantic_sync_state")},
        ],
        "exact_reread_fields": list(EXACT_FIELDS),
        "exact_reread_count": 2,
        "observed_at": at,
        "mocked": False, "live": True,
    }
    out_path = SKILL_ROOT / "reports" / "pipeline-complete" / ".persona-dream" / "state" / \
        f"reviewer_calibration_v3_memory_receipt_{REVISION_ID}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(receipt_out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({**receipt_out, "receipt_path": str(out_path)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
