#!/usr/bin/env python3
"""Persist the BLOCKED Lane C (step 38 fix) outcome to Memory with an exact reread
by ``_key``. Per GOAL.md Memory Persistence Contract, a blocked step must still
write a durable record with the concrete blocker and the next required action.

Persists:
  - the Lane C regeneration receipt (FAILED_LANE_C_ATTEMPTS_EXHAUSTED)
  - the step 38 Lane C blocker receipt (gate conflict + next actions)

No provider or paid work; the Lane C evidence came from live GPT Image 2
(codex-oauth) generations + live scillm gpt-5.5 vision + InsightFace CPU inference.
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
LANE_C_REL = f"{REV_REL}/phase_07_storyboard_live_tau/lane_c_step38_sb_003_end_regen/lane_c_regeneration_receipt.json"
BLOCKER_REL = f"{REV_REL}/step38_lane_c_blocker_receipt.v1.json"

LANE_C_KEY = f"persona_dream:{RUN_ID}:{REVISION_ID}:38:lane_c_sb_003_end_regen"
BLOCKER_KEY = f"persona_dream:{RUN_ID}:{REVISION_ID}:38:lane_c_blocker"
EXACT_FIELDS = ("_key", "status", "receipt_sha256")


def sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _tags(*extra: str) -> list[str]:
    return ["persona-dream", "governance", "blocked", f"run:{RUN_ID}", f"revision:{REVISION_ID}", *extra]


def build_lane_c_doc(r: dict[str, Any], sha: str, at: str) -> dict[str, Any]:
    table = [
        {"attempt": a["attempt"], "identity": a.get("review_status"),
         "embedding_scores": a.get("embedding_scores"),
         "composition": a.get("composition_status"),
         "continuity": [c.get("status") for c in (a.get("continuity") or [])]}
        for a in r.get("attempts", [])
    ]
    text = (
        f"Persona Dream Lane C step 38 fix (run {RUN_ID} revision {REVISION_ID}): {r['status']}. "
        "sb_003_end_frame was regenerated live via the Phase C GPT Image 2 lane (codex-oauth, "
        "embry_contact_sheet_v3 + Kai character sheet reference inputs) applying the step38 composition "
        "delta across a bounded 5-attempt failure-aware loop. NO attempt satisfied all three acceptance "
        "checks at once (augmented identity review PASS for both + composition proving Kai's mouth not "
        "camera-readable + continuity PASS for both affected pairs). Attempt 1 hid the mouth by arm "
        "occlusion (composition PASS) but failed the fail-closed full-frame identity VLM; attempts 2-5 "
        "kept a verifiable face (identity PASS, embeddings 0.64-0.81; attempts 4-5 also passed BOTH "
        "continuity pairs) but the mouth stayed camera-readable (composition FAIL). Fail-closed: the "
        "frame is NOT accepted, the frozen revision and its canonical phase_c sb_003_end_frame are "
        "untouched, and requalification + rung restoration were NOT attempted. No paid/Kling call."
    )
    return {
        "_key": LANE_C_KEY, "schema": "persona_dream.lane_c_sb_003_end_regen_memory.v1",
        "kind": "persona_dream_governance_audit", "record_type": "lane_c_sb_003_end_regen",
        "project": "persona-dream", "run_id": RUN_ID, "revision_id": REVISION_ID,
        "status": r["status"], "accepted": r.get("accepted"),
        "receipt_relative_path": LANE_C_REL, "receipt_sha256": sha,
        "attempts_used": r.get("attempts_used"), "attempt_table": table,
        "superseded_frame": r.get("superseded_frame"),
        "step38_delta": r.get("step38_delta"),
        "blocker": "5 attempts exhausted; augmented-identity vs mouth-not-camera-readable gate conflict",
        "memory_write_method": "/upsert",
        "tags": _tags("lane-c", "step-38", "sb-003-end", f"status:{r['status'].lower()}"),
        "retrieval_text": text, "observed_at": at,
        "mocked": False, "live": True, "provider_live": False,
        "paid_call_authorized": False, "submitted": False, "actual_provider_call_attempts": 0,
    }


def build_blocker_doc(b: dict[str, Any], sha: str, at: str) -> dict[str, Any]:
    text = (
        f"Persona Dream step 38 Lane C BLOCKER (run {RUN_ID} revision {REVISION_ID}): {b['status']}. "
        "Root cause: the hardened full-frame identity reviewer is FAIL-CLOSED and needs Kai's lower face "
        "(nose/mouth/chin/jaw) visible to ground specific-identity features, which directly conflicts "
        "with the composition requirement that Kai's mouth NOT be camera-readable during 5.0-7.7s. GPT "
        "Image 2 could not hit the narrow overlap in 5 bounded attempts (attempts 4-5 were near misses: "
        "identity + both continuity pairs PASS, only composition FAIL). Next action requires a HUMAN "
        "decision: (1) a further targeted non-paid regeneration for the near-miss moderate-three-quarter "
        "pose; OR (2) formally adopt the delta's own end-frame provision (face_required=false, identity "
        "anchored by sb_003.start_frame) as the acceptance standard for the end frame -- a gate-design "
        "change that must be human-authorized, not made silently by an agent; OR (3) paid lane A on the "
        "return. The acceptance rung remains at v4; it is NOT restored. No paid/Kling call."
    )
    return {
        "_key": BLOCKER_KEY, "schema": "persona_dream.step38_lane_c_blocker_memory.v1",
        "kind": "persona_dream_governance_audit", "record_type": "step38_lane_c_blocker",
        "project": "persona-dream", "run_id": RUN_ID, "revision_id": REVISION_ID,
        "status": b["status"], "receipt_relative_path": BLOCKER_REL, "receipt_sha256": sha,
        "root_cause": b.get("root_cause"),
        "next_required_action_human_decision": b.get("next_required_action_human_decision"),
        "current_rung": b.get("disposition", {}).get("current_rung"),
        "rung_restored": False,
        "memory_write_method": "/upsert",
        "tags": _tags("step-38", "lane-c-blocker", "human-decision-required"),
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
    lane_c = json.loads(lane_c_path.read_text(encoding="utf-8"))
    lane_c_sha = sha256_file(lane_c_path)
    records.append((LANE_C_KEY, build_lane_c_doc(lane_c, lane_c_sha, at), lane_c_sha))

    blocker_path = SKILL_ROOT / BLOCKER_REL
    blocker = json.loads(blocker_path.read_text(encoding="utf-8"))
    blocker_sha = sha256_file(blocker_path)
    records.append((BLOCKER_KEY, build_blocker_doc(blocker, blocker_sha, at), blocker_sha))

    timeout = httpx.Timeout(30.0, connect=2.0)
    out_records = []
    with httpx.Client(base_url=args.memory_base_url, timeout=timeout) as client:
        for key, doc, sha in records:
            got = _write_and_reread(client, key, doc)
            out_records.append({"memory_key": key, "status": doc["status"], "receipt_sha256": sha,
                                "semantic_sync_state": got.get("semantic_sync_state")})

    receipt_out = {
        "schema": "persona_dream.lane_c_blocker_memory_receipt.v1",
        "status": "PASS_EXACT_REREAD_LANE_C_BLOCKER", "collection": COLLECTION,
        "run_id": RUN_ID, "revision_id": REVISION_ID, "records": out_records,
        "exact_reread_fields": list(EXACT_FIELDS), "exact_reread_count": len(out_records),
        "observed_at": at, "mocked": False, "live": True,
    }
    out_path = SKILL_ROOT / "reports" / "pipeline-complete" / ".persona-dream" / "state" / \
        f"lane_c_blocker_memory_receipt_{REVISION_ID}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(receipt_out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({**receipt_out, "receipt_path": str(out_path)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
