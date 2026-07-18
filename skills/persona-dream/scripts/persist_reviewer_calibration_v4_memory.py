#!/usr/bin/env python3
"""Persist the calibration-v4 (deterministic ArcFace embedding subgate) governance
records to Memory with an exact reread by ``_key`` (not only semantic recall),
mirroring the httpx + deterministic-hash pattern of the v3 persister.

Persists whichever of these receipts exist:
  - reviewer_calibration_receipt.v4.json          (always required)
  - reviewer_calibration_v4/successor_rereview/successor_rereview_v4_receipt.json
  - acceptance_rung_receipt.v4.json

No provider or paid work; the persisted receipts come from live InsightFace CPU
inference and (for the re-review) live scillm gpt-5.5 full-frame vision calls.
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
CALIB_REL = f"{REV_REL}/reviewer_calibration_receipt.v4.json"
REREVIEW_REL = f"{REV_REL}/reviewer_calibration_v4/successor_rereview/successor_rereview_v4_receipt.json"
RUNG_REL = f"{REV_REL}/acceptance_rung_receipt.v4.json"
CALIB_KEY = f"persona_dream:{RUN_ID}:{REVISION_ID}:reviewer_calibration_v4_face_embedding_subgate"
REREVIEW_KEY = f"persona_dream:{RUN_ID}:{REVISION_ID}:successor_rereview_v4_embedding"
RUNG_KEY = f"persona_dream:{RUN_ID}:{REVISION_ID}:acceptance_rung_v4"
EXACT_FIELDS = ("_key", "status", "receipt_sha256")


def sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _tags(*extra: str) -> list[str]:
    return ["persona-dream", "governance", f"run:{RUN_ID}", f"revision:{REVISION_ID}", *extra]


def build_calibration_doc(r: dict[str, Any], sha: str, at: str) -> dict[str, Any]:
    th = r["threshold"]
    s = r["summary"]
    text = (
        f"Persona Dream reviewer calibration v4 for run {RUN_ID} revision {REVISION_ID}: "
        f"{r['overall_status']}. Identity verification was moved OFF the unstable gpt-5.5 VLM "
        "face-to-face verdict (v1..v3) and ONTO a deterministic ArcFace metric: InsightFace "
        "buffalo_l (w600k_r50, 512-d L2-normalized) detect->5pt-align->embed->cosine vs a "
        f"calibrated threshold {th['value']}. Genuine same-person floor {th['genuine_edge']}, "
        f"known-bad/tamper ceiling {th['known_bad_edge']}, margin {th['margin']}. Outcome: "
        f"known-bad {s['known_bad_failed_or_reclassified']}/{s['known_bad_total']} FAIL, positives "
        f"{s['positives_passed']}/{s['positives_total']} PASS, tamper {s['tamper_failed']}/"
        f"{s['tamper_total']} FAIL. The near-look-alike known_bad_sb_001 that gpt-5.5 could not "
        "reliably reject (unstable run-to-run) scores Embry cosine 0.323 — metrically a DIFFERENT "
        "face, well below the 0.499 genuine floor; no reclassification needed. positive_control_sb_002, "
        "which v3 wrongly FAILed on the VLM crop, now PASSes (Kai 0.526 > threshold). All 8 accepted "
        "successor frames PASS the embedding subgate (0.525..0.815). The full-frame VLM gate is "
        "retained for scene/wardrobe/composition + face visibility; the VLM face-crop is advisory only. "
        "Failure code FAIL_FACE_EMBEDDING_IDENTITY_MISMATCH records the offending score. This resolves "
        "the human_adjudication_bundle dispute by measurement."
    )
    return {
        "_key": CALIB_KEY, "schema": "persona_dream.reviewer_calibration_v4_memory.v1",
        "kind": "persona_dream_governance_audit",
        "record_type": "reviewer_calibration_v4_face_embedding_subgate",
        "project": "persona-dream", "run_id": RUN_ID, "revision_id": REVISION_ID,
        "status": r["overall_status"], "calibration_pass": r["calibration_pass"],
        "receipt_relative_path": CALIB_REL, "receipt_sha256": sha,
        "identity_authority": "insightface_buffalo_l_cosine",
        "subgate_module": "scripts/identity_face_embedding_subgate.py",
        "subgate_failure_code": "FAIL_FACE_EMBEDDING_IDENTITY_MISMATCH",
        "threshold": th["value"], "genuine_edge": th["genuine_edge"],
        "known_bad_edge": th["known_bad_edge"], "margin": th["margin"],
        "known_bad_total": s["known_bad_total"],
        "known_bad_failed_or_reclassified": s["known_bad_failed_or_reclassified"],
        "positives_total": s["positives_total"], "positives_passed": s["positives_passed"],
        "tamper_total": s["tamper_total"], "tamper_failed": s["tamper_failed"],
        "reclassified_known_bads": r.get("reclassified_known_bads", []),
        "sb_001_embry_cosine": 0.323253,
        "successor_all_pass_embedding": r.get("successor_all_pass_embedding"),
        "supersedes": "reviewer_calibration_receipt.v3.json (VLM face-crop, FAILED)",
        "memory_write_method": "/upsert",
        "tags": _tags("reviewer-calibration", "arcface-embedding", "face-embedding-subgate",
                      f"verdict:{r['overall_status'].lower()}"),
        "retrieval_text": text, "observed_at": at,
        "mocked": False, "live": True, "provider_live": False,
        "paid_call_authorized": False, "submitted": False, "actual_provider_call_attempts": 0,
    }


def build_rereview_doc(r: dict[str, Any], sha: str, at: str) -> dict[str, Any]:
    text = (
        f"Persona Dream successor re-review v4 (run {RUN_ID} revision {REVISION_ID}): "
        f"{r['overall_status']} {r['frames_pass']}/{r['frames_total']} PASS. The 8 accepted "
        "successor frames were re-run through the augmented reviewer (hardened full-frame gpt-5.5 "
        "gate for scene/wardrobe/composition/visibility + the deterministic ArcFace embedding subgate "
        "as the identity authority). Embedding cosine scores recorded per frame; repair_needed="
        f"{r.get('repair_needed')}."
    )
    return {
        "_key": REREVIEW_KEY, "schema": "persona_dream.successor_rereview_v4_memory.v1",
        "kind": "persona_dream_governance_audit", "record_type": "successor_rereview_v4_embedding",
        "project": "persona-dream", "run_id": RUN_ID, "revision_id": REVISION_ID,
        "status": r["overall_status"], "receipt_relative_path": REREVIEW_REL, "receipt_sha256": sha,
        "frames_total": r["frames_total"], "frames_pass": r["frames_pass"],
        "all_pass": r["all_pass"], "repair_needed": r.get("repair_needed", []),
        "frames": [{"frame_id": f["frame_id"], "status": f["status"],
                    "embedding_scores": f["embedding_scores"]} for f in r.get("frames", [])],
        "memory_write_method": "/upsert",
        "tags": _tags("successor-rereview", "arcface-embedding", f"verdict:{r['overall_status'].lower()}"),
        "retrieval_text": text, "observed_at": at,
        "mocked": False, "live": True, "provider_live": False,
        "paid_call_authorized": False, "submitted": False, "actual_provider_call_attempts": 0,
    }


def build_rung_doc(r: dict[str, Any], sha: str, at: str) -> dict[str, Any]:
    text = (
        f"Persona Dream acceptance rung v4 (run {RUN_ID} revision {REVISION_ID}): {r['status']}. "
        "The v3 blocker (REVIEWER_CALIBRATION_FAILED on the near-look-alike known_bad_sb_001) is "
        "RESOLVED by moving identity verification from VLM judgment to deterministic ArcFace cosine "
        "distance (calibration v4 PASS, threshold 0.421, margin 0.156). "
        f"{r.get('rung_note','')} does_not_prove keeps Kling readiness, media publication, paid "
        "authorization, a Kling return, and lip-sync-on-return."
    )
    return {
        "_key": RUNG_KEY, "schema": "persona_dream.acceptance_rung_v4_memory.v1",
        "kind": "persona_dream_governance_audit", "record_type": "acceptance_rung_v4",
        "project": "persona-dream", "run_id": RUN_ID, "revision_id": REVISION_ID,
        "status": r["status"], "supersedes": r.get("supersedes"),
        "receipt_relative_path": RUNG_REL, "receipt_sha256": sha,
        "calibration_v4_status": r.get("reviewer_calibration_v4", {}).get("overall_status"),
        "remaining_steps": r.get("gated_and_deferred", {}).get("deferred_steps", []),
        "memory_write_method": "/upsert",
        "tags": _tags("acceptance-rung", "arcface-embedding", f"status:{r['status'].lower()}"),
        "retrieval_text": text, "observed_at": at,
        "mocked": False, "live": True, "provider_live": False,
        "paid_call_authorized": False, "submitted": False, "actual_provider_call_attempts": 0,
    }


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
    at = datetime.now(timezone.utc).isoformat()

    records: list[tuple[str, dict[str, Any], str]] = []
    calib_path = SKILL_ROOT / CALIB_REL
    if not calib_path.is_file():
        raise SystemExit(f"missing required receipt: {calib_path}")
    calib = json.loads(calib_path.read_text(encoding="utf-8"))
    calib_sha = sha256_file(calib_path)
    records.append((CALIB_KEY, build_calibration_doc(calib, calib_sha, at), calib_sha))

    rr_path = SKILL_ROOT / REREVIEW_REL
    if rr_path.is_file():
        rr = json.loads(rr_path.read_text(encoding="utf-8"))
        rr_sha = sha256_file(rr_path)
        records.append((REREVIEW_KEY, build_rereview_doc(rr, rr_sha, at), rr_sha))

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
        "schema": "persona_dream.reviewer_calibration_v4_memory_receipt.v1",
        "status": "PASS_EXACT_REREAD_V4", "collection": COLLECTION,
        "run_id": RUN_ID, "revision_id": REVISION_ID, "records": out_records,
        "exact_reread_fields": list(EXACT_FIELDS), "exact_reread_count": len(out_records),
        "observed_at": at, "mocked": False, "live": True,
    }
    out_path = SKILL_ROOT / "reports" / "pipeline-complete" / ".persona-dream" / "state" / \
        f"reviewer_calibration_v4_memory_receipt_{REVISION_ID}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(receipt_out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({**receipt_out, "receipt_path": str(out_path)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
