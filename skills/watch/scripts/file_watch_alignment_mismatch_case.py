#!/usr/bin/env python3
"""File the Bad Santa 02:48 canary evidence case with live findings.

Posts the WEC-BADSANTAMARCUS0248 evidence case through the memory HTTP
boundary with the verdict the live receipts actually support: the provisional
Marcus candidate for seg_0007 is refuted by crop/reference similarity
(every tracker crop scores higher against approved Willie references), the
row text channels do not mention Marcus, and the segment's persisted
audio/clip artifacts were discovered to contain the previous 24-second
window (artifact off-by-one) while frames were overwritten by a later run.

Also upserts the Marcus domain-prior entity, case edges, and updates the
live observation projections so recall reflects the refuted candidate.
Corrections are overlays and case records; no source artifact is mutated.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

ARCH_DIR = Path(__file__).resolve().parents[1] / "docs" / "architecture"
GEN = ARCH_DIR / "generated"
CASE_KEY = "watch_case_bad_santa_marcus_0248_identity"
CASE_ID = "WEC-BADSANTAMARCUS0248"

ROW_TEXT_RECEIPT = (
    GEN / "bad_santa_marcus_0248_row_text_receipts"
    / "watch_row_text_materialization_receipt.bad_santa_marcus.json"
)
CORROBORATION_RECEIPT = (
    GEN / "bad_santa_marcus_0248_row_text_receipts"
    / "watch_text_scene_corroboration_receipt.bad_santa_marcus.json"
)
LOOP_RECEIPT = (
    GEN / "watch_realtime_identity_memory_loop_live_20260718"
    / "watch_realtime_identity_memory_loop_live_receipt.json"
)
DOMAIN_PAYLOAD = GEN / "bad_santa_marcus_0248_upsert_payloads" / "upsert_movie_domain_entities.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-url", default="http://127.0.0.1:8601")
    parser.add_argument("--out-dir", type=Path, default=GEN / "bad_santa_marcus_0248_evidence_case_live")
    args = parser.parse_args()

    now = datetime.now(timezone.utc).isoformat()
    row_text = read_json(ROW_TEXT_RECEIPT)
    loop = read_json(LOOP_RECEIPT)
    similarity = loop["receipts"]["crop_reference_similarity"]

    per_track: dict[str, dict[str, float]] = {}
    crop_meta = {i["qdrant_point_id"]: i for i in loop["receipts"]["crop_embeddings"]["receipts"]}
    for comparison in similarity["comparisons"]:
        score = comparison.get("cosine_similarity")
        if score is None:
            continue
        track = str(crop_meta.get(comparison["crop_qdrant_point_id"], {}).get("track_id"))
        best = per_track.setdefault(track, {})
        name = comparison.get("character_name") or "?"
        best[name] = max(best.get(name, 0.0), score)
    tracks_favoring_willie = sum(
        1 for scores in per_track.values() if scores.get("Willie", 0) > scores.get("Marcus", 0)
    )

    srt_check = row_text.get("srt_disk_cross_check") or {}
    case_doc = {
        "_key": CASE_KEY,
        "case_id": CASE_ID,
        "schema_version": "watch.evidence_case.v1",
        "case_type": "REALTIME_ENTITY_TRACKING",
        "asset_uid": "movie_bad_santa_2003_unrated",
        "question": "find all movie segments with Marcus",
        "claim": "The 02:48-03:12 segment contains Marcus, the mall-store elf character played by Tony Cox.",
        "case_anchor": {
            "entity_ids": ["movie_domain_entities/marcus_bad_santa_2003"],
            "segment_ids": ["seg_0007"],
            "stream_id": "watch_stream_bad_santa_2003",
            "time_range": {"start": "02:48", "end": "03:12", "start_seconds": 168, "end_seconds": 192},
        },
        "decision": {
            "verdict": "REFUTED",
            "failure_codes": [
                "TRACK_IDENTITY_UNCERTAIN",
                "LIVE_OBSERVATION_UNGROUNDED",
                "ARTIFACT_WINDOW_MISALIGNMENT",
            ],
            "reason": (
                "Live crop/reference similarity refutes the provisional Marcus candidate: "
                f"{tracks_favoring_willie}/{len(per_track)} tracker crops score higher against approved "
                "Willie references than approved Marcus references (best Willie score "
                f"{max((s.get('Willie', 0) for s in per_track.values()), default=0):.3f}). "
                "Row text channels (SRT, Whisper, scene marker, VLM) contain zero Marcus/Tony Cox "
                "mentions. The segment's persisted audio/clip artifacts contain the previous "
                "24-second window (bar scene ~02:24-02:48), the on-disk SRT for 02:48-03:12 shows "
                "the mall arrival scene, and frames were overwritten by a later sampling run — the "
                "tracker crops therefore depict the bar scene with Willie and patrons, not Marcus."
            ),
        },
        "artifact_alignment_findings": {
            "audio_clip_off_by_one_window": True,
            "audio_0008_transcribed_content_window": "~02:20-02:44 (Willie bar monologue)",
            "declared_row_window": "02:48-03:12",
            "srt_disk_cross_check_word_overlap": srt_check.get("stored_vs_disk_word_overlap"),
            "frames_overwritten_by_later_run": True,
            "frame_store_mtime_frames": "2026-06-25",
            "frame_store_mtime_clips_audio": "2026-06-18",
            "root_cause": (
                "storage.generate_playable_segments reuses existing segment_/audio_ files by index "
                "without validating their time window, so re-runs with different frame sampling "
                "silently keep stale clips cut for old windows."
            ),
        },
        "evidence_refs": {
            "row_text_materialization_receipt": str(ROW_TEXT_RECEIPT),
            "text_scene_corroboration_receipt": str(CORROBORATION_RECEIPT),
            "realtime_identity_loop_receipt": str(LOOP_RECEIPT),
            "tracker_crop_contact_sheet": str(
                GEN / "bad_santa_marcus_0248_tracking_crops" / "watch_tracking_crops.contact_sheet.jpg"
            ),
            "approved_reference_manifest": str(
                GEN / "bad_santa_marcus_0248_approved_reference_manifest_live"
                / "watch_approved_reference_manifest.marcus_willie.20260718.json"
            ),
        },
        "per_track_best_scores": per_track,
        "domain_refs": ["movie_domain_entities/marcus_bad_santa_2003"],
        "source_truth_policy": (
            "domain refs corroborate entity identity only; Watch frame/clip/track evidence must "
            "support scene presence"
        ),
        "identity_promotion": {
            "marcus_promoted": False,
            "willie_promoted": False,
            "note": (
                "Similarity favors Willie for every track but promotion still requires human "
                "approval; crops remain candidate observations."
            ),
        },
        "retrieval_text": (
            "Watch evidence case WEC-BADSANTAMARCUS0248: claim that Bad Santa segment 02:48-03:12 "
            "contains Marcus is REFUTED. Tracker crops actually show the earlier bar scene with "
            "Willie; audio/clip artifacts were off by one window; row text has no Marcus mention; "
            "crop/reference similarity favors Willie for all tracks."
        ),
        "tags": [
            "watch", "watch_evidence_case", "movie:bad_santa_2003",
            "asset:movie_bad_santa_2003_unrated", "character:marcus", "verdict:refuted",
        ],
        "created_at": "2026-06-27T16:45:00Z",
        "updated_at": now,
    }

    domain_payload = read_json(DOMAIN_PAYLOAD)

    with httpx.Client(base_url=args.memory_url, timeout=httpx.Timeout(30.0), headers={"X-Caller-Skill": "watch"}) as client:
        receipts: list[dict[str, Any]] = []

        def post_upsert(collection: str, documents: list[dict[str, Any]]) -> None:
            response = client.post("/upsert", json={"collection": collection, "documents": documents})
            receipts.append({
                "collection": collection,
                "document_count": len(documents),
                "status_code": response.status_code,
                "ok": 200 <= response.status_code < 300,
                "response_preview": response.text[:300],
            })
            response.raise_for_status()

        post_upsert("movie_domain_entities", domain_payload["documents"])
        post_upsert("watch_evidence_cases", [case_doc])

        observation_keys = loop["receipts"]["memory_recall"]["item_keys"]
        response = client.post(
            "/recall/by-keys", json={"collection": "watch_content", "keys": observation_keys}
        )
        response.raise_for_status()
        projections = response.json().get("documents", [])
        updated_docs = []
        edges = []
        for doc in projections:
            doc = {k: v for k, v in doc.items() if not k.startswith("_") or k == "_key"}
            doc["identity_status"] = "CANDIDATE_REFUTED_BY_REFERENCE_SIMILARITY"
            doc["evidence_case_refs"] = [f"watch_evidence_cases/{CASE_KEY}"]
            doc["answer"] = (
                "Segment seg_0007 tracking observation: the provisional Marcus candidate is REFUTED "
                "by crop/reference similarity (crop scores higher against approved Willie references). "
                "See evidence case WEC-BADSANTAMARCUS0248. The crop depicts the earlier bar scene due "
                "to an artifact window misalignment; identity is not promoted."
            )
            doc["retrieval_text"] = (
                "Watch realtime track observation in Bad Santa seg_0007: Marcus candidate refuted by "
                "reference similarity and evidence case WEC-BADSANTAMARCUS0248; crop shows bar scene "
                "with Willie and patrons; no identity promoted."
            )
            tags = [t for t in doc.get("tags", []) if t != "character:marcus"]
            tags += ["character_candidate_refuted:marcus", "identity:refuted", f"case:{CASE_ID.lower()}"]
            doc["tags"] = tags
            doc["updated_at"] = now
            updated_docs.append(doc)
            edges.append({
                "_key": f"watch_edge_case_obs_{doc['_key'][-12:]}",
                "_from": f"watch_evidence_cases/{CASE_KEY}",
                "_to": f"watch_content/{doc['_key']}",
                "edge_type": "CASE_HAS_OBSERVATION",
                "basis": "live tracker crop observation refuted by reference similarity",
                "schema_version": "watch.evidence_edge.v1",
                "created_at": now,
            })
        post_upsert("watch_content", updated_docs)
        post_upsert("watch_evidence_edges", edges)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema": "watch.evidence_case_live_filing_receipt.v1",
        "status": "CASE_FILED_LIVE",
        "filed_at": now,
        "case_key": CASE_KEY,
        "case_verdict": "REFUTED",
        "upsert_receipts": receipts,
        "updated_observation_count": len(observation_keys),
        "proof_scope": [
            "memory_upsert_receipt_domain_entities",
            "memory_upsert_receipt_evidence_case",
            "observation_projection_refutation_update",
            "case_observation_edges",
        ],
        "claims": {
            "proves": [
                "Domain entity and evidence case were written through memory /upsert with receipts",
                "The 02:48 canary claim is recorded as REFUTED with live evidence references",
                "Observation projections now carry the refuted candidate status for recall",
            ],
            "does_not_prove": [
                "Willie identity promotion (requires human approval)",
                "corrected batch artifacts (requires pipeline re-run)",
            ],
        },
    }
    out_path = args.out_dir / "watch_evidence_case_live_filing_receipt.json"
    out_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"case filed: {CASE_KEY} verdict=REFUTED")
    print(f"receipt: {out_path}")
    for item in receipts:
        print(f"  {item['collection']}: {item['document_count']} docs status={item['status_code']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
