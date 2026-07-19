#!/usr/bin/env python3
"""Persist the Phase 11 provider-media-binding stale-media-lock blocker to Memory.

Writes a governance blocker record (persona_dream_governance) and a
pipeline-step-shaped blocker record (persona_dream_pipeline_steps), then proves
exact reread by _key for both. Fail-closed: exact reread mismatch aborts.
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
RUN_ID = "pipeline-complete"
REVISION_ID = "rev_successor_943b01ecd9a3"
GOV_COLLECTION = "persona_dream_governance"
STEP_COLLECTION = "persona_dream_pipeline_steps"

RECEIPT_REL = (
    "reports/pipeline-complete/.persona-dream/revisions/rev_successor_943b01ecd9a3/"
    "phase_11_submit_return/preflight/phase11_provider_media_binding_blocker_receipt.v1.json"
)
BOOTSTRAP_REL = (
    "reports/pipeline-complete/.persona-dream/revisions/rev_successor_943b01ecd9a3/"
    "phase_11_submit_return/preflight/phase11_payload_binding_bootstrap_blocker.json"
)

GOV_KEY = f"persona_dream:{RUN_ID}:{REVISION_ID}:28:phase11_provider_media_binding_blocker"
STEP_KEY = f"persona_dream:{RUN_ID}:{REVISION_ID}:28:kling_scene_packet"

EXACT_FIELDS = ("_key", "schema", "status", "run_id", "revision_id", "receipt_sha256")


def sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _tags(*extra: str) -> list[str]:
    return ["persona-dream", "blocked", f"run:{RUN_ID}", f"revision:{REVISION_ID}", *extra]


def build_gov_doc(sha: str, boot_sha: str, at: str) -> dict[str, Any]:
    text = (
        f"Persona Dream Phase 11 provider-media-binding BLOCKER (run {RUN_ID} revision {REVISION_ID}): "
        "BLOCKED_PHASE11_PROVIDER_MEDIA_BINDING_STALE_MEDIA_LOCK. The zero-call payload-binding bootstrap "
        "fails closed with BLOCKED_PHASE11_MEDIA_LOCK_HASH: the revision artifact index binds the accepted, "
        "identity-certified phase_c_successor_regen start frame for sb_001.start_frame "
        "(sha256:135564ca...) but phase_08_media_lock/storyboard_media_lock_manifest.json still LOCKS the "
        "predecessor-identical frame (sha256:bbd7a631...) at wrong-worktree, non-revision-scoped paths. "
        "index != media lock, so compile -> provider final gate -> paid authorization -> single submit are "
        "unreachable. The accepted successor start frames (135564ca / aebcbd90 / 9046059c / 2c3211f2) and "
        "the lane C waiver canonical sb_003.end_frame (9f8fb8c9) were certified by acceptance_rung_receipt.v5 "
        "(PASS_ACCEPTANCE_RUNG) and reviewer_calibration_v4 ArcFace subgate, but the phase_08 media lock was "
        "never regenerated for the accepted START frames. Fail-closed: NO provider request compiled and NO "
        "paid Kling/fal call made; the single authorized submit was NOT spent on the stale, out-of-scope "
        "predecessor-identical media. Next action (human/upstream decision): regenerate phase_08 media lock "
        "to the accepted frames + re-run supersession/prepare/verify/activate --supersede requalification, "
        "then run the phase 11 chain. Operator authorization (2026-07-18, Graham) recorded verbatim and "
        "UNCONSUMED in the receipt."
    )
    return {
        "_key": GOV_KEY,
        "schema": "persona_dream.phase11_provider_media_binding_blocker_memory.v1",
        "kind": "persona_dream_governance_audit",
        "record_type": "phase11_provider_media_binding_blocker",
        "project": "persona-dream",
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "status": "BLOCKED_PHASE11_PROVIDER_MEDIA_BINDING_STALE_MEDIA_LOCK",
        "gate_code": "BLOCKED_PHASE11_MEDIA_LOCK_HASH",
        "receipt_relative_path": RECEIPT_REL,
        "receipt_sha256": sha,
        "bootstrap_capture_relative_path": BOOTSTRAP_REL,
        "bootstrap_capture_sha256": boot_sha,
        "accepted_start_frames_sha256": {
            "sb_001.start_frame": "sha256:135564cad9c40718322e9f13d347b6829ecbd9ab2197cbddc70262deb72e227d",
            "sb_002.start_frame": "sha256:aebcbd907c999d64ba4e7effd4f9f95e75e8e094e6deee605f5fb6f5a2e4606b",
            "sb_003.start_frame": "sha256:9046059c87f35a6be56f166415979a25bfb72f9c51293a1434eb0f7ac8a1118c",
            "sb_004.start_frame": "sha256:2c3211f225eea31a8091569ec10f68a87d7f324e12f04653c5efb1084c97a26e",
        },
        "stale_locked_start_frames_sha256": {
            "sb_001.start_frame": "sha256:bbd7a63110b1c42af94e682ae93bf055bbe1c84e48468b3470a2032db70d09bb",
            "sb_002.start_frame": "sha256:3f7a1d4e9def3f6f0e726ef9cd25b1f5dfeacbf0eabd4e43e871479f7a219b6a",
            "sb_003.start_frame": "sha256:471513b449fb6c39b576360064d831c357bfa0233bb7a96a84ee1d7ef3eaaa20",
            "sb_004.start_frame": "sha256:8fcd2045314c7c464c920bd6e7bf370a4cf90bcfd529bcf8e22f7100e5994a29",
        },
        "waiver_canonical_sb_003_end_frame": "sha256:9f8fb8c93e5382667ab7be1ebf4001ff702500117baca2837b33f2bb228bf20a",
        "operator_authorization_consumed": False,
        "memory_write_method": "/upsert",
        "tags": _tags("phase-11", "media-lock-stale", "human-decision-required", "no-paid-call"),
        "retrieval_text": text,
        "observed_at": at,
        "mocked": False,
        "live": True,
        "provider_live": False,
        "paid_call_authorized": False,
        "submitted": False,
        "actual_provider_call_attempts": 0,
    }


def build_step_doc(sha: str, at: str) -> dict[str, Any]:
    return {
        "_key": STEP_KEY,
        "schema": "persona_dream.pipeline_step_record.v1",
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "step_no": 28,
        "step_slug": "kling_scene_packet",
        "step_name": "Kling Scene Packet",
        "status": "BLOCKED_PHASE11_PROVIDER_MEDIA_BINDING_STALE_MEDIA_LOCK",
        "inputs": {
            "artifact_index_sha256": "sha256:85c92446f1c9e138b58b96d0e02de8c88657907a3fc7bf2d2f6774cdf6b42720",
            "phase_08_media_lock": "phase_08_media_lock/storyboard_media_lock_manifest.json",
            "phase_10_payload": "phase_10_provider_contract/final_provider_payload_by_panel.json",
        },
        "outputs": {
            "compiled_request": None,
            "blocker_receipt_relative_path": RECEIPT_REL,
        },
        "receipt_paths": [RECEIPT_REL, BOOTSTRAP_REL],
        "artifact_hashes": {"blocker_receipt_sha256": sha},
        "request_hash": None,
        "provider_task_id": None,
        "memory_write_method": "/upsert",
        "memory_write_receipt": "this record",
        "exact_reread_receipt": "verified by _key /list",
        "claims": {
            "proves": [
                "phase_08 media lock is stale relative to the accepted successor frames",
                "phase 11 binding gate fails closed; no request compiled; no paid call",
            ],
            "does_not_prove": [
                "Kling readiness",
                "provider media publication of accepted frames",
                "a successor provider return",
            ],
        },
        "blocker": (
            "BLOCKED_PHASE11_MEDIA_LOCK_HASH: revision artifact index binds accepted phase_c_successor_regen "
            "start frames but phase_08 media lock still locks predecessor-identical frames. Next: regenerate "
            "phase_08 media lock to the accepted frames + supersession/requalification (human/upstream "
            "decision), then run the phase 11 compile->authorize->submit chain."
        ),
        "receipt_sha256": sha,
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

    receipt_path = SKILL_ROOT / RECEIPT_REL
    boot_path = SKILL_ROOT / BOOTSTRAP_REL
    sha = sha256_file(receipt_path)
    boot_sha = sha256_file(boot_path)

    gov_doc = build_gov_doc(sha, boot_sha, at)
    step_doc = build_step_doc(sha, at)

    timeout = httpx.Timeout(30.0, connect=2.0)
    out_records = []
    with httpx.Client(base_url=args.memory_base_url, timeout=timeout) as client:
        got_gov = _write_and_reread(client, GOV_COLLECTION, GOV_KEY, gov_doc)
        out_records.append({
            "collection": GOV_COLLECTION, "memory_key": GOV_KEY, "status": gov_doc["status"],
            "semantic_sync_state": got_gov.get("semantic_sync_state"),
        })
        got_step = _write_and_reread(client, STEP_COLLECTION, STEP_KEY, step_doc)
        out_records.append({
            "collection": STEP_COLLECTION, "memory_key": STEP_KEY, "status": step_doc["status"],
            "semantic_sync_state": got_step.get("semantic_sync_state"),
        })

    receipt_out = {
        "schema": "persona_dream.phase11_media_binding_blocker_memory_receipt.v1",
        "status": "PASS_EXACT_REREAD_PHASE11_MEDIA_BINDING_BLOCKER",
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "records": out_records,
        "exact_reread_fields": list(EXACT_FIELDS),
        "exact_reread_count": len(out_records),
        "blocker_receipt_sha256": sha,
        "observed_at": at,
        "mocked": False,
        "live": True,
        "paid_call_authorized": False,
        "submitted": False,
        "actual_provider_call_attempts": 0,
    }
    out_path = SKILL_ROOT / "reports" / "pipeline-complete" / ".persona-dream" / "state" / \
        f"phase11_media_binding_blocker_memory_receipt_{REVISION_ID}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(receipt_out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({**receipt_out, "receipt_path": str(out_path)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
