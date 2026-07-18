#!/usr/bin/env python3
"""Persist the Lane C (step 38) PASS under the anchored-identity waiver AND the
requalification blocker to Memory with an exact reread by ``_key`` (per GOAL.md
Memory Persistence Contract). Updates the lane C outcome record to PASS and records
the requalification blocker (pre-existing qualification-vs-governance memory-record
-space collision) fail-closed.

No provider or paid work; the Lane C evidence came from live GPT Image 2
(codex-oauth) generation + live scillm gpt-5.5 vision + InsightFace CPU inference.
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
LANE_C_REL = f"{REV_REL}/phase_07_storyboard_live_tau/lane_c_step38_sb_003_end_regen_waiver/lane_c_regeneration_receipt.json"
BLOCKER_REL = f"{REV_REL}/step38_lane_c_waiver_requalification_blocker_receipt.v1.json"

LANE_C_KEY = f"persona_dream:{RUN_ID}:{REVISION_ID}:38:lane_c_sb_003_end_regen"
BLOCKER_KEY = f"persona_dream:{RUN_ID}:{REVISION_ID}:38:lane_c_waiver_requalification_blocker"
EXACT_FIELDS = ("_key", "status", "receipt_sha256")


def sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _tags(*extra: str) -> list[str]:
    return ["persona-dream", "governance", f"run:{RUN_ID}", f"revision:{REVISION_ID}", *extra]


def build_lane_c_doc(r: dict[str, Any], sha: str, at: str) -> dict[str, Any]:
    acc = r.get("acceptance", {})
    anchor = r.get("identity_anchor_start_frame", {})
    embry_cos = None
    try:
        embry_cos = acc["embry_review"]["face_embedding_subgate"]["entity_results"][0]["best_cosine"]
    except Exception:
        pass
    text = (
        f"Persona Dream Lane C step 38 fix under the anchored-identity waiver (run {RUN_ID} "
        f"revision {REVISION_ID}): {r['status']} on attempt 1. sb_003_end_frame regenerated via the "
        "Phase C GPT Image 2 lane (codex-oauth, embry_contact_sheet_v3 + Kai character sheet reference "
        "inputs) applying the step38 composition delta under the scoped anchored-identity waiver. "
        "Acceptance (all four): composition PASS (Kai's mouth NOT camera-readable, Embry readable, Kai "
        f"present matching build); Embry end-frame FULL augmented identity PASS (full-frame VLM + ArcFace "
        f"embedding subgate, cosine {embry_cos}); Kai anchored-identity waiver GRANTED (contract flag by "
        f"sha256 + start-frame Kai full augmented PASS, anchor cosine {anchor.get('kai_embedding_cosine')} "
        "+ non-facial start->end continuity PASS + waiver receipt emitted); BOTH continuity pairs PASS "
        "(sb_003 start->end, end->sb_004 start). The step-38 gate-design contradiction is resolved by the "
        "delta's own recorded design (end-frame Kai face_required=false, anchored by the unchanged start "
        "frame + non-facial continuity), not a gate weakening; Embry keeps the full augmented check. The "
        "index rebuild + supersession promoting the new frame ran cleanly, but prepare/verify/activate "
        "requalification is BLOCKED (see the requalification blocker record) so the rung is not yet "
        "restored to v5. No paid/Kling call."
    )
    return {
        "_key": LANE_C_KEY, "schema": "persona_dream.lane_c_sb_003_end_regen_memory.v2",
        "kind": "persona_dream_governance_audit", "record_type": "lane_c_sb_003_end_regen",
        "project": "persona-dream", "run_id": RUN_ID, "revision_id": REVISION_ID,
        "status": r["status"], "accepted": r.get("accepted"), "standard": "anchored_identity_waiver",
        "receipt_relative_path": LANE_C_REL, "receipt_sha256": sha,
        "attempts_used": r.get("attempts_used"),
        "new_frame_sha256": r.get("new_frame_sha256"),
        "kai_anchor_cosine": anchor.get("kai_embedding_cosine"),
        "embry_end_frame_cosine": embry_cos,
        "waiver_receipt": (acc.get("waiver_receipt") if isinstance(acc, dict) else None),
        "superseded_frame": r.get("superseded_frame"),
        "memory_write_method": "/upsert",
        "tags": _tags("lane-c", "step-38", "sb-003-end", "anchored-identity-waiver", "pass"),
        "retrieval_text": text, "observed_at": at,
        "mocked": False, "live": True, "provider_live": False,
        "paid_call_authorized": False, "submitted": False, "actual_provider_call_attempts": 0,
    }


def build_blocker_doc(b: dict[str, Any], sha: str, at: str) -> dict[str, Any]:
    text = (
        f"Persona Dream step 38 Lane C waiver REQUALIFICATION BLOCKER (run {RUN_ID} revision "
        f"{REVISION_ID}): {b['status']}. Lane C PASSED under the anchored-identity waiver and the "
        "artifact-index rebuild + supersession promoting the new frame ran cleanly, but "
        "prepare/verify/activate could NOT reach PASS_ACTIVE_CONSISTENT: it is blocked fail-closed by a "
        "PRE-EXISTING memory-record-space collision. The prepare gate lists project_knowledge filtered by "
        "(run_id, revision_id) and requires EXACTLY the 27 qualification records, but 14 governance/audit "
        "records (13 predating this session) share that space; the Memory daemon exposes no deletion "
        "primitive (no /delete endpoint; /query forbids destructive AQL REMOVE), so the governance records "
        "cannot be relocated. Per 'factual blocked outcome beats forced pass', requalification was NOT "
        "forced (no audit deletion, no gate edit); the revision was restored to its prior ACTIVE_CONSISTENT "
        "baseline (artifact index 06496a6a) and the acceptance rung REMAINS at v4. Resolving the collision "
        "is a human/design decision (governance records to a distinct collection/namespace, or a sanctioned "
        "clearing step, or scope the prepare exact-match to qualification record_types). No paid/Kling call."
    )
    return {
        "_key": BLOCKER_KEY, "schema": "persona_dream.step38_lane_c_waiver_requalification_blocker_memory.v1",
        "kind": "persona_dream_governance_audit", "record_type": "step38_lane_c_waiver_requalification_blocker",
        "project": "persona-dream", "run_id": RUN_ID, "revision_id": REVISION_ID,
        "status": b["status"], "receipt_relative_path": BLOCKER_REL, "receipt_sha256": sha,
        "requalification_blocker": b.get("requalification_blocker"),
        "disposition": b.get("disposition"),
        "next_required_action": b.get("next_required_action"),
        "rung_restored": False, "current_rung": "acceptance_rung_receipt.v4.json",
        "memory_write_method": "/upsert",
        "tags": _tags("step-38", "lane-c-waiver", "requalification-blocker", "human-decision-required"),
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

    records: list[tuple[str, dict[str, Any], str]] = []
    lane_c_path = SKILL_ROOT / LANE_C_REL
    lane_c = json.loads(lane_c_path.read_text(encoding="utf-8"))
    lane_c_sha = sha256_file(lane_c_path)
    records.append((LANE_C_KEY, build_lane_c_doc(lane_c, lane_c_sha, at), lane_c_sha))

    blocker_path = SKILL_ROOT / BLOCKER_REL
    blocker = json.loads(blocker_path.read_text(encoding="utf-8"))
    blocker_sha = sha256_file(blocker_path)
    records.append((BLOCKER_KEY, build_blocker_doc(blocker, blocker_sha, at), blocker_sha))

    out_records = []
    with httpx.Client(base_url=args.memory_base_url, timeout=httpx.Timeout(30.0, connect=2.0)) as client:
        for key, doc, sha in records:
            got = write_and_reread(client, key, doc)
            out_records.append({"memory_key": key, "status": doc["status"], "receipt_sha256": sha,
                                "semantic_sync_state": got.get("semantic_sync_state")})

    receipt_out = {
        "schema": "persona_dream.lane_c_waiver_outcome_memory_receipt.v1",
        "status": "PASS_EXACT_REREAD_LANE_C_WAIVER_OUTCOME", "collection": COLLECTION,
        "run_id": RUN_ID, "revision_id": REVISION_ID, "records": out_records,
        "exact_reread_fields": list(EXACT_FIELDS), "exact_reread_count": len(out_records),
        "observed_at": at, "mocked": False, "live": True,
    }
    out_path = SKILL_ROOT / "reports" / "pipeline-complete" / ".persona-dream" / "state" / \
        f"lane_c_waiver_outcome_memory_receipt_{REVISION_ID}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(receipt_out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({**receipt_out, "receipt_path": str(out_path)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
