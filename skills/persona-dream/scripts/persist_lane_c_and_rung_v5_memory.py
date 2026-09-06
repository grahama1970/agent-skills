#!/usr/bin/env python3
"""Persist the Lane C (step 38 fix) outcome, the supersession requalification, and
the acceptance rung v5 governance records to Memory with an exact reread by
``_key`` (not only semantic recall), mirroring the v4 persister's httpx pattern.

Persists whichever of these receipts exist:
  - phase_07_storyboard_live_tau/lane_c_step38_sb_003_end_regen/lane_c_regeneration_receipt.json
  - revision_requalification_supersession_receipt.v1.json
  - revision_activation_receipt.json (post-requalification, PASS_ACTIVE_CONSISTENT)
  - acceptance_rung_receipt.v5.json

No provider or paid work; the Lane C receipt comes from a live GPT Image 2 (codex
-oauth) generation plus live scillm gpt-5.5 vision + InsightFace CPU inference, and
the requalification/activation receipts come from local Memory transactions only.
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
COLLECTION = "persona_dream_governance"  # governance/audit records; historical copies remain in project_knowledge (harmless to the scoped qualification gate)
RUN_ID = "pipeline-complete"
REVISION_ID = "rev_successor_943b01ecd9a3"
REV_REL = f"reports/pipeline-complete/.persona-dream/revisions/{REVISION_ID}"
LANE_C_REL = f"{REV_REL}/phase_07_storyboard_live_tau/lane_c_step38_sb_003_end_regen_waiver/lane_c_regeneration_receipt.json"
SUPERSEDE_REL = f"{REV_REL}/revision_requalification_supersession_receipt.v1.json"
ACTIVATION_REL = f"{REV_REL}/revision_activation_receipt.json"
RUNG_REL = f"{REV_REL}/acceptance_rung_receipt.v5.json"

LANE_C_KEY = f"persona_dream:{RUN_ID}:{REVISION_ID}:38:lane_c_sb_003_end_regen"
REQUAL_KEY = f"persona_dream:{RUN_ID}:{REVISION_ID}:requalification_supersession_v5"
RUNG_KEY = f"persona_dream:{RUN_ID}:{REVISION_ID}:acceptance_rung_v5"
EXACT_FIELDS = ("_key", "status", "receipt_sha256")


def sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _tags(*extra: str) -> list[str]:
    return ["persona-dream", "governance", f"run:{RUN_ID}", f"revision:{REVISION_ID}", *extra]


def build_lane_c_doc(r: dict[str, Any], sha: str, at: str) -> dict[str, Any]:
    acc = r.get("acceptance", {})
    scores = acc.get("embedding_scores")
    text = (
        f"Persona Dream Lane C step 38 fix (run {RUN_ID} revision {REVISION_ID}): {r['status']}. "
        "sb_003_end_frame was regenerated via the Phase C GPT Image 2 lane (codex-oauth, "
        "embry_contact_sheet_v3 + Kai character sheet as reference inputs) applying the "
        "step38_sb_003_composition_delta so Kai's mouth is NOT camera-readable during the 5.0-7.7s "
        "dialogue window while Kai stays identity-recognizable and Embry stays fully readable; "
        "sb_003_start is retained as the identity anchor. Acceptance per attempt required ALL of: "
        "(a) augmented identity review PASS (full-frame gpt-5.5 VLM + deterministic ArcFace embedding "
        f"subgate for both characters; cosines {scores}, threshold {acc.get('embedding_threshold')}), "
        "(b) a composition check proving Kai's mouth is not camera-readable, and (c) continuity "
        "re-review PASS for sb_003_start->end(new) and end(new)->sb_004_start. The prior canonical "
        "phase_c sb_003_end_frame is retained as superseded evidence. No paid/Kling call was made. "
        f"Attempts used: {r.get('attempts_used')}."
    )
    return {
        "_key": LANE_C_KEY, "schema": "persona_dream.lane_c_sb_003_end_regen_memory.v1",
        "kind": "persona_dream_governance_audit", "record_type": "lane_c_sb_003_end_regen",
        "project": "persona-dream", "run_id": RUN_ID, "revision_id": REVISION_ID,
        "status": r["status"], "accepted": r.get("accepted"),
        "receipt_relative_path": LANE_C_REL, "receipt_sha256": sha,
        "frame_id": r.get("frame_id"),
        "new_frame_path": r.get("new_frame_path"), "new_frame_sha256": r.get("new_frame_sha256"),
        "superseded_frame": r.get("superseded_frame"),
        "identity_review": acc.get("identity_review"),
        "identity_authority": acc.get("identity_authority"),
        "embedding_scores": scores, "embedding_threshold": acc.get("embedding_threshold"),
        "composition_status": acc.get("composition_status"),
        "continuity": acc.get("continuity"),
        "attempts_used": r.get("attempts_used"),
        "step38_delta": r.get("step38_delta"),
        "memory_write_method": "/upsert",
        "tags": _tags("lane-c", "step-38", "sb-003-end", f"status:{r['status'].lower()}"),
        "retrieval_text": text, "observed_at": at,
        "mocked": False, "live": True, "provider_live": False,
        "paid_call_authorized": False, "submitted": False, "actual_provider_call_attempts": 0,
    }


def build_requal_doc(sup: dict[str, Any], sup_sha: str, act: dict[str, Any] | None,
                     act_sha: str | None, at: str) -> dict[str, Any]:
    text = (
        f"Persona Dream requalification via sanctioned supersession (run {RUN_ID} revision "
        f"{REVISION_ID}): {sup['status']}. After the Lane C frame was folded into the same immutable "
        "revision id (artifact index rebuilt via rebuild_revision_artifact_bindings.py), the stale "
        "prepare/verify/activation receipts, the queue terminal event, and the old Memory active "
        "pointer were retained-and-marked (archived under superseded/ + a SUPERSEDED Memory snapshot), "
        "an old->new artifact-index entry was appended to the append-only supersession ledger, and the "
        "standard prepare/verify/activate chain re-ran against the rebuilt index. "
        + (f"Activation: {act.get('status')} (index {act.get('local_files',{}).get('artifact_index',{}).get('sha256')})."
           if act else "Activation receipt not present.")
        + " No paid/provider call; local Memory transactions only."
    )
    doc = {
        "_key": REQUAL_KEY, "schema": "persona_dream.requalification_supersession_v5_memory.v1",
        "kind": "persona_dream_governance_audit", "record_type": "requalification_supersession_v5",
        "project": "persona-dream", "run_id": RUN_ID, "revision_id": REVISION_ID,
        "status": (act.get("status") if act else sup["status"]),
        "supersession_status": sup["status"],
        "supersession_receipt_relative_path": SUPERSEDE_REL, "receipt_sha256": sup_sha,
        "old_artifact_index_sha256": sup.get("old_artifact_index_sha256"),
        "new_artifact_index_sha256": sup.get("new_artifact_index_sha256"),
        "archived_files": [a.get("artifact") for a in sup.get("archived_files", [])],
        "superseded_active_pointer": sup.get("superseded_active_pointer"),
        "activation_status": (act.get("status") if act else None),
        "activation_receipt_relative_path": ACTIVATION_REL if act else None,
        "activation_receipt_sha256": act_sha,
        "activation_transaction_id": (act.get("activation_transaction_id") if act else None),
        "memory_write_method": "/upsert",
        "tags": _tags("requalification", "supersession", "activation",
                      f"status:{(act.get('status') if act else sup['status']).lower()}"),
        "retrieval_text": text, "observed_at": at,
        "mocked": False, "live": True, "provider_live": False,
        "paid_call_authorized": False, "submitted": False, "actual_provider_call_attempts": 0,
    }
    return doc


def build_rung_doc(r: dict[str, Any], sha: str, at: str) -> dict[str, Any]:
    text = (
        f"Persona Dream acceptance rung v5 (run {RUN_ID} revision {REVISION_ID}): {r['status']}. "
        "Supersedes v4. The activated acceptance rung is restored: identity is certified by the "
        "deterministic ArcFace embedding subgate (calibration v4 PASS, threshold 0.421), all 8 "
        "successor frames pass the augmented re-review, Lane C regenerated sb_003_end_frame so Kai's "
        "mouth is not camera-readable during 5.0-7.7s (passing augmented identity + composition + "
        "continuity), the rebuilt index was requalified through the sanctioned supersession path, and "
        "activation is PASS_ACTIVE_CONSISTENT. does_not_prove keeps Kling readiness, provider media "
        "publication, publication authorization, paid authorization, provider return, and "
        "lip-sync-on-return (Lane C removes the known cause of the prior step 38 failure by "
        "construction, but proof requires a real return)."
    )
    return {
        "_key": RUNG_KEY, "schema": "persona_dream.acceptance_rung_v5_memory.v1",
        "kind": "persona_dream_governance_audit", "record_type": "acceptance_rung_v5",
        "project": "persona-dream", "run_id": RUN_ID, "revision_id": REVISION_ID,
        "status": r["status"], "supersedes": r.get("supersedes"),
        "receipt_relative_path": RUNG_REL, "receipt_sha256": sha,
        "activation_status": r.get("activation", {}).get("status"),
        "lane_c_status": r.get("lane_c", {}).get("status"),
        "memory_write_method": "/upsert",
        "tags": _tags("acceptance-rung", "rung-v5", f"status:{r['status'].lower()}"),
        "retrieval_text": text, "observed_at": at,
        "mocked": False, "live": True, "provider_live": False,
        "paid_call_authorized": False, "submitted": False, "actual_provider_call_attempts": 0,
    }


def _write_and_reread(client: httpx.Client, key: str, document: dict[str, Any]) -> dict[str, Any]:
    client.post("/upsert", json={"collection": COLLECTION, "documents": [document]}).raise_for_status()
    reread = client.post("/list", json={"collection": COLLECTION, "limit": 2, "filters": {"_key": key}})
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

    records: list[tuple[str, dict[str, Any], str]] = []

    lane_c_path = SKILL_ROOT / LANE_C_REL
    if not lane_c_path.is_file():
        raise SystemExit(f"missing required Lane C receipt: {lane_c_path}")
    lane_c = json.loads(lane_c_path.read_text(encoding="utf-8"))
    lane_c_sha = sha256_file(lane_c_path)
    records.append((LANE_C_KEY, build_lane_c_doc(lane_c, lane_c_sha, at), lane_c_sha))

    sup_path = SKILL_ROOT / SUPERSEDE_REL
    act_path = SKILL_ROOT / ACTIVATION_REL
    if sup_path.is_file():
        sup = json.loads(sup_path.read_text(encoding="utf-8"))
        sup_sha = sha256_file(sup_path)
        act = json.loads(act_path.read_text(encoding="utf-8")) if act_path.is_file() else None
        act_sha = sha256_file(act_path) if act_path.is_file() else None
        records.append((REQUAL_KEY, build_requal_doc(sup, sup_sha, act, act_sha, at), sup_sha))

    rung_path = SKILL_ROOT / RUNG_REL
    if rung_path.is_file():
        rung = json.loads(rung_path.read_text(encoding="utf-8"))
        rung_sha = sha256_file(rung_path)
        records.append((RUNG_KEY, build_rung_doc(rung, rung_sha, at), rung_sha))

    timeout = httpx.Timeout(30.0, connect=2.0)
    out_records = []
    with httpx.Client(base_url=args.memory_base_url, timeout=timeout) as client:
        for key, doc, sha in records:
            got = _write_and_reread(client, key, doc)
            out_records.append({"memory_key": key, "status": doc["status"], "receipt_sha256": sha,
                                "semantic_sync_state": got.get("semantic_sync_state")})

    receipt_out = {
        "schema": "persona_dream.lane_c_requalification_rung_v5_memory_receipt.v1",
        "status": "PASS_EXACT_REREAD_V5", "collection": COLLECTION,
        "run_id": RUN_ID, "revision_id": REVISION_ID, "records": out_records,
        "exact_reread_fields": list(EXACT_FIELDS), "exact_reread_count": len(out_records),
        "observed_at": at, "mocked": False, "live": True,
    }
    out_path = SKILL_ROOT / "reports" / "pipeline-complete" / ".persona-dream" / "state" / \
        f"lane_c_requalification_rung_v5_memory_receipt_{REVISION_ID}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(receipt_out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({**receipt_out, "receipt_path": str(out_path)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
