#!/usr/bin/env python3
"""Persist reviewer-hardening remediation records to Memory (GOAL.md contract).

Writes durable ``$memory`` records for the reviewer-leniency remediation and
proves an exact reread by ``_key`` for each (exact reread, not only semantic
recall). Reuses the deterministic hash + httpx pattern from
``persist_step38_lipsync_decision_memory.py``.

Records (only those whose source artifact exists are written):
  * reviewer calibration v2 (hardened negative-control outcome)
  * hardened re-review of the 8 successor frames
  * acceptance rung v2 (if present)

No provider or paid work.
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


def sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _upsert_and_reread(client: httpx.Client, document: dict[str, Any], check_fields: list[str]) -> dict[str, Any]:
    key = document["_key"]
    w = client.post("/upsert", json={"collection": COLLECTION, "documents": [document]})
    w.raise_for_status()
    r = client.post("/list", json={"collection": COLLECTION, "limit": 2, "filters": {"_key": key}})
    r.raise_for_status()
    docs = validate_http_json("memory_list", r.json()).get("documents") or []
    if len(docs) != 1:
        raise SystemExit(f"exact reread count mismatch for {key}: {len(docs)}")
    got = docs[0]
    for f in check_fields:
        if got.get(f) != document.get(f):
            raise SystemExit(f"exact reread field mismatch for {f}: {got.get(f)!r} != {document.get(f)!r}")
    return got


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--memory-base-url", default="http://127.0.0.1:8601")
    args = ap.parse_args()

    calib_path = SKILL_ROOT / REV_REL / "reviewer_calibration_receipt.v2.json"
    rereview_path = SKILL_ROOT / REV_REL / "hardened_rereview" / "hardened_rereview_summary.v2.json"
    rung_path = SKILL_ROOT / REV_REL / "acceptance_rung_receipt.v2.json"

    observed_at = _now()
    written: list[dict[str, Any]] = []
    timeout = httpx.Timeout(30.0, connect=2.0)
    with httpx.Client(base_url=args.memory_base_url, timeout=timeout) as client:

        # --- Calibration v2 ---
        if calib_path.is_file():
            calib = json.loads(calib_path.read_text(encoding="utf-8"))
            hardened_prompt_sha = None
            for c in calib.get("cases", []):
                if c.get("review_prompt_sha256"):
                    hardened_prompt_sha = c["review_prompt_sha256"]
                    break
            key = f"persona_dream:{RUN_ID}:{REVISION_ID}:07r:reviewer_calibration_v2"
            doc = {
                "_key": key,
                "schema": "persona_dream.reviewer_calibration_v2_memory.v1",
                "kind": "persona_dream_pipeline_gate",
                "record_type": "reviewer_calibration_v2",
                "project": "persona-dream",
                "run_id": RUN_ID,
                "revision_id": REVISION_ID,
                "step_no": 7,
                "step_slug": "reviewer-calibration-hardened",
                "status": calib.get("overall_status"),
                "calibration_pass": calib.get("calibration_pass"),
                "hardened_review_prompt_sha256": hardened_prompt_sha,
                "summary": calib.get("summary"),
                "failure_reasons": calib.get("failure_reasons"),
                "receipt_relative_path": f"{REV_REL}/reviewer_calibration_receipt.v2.json",
                "receipt_sha256": sha256_file(calib_path),
                "memory_write_method": "/upsert",
                "claims": calib.get("claims"),
                "tags": ["persona-dream", "reviewer-calibration", "hardened-reviewer",
                         "negative-control", f"run:{RUN_ID}", f"revision:{REVISION_ID}"],
                "retrieval_text": (
                    "Persona Dream hardened reviewer calibration v2 negative-control for run "
                    f"{RUN_ID} revision {REVISION_ID}. After hardening _identity_review_prompt "
                    "(specific-identity gate, age-consistency clause, feature grounding, "
                    "complexion/adversarial divergence, fail-closed on uncertainty) the negative "
                    f"control was re-run live (scillm gpt-5.5 image_url). Outcome: {calib.get('overall_status')}. "
                    "Hardened prompt sha256 " + str(hardened_prompt_sha) + "."
                ),
                "observed_at": observed_at,
                "mocked": False, "live": True, "provider_live": False, "paid_call_authorized": False,
            }
            _upsert_and_reread(client, doc, ["_key", "status", "hardened_review_prompt_sha256", "receipt_sha256"])
            written.append({"key": key, "status": doc["status"]})

        # --- Hardened re-review of 8 frames ---
        if rereview_path.is_file():
            rr = json.loads(rereview_path.read_text(encoding="utf-8"))
            key = f"persona_dream:{RUN_ID}:{REVISION_ID}:07r:hardened_rereview_8frames"
            doc = {
                "_key": key,
                "schema": "persona_dream.hardened_rereview_memory.v1",
                "kind": "persona_dream_pipeline_gate",
                "record_type": "hardened_rereview_successor_frames",
                "project": "persona-dream",
                "run_id": RUN_ID,
                "revision_id": REVISION_ID,
                "step_no": 7,
                "step_slug": "hardened-rereview-successor-frames",
                "status": rr.get("overall_status"),
                "frames_pass_hardened": rr.get("frames_pass_hardened"),
                "frames_fail_hardened": rr.get("frames_fail_hardened"),
                "hardened_prompt_sha256": (rr.get("reviewer") or {}).get("hardened_prompt_sha256"),
                "receipt_relative_path": f"{REV_REL}/hardened_rereview/hardened_rereview_summary.v2.json",
                "receipt_sha256": sha256_file(rereview_path),
                "per_frame": [
                    {"frame_id": f["frame_id"], "hardened_status": f["hardened_status"],
                     "image_sha256": f["image_sha256"]}
                    for f in rr.get("frames", [])
                ],
                "memory_write_method": "/upsert",
                "prior_result": rr.get("prior_result"),
                "tags": ["persona-dream", "hardened-rereview", "identity-review",
                         f"run:{RUN_ID}", f"revision:{REVISION_ID}"],
                "retrieval_text": (
                    "Persona Dream hardened re-review of the 8 Phase C successor storyboard frames "
                    f"for run {RUN_ID} revision {REVISION_ID}. The prior Phase C 8/8 first-attempt PASS "
                    "was under the pre-hardening reviewer prompt; re-reviewed on actual pixels under the "
                    f"hardened reviewer. Outcome: {rr.get('overall_status')}; failing frames: "
                    f"{rr.get('frames_fail_hardened')}."
                ),
                "observed_at": observed_at,
                "mocked": False, "live": True, "provider_live": False, "paid_call_authorized": False,
            }
            _upsert_and_reread(client, doc, ["_key", "status", "receipt_sha256"])
            written.append({"key": key, "status": doc["status"]})

        # --- Acceptance rung v2 (if produced) ---
        if rung_path.is_file():
            rung = json.loads(rung_path.read_text(encoding="utf-8"))
            key = f"persona_dream:{RUN_ID}:{REVISION_ID}:rung:acceptance_rung_v2"
            doc = {
                "_key": key,
                "schema": "persona_dream.acceptance_rung_v2_memory.v1",
                "kind": "persona_dream_pipeline_gate",
                "record_type": "acceptance_rung_v2",
                "project": "persona-dream",
                "run_id": RUN_ID,
                "revision_id": REVISION_ID,
                "status": rung.get("status"),
                "rung": rung.get("rung"),
                "receipt_relative_path": f"{REV_REL}/acceptance_rung_receipt.v2.json",
                "receipt_sha256": sha256_file(rung_path),
                "claims": rung.get("claims"),
                "memory_write_method": "/upsert",
                "tags": ["persona-dream", "acceptance-rung", "hardened-reviewer",
                         f"run:{RUN_ID}", f"revision:{REVISION_ID}"],
                "retrieval_text": (
                    "Persona Dream acceptance rung v2 for run "
                    f"{RUN_ID} revision {REVISION_ID}, resting on the hardened reviewer "
                    f"(status {rung.get('status')})."
                ),
                "observed_at": observed_at,
                "mocked": False, "live": True, "provider_live": False, "paid_call_authorized": False,
            }
            _upsert_and_reread(client, doc, ["_key", "status", "receipt_sha256"])
            written.append({"key": key, "status": doc["status"]})

    receipt = {
        "schema": "persona_dream.reviewer_hardening_memory_receipt.v1",
        "status": "PASS_EXACT_REREAD_REVIEWER_HARDENING",
        "collection": COLLECTION,
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "records_written": written,
        "observed_at": observed_at,
        "mocked": False, "live": True,
    }
    out = SKILL_ROOT / REV_REL.replace(f"revisions/{REVISION_ID}", "state") / f"reviewer_hardening_memory_receipt_{REVISION_ID}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({**receipt, "receipt_path": str(out)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
