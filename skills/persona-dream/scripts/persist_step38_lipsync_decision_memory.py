#!/usr/bin/env python3
"""Persist the step 38 visible-speaker lip-sync decision packet to Memory.

Writes one durable governance/decision record through ``$memory`` and proves an
exact reread by ``_key`` (GOAL.md Memory Persistence Contract: exact reread, not
only semantic recall). Reuses the deterministic hash + httpx pattern already used
by ``persist_state_clearing_audit_memory.py``. No provider or paid work.
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
PACKET_RELPATH = (
    f"reports/pipeline-complete/.persona-dream/revisions/{REVISION_ID}/"
    "step38_lipsync_decision_packet.v1.json"
)
PACKET_MD_RELPATH = (
    f"reports/pipeline-complete/.persona-dream/revisions/{REVISION_ID}/"
    "step38_lipsync_decision_packet.v1.md"
)
DELTA_RELPATH = (
    f"reports/pipeline-complete/.persona-dream/revisions/{REVISION_ID}/"
    "step38_sb_003_composition_delta_proposal.v1.json"
)
MEMORY_KEY = f"persona_dream:{RUN_ID}:{REVISION_ID}:38:step38_lipsync_decision"


def sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def build_document(packet: dict[str, Any], *, packet_sha: str, md_sha: str, delta_sha: str, observed_at: str) -> dict[str, Any]:
    decision = packet["decision"]
    retrieval_text = (
        "Persona Dream step 38 visible-speaker lip-sync decision for run "
        f"{RUN_ID} revision {REVISION_ID}. The frozen predecessor return "
        "(request sha256:ca90ba9f) post-muxed the exact Kai line 'If we paddle "
        "now, we're cutting across the lineup.' at 5.00-7.70s; forced alignment "
        "PASSED but SB_003 is a two-shot with Kai's mouth camera-readable during "
        "the measured speech, so step 38 fails FAIL_VISIBLE_SPEAKER_NOT_LIPSYNCED. "
        "Three lanes were evaluated: A Kling lip-sync API (paid, post-return "
        "repair, video_url or origin_task_id, JWT HS256, ~$0.084/clip, blocked by "
        "the 10.041667s>10s fal cap and the one-person two-shot constraint) = "
        "FALLBACK; B generate_audio=true = REJECT because provider audio cannot "
        "carry the exact canonical line in the consented Kai voice and breaks the "
        "immutable exact-transcript requirement; C SB_003 composition change "
        "(non-paid: keep the start frame as identity anchor, regenerate the end "
        "frame + per-segment motion so Kai delivers his cue looking out toward the "
        "lineup with his mouth not camera-readable during 5.0-7.7s) = PRIMARY "
        "because it is the only lane that changes the next paid call's inputs so "
        "the return passes step 38 by construction while preserving identity, "
        "story intent, and the post-mux consented-voice audio lane. No paid call "
        "made or authorized."
    )
    return {
        "_key": MEMORY_KEY,
        "schema": "persona_dream.step38_lipsync_decision_memory.v1",
        "kind": "persona_dream_pipeline_decision",
        "record_type": "step38_visible_speaker_lipsync_decision",
        "project": "persona-dream",
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "step_no": 38,
        "step_slug": "final-assembly-movie-lane",
        "status": packet["status"],
        "failure_code": packet["problem_statement"]["failure_code"],
        "beat": packet["problem_statement"]["beat"],
        "canonical_line": packet["problem_statement"]["canonical_line"],
        "spoken_interval_seconds": packet["problem_statement"]["spoken_interval_seconds"],
        "primary_lane": decision["primary_lane"],
        "primary_lane_name": decision["primary_lane_name"],
        "fallback_lane": decision["fallback_lane"],
        "fallback_lane_name": decision["fallback_lane_name"],
        "rejected_lane": decision["rejected_lane"],
        "human_decision_required": decision["human_decision_required"],
        "decision_packet_relative_path": PACKET_RELPATH,
        "decision_packet_sha256": packet_sha,
        "decision_packet_md_relative_path": PACKET_MD_RELPATH,
        "decision_packet_md_sha256": md_sha,
        "sb_003_composition_delta_relative_path": DELTA_RELPATH,
        "sb_003_composition_delta_sha256": delta_sha,
        "web_sources": packet["web_sources"],
        "memory_write_method": "/upsert",
        "claims": packet["claims"],
        "tags": [
            "persona-dream",
            "pipeline-decision",
            "step-38",
            "visible-speaker-lipsync",
            "kling-lipsync-api",
            f"run:{RUN_ID}",
            f"revision:{REVISION_ID}",
            f"primary-lane:{decision['primary_lane'].lower()}",
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

    packet_path = SKILL_ROOT / PACKET_RELPATH
    md_path = SKILL_ROOT / PACKET_MD_RELPATH
    delta_path = SKILL_ROOT / DELTA_RELPATH
    for p in (packet_path, md_path, delta_path):
        if not p.is_file():
            raise SystemExit(f"required artifact missing: {p}")

    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet_sha = sha256_file(packet_path)
    md_sha = sha256_file(md_path)
    delta_sha = sha256_file(delta_path)
    observed_at = datetime.now(timezone.utc).isoformat()
    document = build_document(
        packet, packet_sha=packet_sha, md_sha=md_sha, delta_sha=delta_sha, observed_at=observed_at
    )

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
        for field in (
            "_key",
            "status",
            "primary_lane",
            "fallback_lane",
            "rejected_lane",
            "decision_packet_sha256",
            "sb_003_composition_delta_sha256",
        ):
            if got.get(field) != document.get(field):
                raise SystemExit(
                    f"exact reread field mismatch for {field}: {got.get(field)!r} != {document.get(field)!r}"
                )

    receipt = {
        "schema": "persona_dream.step38_lipsync_decision_memory_receipt.v1",
        "status": "PASS_EXACT_REREAD_STEP38_LIPSYNC_DECISION",
        "collection": COLLECTION,
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "memory_key": MEMORY_KEY,
        "decision_packet_sha256": packet_sha,
        "decision_packet_md_sha256": md_sha,
        "sb_003_composition_delta_sha256": delta_sha,
        "primary_lane": document["primary_lane"],
        "fallback_lane": document["fallback_lane"],
        "rejected_lane": document["rejected_lane"],
        "exact_reread_count": 1,
        "semantic_sync_state": got.get("semantic_sync_state"),
        "qdrant_collection": got.get("qdrant_collection"),
        "qdrant_point_id": got.get("qdrant_point_id"),
        "memory_write_method": "/upsert",
        "observed_at": observed_at,
        "mocked": False,
        "live": True,
    }
    receipt_path = (
        SKILL_ROOT
        / "reports"
        / "pipeline-complete"
        / ".persona-dream"
        / "state"
        / f"step38_lipsync_decision_memory_receipt_{REVISION_ID}.json"
    )
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({**receipt, "receipt_path": str(receipt_path)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
