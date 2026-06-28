#!/usr/bin/env python3
"""Run the Watch realtime identity persistence loop for tracker events.

This script is intentionally strict about claim boundaries:

- YOLO/ByteTrack events are observations.
- Crop embeddings are written to Qdrant.
- Metadata and Qdrant pointers are written through memory /upsert.
- Recall proof is collected through memory /recall.
- Named identity remains unsupported unless approved reference embeddings and
  crop/reference similarity receipts exist.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


WATCH_NAMESPACE_UUID = uuid.UUID("7a17ce7d-9dbf-5e8a-bc40-8ef36138c84d")
DEFAULT_ARCH_DIR = Path(__file__).resolve().parents[1] / "docs" / "architecture"
DEFAULT_EVENTS = (
    DEFAULT_ARCH_DIR
    / "generated"
    / "bad_santa_marcus_0248_yolo_bytetrack"
    / "watch_tracker_event_log.bad_santa_marcus.yolo_bytetrack.jsonl"
)
DEFAULT_CROPS = (
    DEFAULT_ARCH_DIR
    / "generated"
    / "bad_santa_marcus_0248_tracking_crops"
    / "watch_tracking_crops.bad_santa_marcus.json"
)
DEFAULT_OUT_DIR = DEFAULT_ARCH_DIR / "generated" / "watch_realtime_identity_memory_loop_live"
WATCH_SKILL_DIR = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--crop-manifest", type=Path, default=DEFAULT_CROPS)
    parser.add_argument("--reference-manifest", type=Path, help="Optional approved reference image manifest")
    parser.add_argument("--reference-approval-receipt", type=Path, help="Optional concrete reference approval receipt")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--embedding-url", default=os.getenv("EMBEDDING_MULTIMODAL_URL", "http://127.0.0.1:8603"))
    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"))
    parser.add_argument("--memory-url", default=os.getenv("MEMORY_DAEMON_URL", "http://127.0.0.1:8601"))
    parser.add_argument("--crop-collection", default="watch_track_crop_embeddings_jina_v5_1024")
    parser.add_argument("--reference-collection", default="watch_reference_image_embeddings_jina_v5_1024")
    parser.add_argument("--dimensions", type=int, default=1024)
    parser.add_argument("--limit-crops", type=int, default=0)
    args = parser.parse_args()

    started_at = utc_now()
    events = read_jsonl(args.events)
    crop_manifest = read_json(args.crop_manifest)
    crops = crop_manifest.get("crops") or []
    if args.limit_crops > 0:
        crops = crops[: args.limit_crops]
    if not events:
        raise ValueError(f"no tracker events: {args.events}")
    if not crops:
        raise ValueError(f"no tracking crops: {args.crop_manifest}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    service_receipts = probe_services(args)

    crop_embedding_receipt = embed_and_write_crops(
        crops=crops,
        args=args,
    )
    reference_approval_receipt = load_reference_approval_receipt(args.reference_approval_receipt)
    reference_receipt = embed_and_write_references(args.reference_manifest, reference_approval_receipt, args)
    similarity_receipt = build_similarity_receipts(crop_embedding_receipt, reference_receipt, args)
    memory_receipt = upsert_memory_records(
        events=events,
        crops=crops,
        crop_embedding_receipt=crop_embedding_receipt,
        similarity_receipt=similarity_receipt,
        memory_url=args.memory_url,
    )
    recall_receipt = run_recall_proof(memory_receipt, args.memory_url)

    summary = {
        "schema": "watch.realtime_identity_memory_loop_live_receipt.v1",
        "status": loop_status(crop_embedding_receipt, memory_receipt, recall_receipt),
        "started_at": started_at,
        "completed_at": utc_now(),
        "source_events": display_path(args.events),
        "source_crop_manifest": display_path(args.crop_manifest),
        "source_reference_manifest": display_path(args.reference_manifest) if args.reference_manifest else None,
        "source_reference_approval_receipt": display_path(args.reference_approval_receipt) if args.reference_approval_receipt else None,
        "service_receipts": service_receipts,
        "counts": {
            "event_count": len(events),
            "crop_count": len(crops),
            "crop_embedding_write_count": crop_embedding_receipt["counts"]["qdrant_written"],
            "reference_embedding_write_count": reference_receipt["counts"]["qdrant_written"],
            "reference_approval_receipt_count": reference_receipt["counts"].get("approval_receipt_count", 0),
            "similarity_receipt_count": similarity_receipt["counts"]["comparison_count"],
            "memory_document_count": memory_receipt["counts"]["document_count"],
            "recall_item_count": recall_receipt["counts"]["item_count"],
        },
        "receipts": {
            "crop_embeddings": crop_embedding_receipt,
            "reference_approval": reference_approval_receipt,
            "reference_embeddings": reference_receipt,
            "crop_reference_similarity": similarity_receipt,
            "memory_upsert": memory_receipt,
            "memory_recall": recall_receipt,
        },
        "identity_claim": {
            "status": "IDENTITY_INCONCLUSIVE",
            "reason": (
                "YOLO/ByteTrack observations and crop embeddings exist, but named identity "
                "requires approved reference embeddings, similarity receipts, negative controls, "
                "text/scene corroboration, and memory recall proof."
            ),
        },
    }
    summary_path = args.out_dir / "watch_realtime_identity_memory_loop_live_receipt.json"
    write_json(summary_path, summary)
    print("watch_realtime_identity_memory_loop_receipt", summary["status"])
    print("events", len(events))
    print("crops", len(crops))
    print("crop_qdrant_writes", crop_embedding_receipt["counts"]["qdrant_written"])
    print("memory_documents", memory_receipt["counts"]["document_count"])
    print("recall_items", recall_receipt["counts"]["item_count"])
    print("receipt", summary_path)
    return 0 if summary["status"] in {"LIVE_RECEIPTS_WRITTEN", "LIVE_RECEIPTS_PARTIAL"} else 2


def probe_services(args: argparse.Namespace) -> dict[str, Any]:
    receipts: dict[str, Any] = {}
    with httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
        receipts["embedding"] = get_json(client, f"{args.embedding_url.rstrip('/')}/health")
        receipts["qdrant"] = get_json(client, f"{args.qdrant_url.rstrip('/')}/collections")
        receipts["memory"] = get_json(client, f"{args.memory_url.rstrip('/')}/health")
    return receipts


def embed_and_write_crops(*, crops: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    image_inputs: list[str] = []
    valid_crops: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for crop in crops:
        crop_path = resolve_repo_path(crop.get("crop_path"))
        if not crop_path.exists():
            failures.append({"crop_path": str(crop_path), "error": "CROP_FILE_MISSING", "overlay_id": crop.get("overlay_id")})
            continue
        image_inputs.append(data_uri(crop_path))
        valid_crops.append(crop)

    vectors: list[list[float]] = []
    embedding_response: dict[str, Any] = {}
    if image_inputs:
        with httpx.Client(timeout=httpx.Timeout(300.0, connect=5.0)) as client:
            response = client.post(
                f"{args.embedding_url.rstrip('/')}/embed/batch",
                json={"images": image_inputs, "task": "retrieval", "dimensions": args.dimensions},
                headers={"X-Caller-Skill": "watch"},
            )
            response.raise_for_status()
            embedding_response = response.json()
        vectors = embedding_response.get("embeddings") or embedding_response.get("vectors") or []
    if len(vectors) != len(valid_crops):
        raise RuntimeError(f"embedding count mismatch: {len(vectors)} vectors for {len(valid_crops)} crops")

    points = []
    receipts = []
    for crop, vector in zip(valid_crops, vectors):
        point_id = point_id_for("crop", crop.get("overlay_id") or crop.get("crop_path"))
        payload = {
            "asset_uid": crop.get("asset_uid"),
            "segment_id": crop.get("segment_id"),
            "track_id": crop.get("track_id"),
            "overlay_id": crop.get("overlay_id"),
            "media_time_seconds": crop.get("media_time_seconds"),
            "crop_path": str(resolve_repo_path(crop.get("crop_path"))),
            "candidate_entity": crop.get("candidate_entity"),
            "identity_evidence_status": crop.get("identity_evidence_status"),
            "source": "watch_realtime_identity_memory_loop",
        }
        points.append({"id": point_id, "vector": vector, "payload": payload})
        receipts.append(
            {
                "overlay_id": crop.get("overlay_id"),
                "track_id": crop.get("track_id"),
                "crop_path": crop.get("crop_path"),
                "qdrant_collection": args.crop_collection,
                "qdrant_point_id": point_id,
                "embedding_model": embedding_response.get("model"),
                "dimensions": len(vector),
                "status": "WRITTEN",
            }
        )
    ensure_qdrant_collection(args.qdrant_url, args.crop_collection, args.dimensions)
    if points:
        upsert_qdrant_points(args.qdrant_url, args.crop_collection, points)
    return {
        "schema": "watch.crop_embedding_live_receipt.v1",
        "status": "WRITTEN" if points and not failures else "PARTIAL" if points else "FAILED",
        "embedding_service": args.embedding_url,
        "qdrant_collection": args.crop_collection,
        "embedding_model": embedding_response.get("model"),
        "dimensions": embedding_response.get("dimensions") or (len(vectors[0]) if vectors else None),
        "receipts": receipts,
        "failures": failures,
        "counts": {
            "crop_count": len(crops),
            "embedded_crop_count": len(vectors),
            "qdrant_written": len(points),
            "failure_count": len(failures),
        },
    }


def load_reference_approval_receipt(path: Path | None) -> dict[str, Any]:
    if not path:
        return {
            "schema": "watch.reference_download_review_approval_receipt.v1",
            "status": "NOT_PROVIDED",
            "reference_receipts": [],
            "counts": {"approved_reference_count": 0},
        }
    receipt = read_json(path)
    if receipt.get("schema") != "watch.reference_download_review_approval_receipt.v1":
        raise ValueError(f"unsupported reference approval receipt schema: {receipt.get('schema')!r}")
    return receipt


def reference_approval_by_id(approval_receipt: dict[str, Any]) -> dict[str, dict[str, Any]]:
    refs = approval_receipt.get("reference_receipts") or []
    return {str(item.get("reference_id")): item for item in refs if item.get("reference_id")}


def attach_reference_approval(
    ref: dict[str, Any],
    approval_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    reference_id = str(ref.get("reference_id") or ref.get("local_path"))
    approval = approval_by_id.get(reference_id)
    if not approval:
        return {
            **ref,
            "approval_gate_status": "APPROVED_MANIFEST_ONLY_NO_RECEIPT",
            "approval_receipt_id": None,
            "approval_receipt_status": None,
            "approval_scope": None,
        }
    receipt = approval.get("approval_receipt") or {}
    return {
        **ref,
        "approval_gate_status": "APPROVAL_RECEIPT_LINKED",
        "approval_receipt_id": receipt.get("receipt_id"),
        "approval_receipt_status": receipt.get("status"),
        "approval_scope": receipt.get("approval_scope"),
        "approval_promotion_allowed": bool(approval.get("identity_promotion_allowed")),
    }


def approval_receipt_allows_embedding(ref: dict[str, Any]) -> bool:
    status = str(ref.get("approval_receipt_status") or "").upper()
    if not status:
        return True
    return status in {"APPROVED", "APPROVED_CANARY_PIPELINE_ONLY"}


def embed_and_write_references(
    reference_manifest_path: Path | None,
    reference_approval_receipt: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    if not reference_manifest_path:
        return {
            "schema": "watch.reference_embedding_live_receipt.v1",
            "status": "BLOCKED_NO_APPROVED_REFERENCE_MANIFEST",
            "qdrant_collection": args.reference_collection,
            "receipts": [],
            "failures": [],
            "counts": {"approved_reference_count": 0, "approval_receipt_count": 0, "qdrant_written": 0},
        }
    manifest = read_json(reference_manifest_path)
    approval_by_id = reference_approval_by_id(reference_approval_receipt)
    references = [
        attach_reference_approval(ref, approval_by_id)
        for ref in approved_reference_records(manifest)
    ]
    references = [ref for ref in references if approval_receipt_allows_embedding(ref)]
    image_inputs = [data_uri(resolve_repo_path(reference_local_path(ref))) for ref in references]
    with httpx.Client(timeout=httpx.Timeout(300.0, connect=5.0)) as client:
        response = client.post(
            f"{args.embedding_url.rstrip('/')}/embed/batch",
            json={"images": image_inputs, "task": "retrieval", "dimensions": args.dimensions},
            headers={"X-Caller-Skill": "watch"},
        )
        response.raise_for_status()
        data = response.json()
    vectors = data.get("embeddings") or data.get("vectors") or []
    ensure_qdrant_collection(args.qdrant_url, args.reference_collection, args.dimensions)
    points = []
    receipts = []
    for ref, vector in zip(references, vectors):
        point_id = point_id_for("reference", ref.get("reference_id") or ref.get("local_path"))
        points.append(
            {
                "id": point_id,
                "vector": vector,
                "payload": {
                    "reference_id": ref.get("reference_id"),
                    "entity_id": ref.get("entity_id"),
                    "actor_name": ref.get("actor_name"),
                    "local_path": str(resolve_repo_path(reference_local_path(ref))),
                    "source_url": ref.get("source_url"),
                    "approval_status": ref.get("approval_status"),
                    "approval_receipt_id": ref.get("approval_receipt_id"),
                    "approval_receipt_status": ref.get("approval_receipt_status"),
                    "approval_scope": ref.get("approval_scope"),
                },
            }
        )
        receipts.append(
            {
                "reference_id": ref.get("reference_id"),
                "entity_id": ref.get("entity_id"),
                "character_name": ref.get("character_name") or ref.get("name"),
                "actor_name": ref.get("actor_name"),
                "qdrant_collection": args.reference_collection,
                "qdrant_point_id": point_id,
                "dimensions": len(vector),
                "status": "WRITTEN",
                "approval_gate_status": ref.get("approval_gate_status"),
                "approval_receipt_id": ref.get("approval_receipt_id"),
                "approval_receipt_status": ref.get("approval_receipt_status"),
                "approval_scope": ref.get("approval_scope"),
                "approval_promotion_allowed": bool(ref.get("approval_promotion_allowed")),
            }
        )
    if points:
        upsert_qdrant_points(args.qdrant_url, args.reference_collection, points)
    return {
        "schema": "watch.reference_embedding_live_receipt.v1",
        "status": "WRITTEN" if points else "NO_APPROVED_REFERENCES",
        "qdrant_collection": args.reference_collection,
        "receipts": receipts,
        "failures": [],
        "counts": {
            "approved_reference_count": len(references),
            "approval_receipt_count": len([ref for ref in references if ref.get("approval_receipt_id")]),
            "qdrant_written": len(points),
        },
    }


def build_similarity_receipts(
    crop_receipt: dict[str, Any],
    reference_receipt: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    comparisons: list[dict[str, Any]] = []
    if reference_receipt["counts"]["qdrant_written"] == 0:
        return {
            "schema": "watch.crop_reference_similarity_live_receipt.v1",
            "status": "BLOCKED_NO_APPROVED_REFERENCE_EMBEDDINGS",
            "comparisons": comparisons,
            "counts": {"comparison_count": 0},
            "promotion_allowed": False,
        }
    crop_vectors = qdrant_vectors_by_point_id(
        args.qdrant_url,
        args.crop_collection,
        [item["qdrant_point_id"] for item in crop_receipt.get("receipts", [])],
    )
    reference_vectors = qdrant_vectors_by_point_id(
        args.qdrant_url,
        args.reference_collection,
        [item["qdrant_point_id"] for item in reference_receipt.get("receipts", [])],
    )
    for crop in crop_receipt.get("receipts", []):
        for ref in reference_receipt.get("receipts", []):
            crop_vector = crop_vectors.get(crop["qdrant_point_id"])
            ref_vector = reference_vectors.get(ref["qdrant_point_id"])
            score = cosine_similarity(crop_vector, ref_vector) if crop_vector and ref_vector else None
            comparisons.append(
                {
                    "comparison_id": stable_id("similarity", {"crop": crop["qdrant_point_id"], "reference": ref["qdrant_point_id"]}),
                    "crop_qdrant_point_id": crop["qdrant_point_id"],
                    "reference_qdrant_point_id": ref["qdrant_point_id"],
                    "entity_id": ref.get("entity_id"),
                    "character_name": ref.get("character_name"),
                    "actor_name": ref.get("actor_name"),
                    "reference_approval_receipt_id": ref.get("approval_receipt_id"),
                    "reference_approval_receipt_status": ref.get("approval_receipt_status"),
                    "reference_approval_scope": ref.get("approval_scope"),
                    "cosine_similarity": round(score, 6) if score is not None else None,
                    "threshold": 0.72,
                    "status": "SIMILARITY_SCORED" if score is not None else "SIMILARITY_SCORE_MISSING_VECTOR",
                    "negative_control_required": True,
                    "memory_recall_required": True,
                    "promotion_allowed": False,
                }
            )
    return {
        "schema": "watch.crop_reference_similarity_live_receipt.v1",
        "status": "SCORED_REQUIRES_NEGATIVE_CONTROLS",
        "comparisons": comparisons,
        "counts": {"comparison_count": len(comparisons)},
        "promotion_allowed": False,
    }


def upsert_memory_records(
    *,
    events: list[dict[str, Any]],
    crops: list[dict[str, Any]],
    crop_embedding_receipt: dict[str, Any],
    similarity_receipt: dict[str, Any],
    memory_url: str,
) -> dict[str, Any]:
    point_by_overlay = {item["overlay_id"]: item for item in crop_embedding_receipt.get("receipts", [])}
    docs = []
    for crop in crops:
        point = point_by_overlay.get(crop.get("overlay_id"))
        if not point:
            continue
        doc = {
            "_key": key_for(crop.get("overlay_id")),
            "schema": "watch.track_observation.live.v1",
            "record_kind": "watch_track_observation",
            "asset_uid": crop.get("asset_uid"),
            "segment_id": crop.get("segment_id"),
            "track_id": crop.get("track_id"),
            "overlay_id": crop.get("overlay_id"),
            "media_time_seconds": crop.get("media_time_seconds"),
            "candidate_entity": crop.get("candidate_entity"),
            "tags": watch_tags(crop),
            "identity_status": "IDENTITY_INCONCLUSIVE",
            "promotion_blockers": [
                "APPROVED_REFERENCE_EMBEDDINGS_REQUIRED",
                "CROP_REFERENCE_SIMILARITY_REQUIRED",
                "NEGATIVE_CONTROL_REQUIRED",
                "TEXT_SCENE_CORROBORATION_REQUIRED",
                "MEMORY_RECALL_RECHECK_REQUIRED",
            ],
            "qdrant_pointers": [
                {
                    "collection": point["qdrant_collection"],
                    "point_id": point["qdrant_point_id"],
                    "modality": "track_crop_image",
                    "embedding_model": point.get("embedding_model"),
                }
            ],
            "retrieval_text": retrieval_text(crop),
            "source": "watch_realtime_identity_memory_loop",
            "updated_at": utc_now(),
        }
        docs.append(doc)

    cases = []
    for doc in docs:
        entity = doc.get("candidate_entity") or {}
        case_id = key_for(f"case:{doc['overlay_id']}")
        cases.append(
            {
                "_key": case_id,
                "schema": "watch.evidence_case.live.v1",
                "record_kind": "watch_evidence_case",
                "asset_uid": doc["asset_uid"],
                "segment_id": doc["segment_id"],
                "entity_ids": [entity.get("entity_id")] if entity.get("entity_id") else [],
                "tags": watch_tags(doc),
                "time_range": {"start_seconds": doc["media_time_seconds"], "end_seconds": doc["media_time_seconds"]},
                "verdict": "INCONCLUSIVE",
                "failure_code": "NEEDS_HUMAN_REVIEW",
                "track_observation_key": doc["_key"],
                "retrieval_text": f"Watch evidence case for {entity.get('name') or 'unknown entity'} in segment {doc['segment_id']} remains inconclusive pending reference similarity and memory recall proof.",
                "updated_at": utc_now(),
            }
        )

    watch_content_docs = []
    for doc in docs:
        entity = doc.get("candidate_entity") or {}
        watch_content_docs.append(
            {
                "_key": key_for(f"watch_content:{doc['overlay_id']}"),
                "schema": "watch.content.identity_tracking_recall_projection.v1",
                "record_kind": "watch_identity_tracking_recall_projection",
                "question": (
                    f"Which Watch movie segments contain {entity.get('name') or 'unknown entity'} "
                    f"track observations from Bad Santa?"
                ),
                "answer": (
                    f"Segment {doc['segment_id']} contains a realtime tracking observation for "
                    f"{entity.get('name') or 'unknown entity'} at {doc['media_time_seconds']} seconds. "
                    "The crop is embedded in Qdrant and identity remains inconclusive until approved "
                    "reference similarity and negative controls pass."
                ),
                "reasoning": json.dumps(
                    {
                        "source": "watch_realtime_identity_memory_loop",
                        "asset_uid": doc["asset_uid"],
                        "segment_id": doc["segment_id"],
                        "track_id": doc["track_id"],
                        "overlay_id": doc["overlay_id"],
                        "track_observation_key": doc["_key"],
                        "qdrant_pointers": doc["qdrant_pointers"],
                    },
                    sort_keys=True,
                ),
                "title": "Bad Santa realtime identity tracking receipt",
                "source": "watch_realtime_identity_memory_loop",
                "retrieval_text": doc["retrieval_text"],
                "asset_uid": doc["asset_uid"],
                "segment_id": doc["segment_id"],
                "entity_ids": [entity.get("entity_id")] if entity.get("entity_id") else [],
                "tags": watch_tags(doc),
                "updated_at": utc_now(),
            }
        )

    payloads = {
        "watch_track_observations": docs,
        "watch_evidence_cases": cases,
        "watch_content": watch_content_docs,
    }
    similarity_comparisons = similarity_receipt.get("comparisons") or []
    linked_approval_receipts = {
        item.get("reference_approval_receipt_id")
        for item in similarity_comparisons
        if item.get("reference_approval_receipt_id")
    }
    collection_receipts = []
    with httpx.Client(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
        for collection, documents in payloads.items():
            if not documents:
                collection_receipts.append(
                    {
                        "collection": collection,
                        "document_count": 0,
                        "status_code": None,
                        "ok": False,
                        "response_preview": "SKIPPED_EMPTY_DOCUMENT_BATCH",
                    }
                )
                continue
            response = client.post(
                f"{memory_url.rstrip('/')}/upsert",
                json={"collection": collection, "documents": documents},
                headers={"X-Caller-Skill": "watch"},
            )
            collection_receipts.append(
                {
                    "collection": collection,
                    "document_count": len(documents),
                    "status_code": response.status_code,
                    "ok": 200 <= response.status_code < 300,
                    "response_preview": response.text[:500],
                }
            )
            response.raise_for_status()
    return {
        "schema": "watch.memory_upsert_live_receipt.v1",
        "status": "WRITTEN" if docs and cases else "FAILED_EMPTY_DOCUMENT_BATCH",
        "collections": collection_receipts,
        "similarity_status": similarity_receipt.get("status"),
        "reference_approval_receipt_linked_count": len(linked_approval_receipts),
        "similarity_comparison_count": len(similarity_comparisons),
        "counts": {
            "document_count": sum(len(documents) for documents in payloads.values()),
            "track_observation_count": len(docs),
            "evidence_case_count": len(cases),
            "watch_content_projection_count": len(watch_content_docs),
            "reference_approval_receipt_linked_count": len(linked_approval_receipts),
            "similarity_comparison_count": len(similarity_comparisons),
        },
    }


def run_recall_proof(memory_receipt: dict[str, Any], memory_url: str) -> dict[str, Any]:
    body = {
        "q": "realtime identity tracking receipt Marcus track observation",
        "collections": ["watch_content"],
        "tags": ["character:marcus"],
        "k": 10,
    }
    with httpx.Client(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
        response = client.post(f"{memory_url.rstrip('/')}/recall", json=body, headers={"X-Caller-Skill": "watch"})
    data: dict[str, Any]
    try:
        data = response.json()
    except Exception:
        data = {"raw": response.text[:1000]}
    items = data.get("items") if isinstance(data, dict) else []
    return {
        "schema": "watch.memory_recall_live_receipt.v1",
        "status": "QUERIED",
        "request": body,
        "status_code": response.status_code,
        "found": bool(data.get("found")) if isinstance(data, dict) else False,
        "confidence": data.get("confidence") if isinstance(data, dict) else None,
        "item_keys": [item.get("_key") for item in (items or []) if isinstance(item, dict)],
        "counts": {"item_count": len(items or [])},
        "response_preview": data,
    }


def ensure_qdrant_collection(base_url: str, collection: str, dimensions: int) -> None:
    with httpx.Client(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
        existing = client.get(f"{base_url.rstrip('/')}/collections/{collection}")
        if existing.status_code == 200:
            return
        if existing.status_code != 404:
            existing.raise_for_status()
        response = client.put(
            f"{base_url.rstrip('/')}/collections/{collection}",
            json={"vectors": {"size": dimensions, "distance": "Cosine"}},
        )
        response.raise_for_status()


def upsert_qdrant_points(base_url: str, collection: str, points: list[dict[str, Any]]) -> None:
    with httpx.Client(timeout=httpx.Timeout(120.0, connect=5.0)) as client:
        response = client.put(
            f"{base_url.rstrip('/')}/collections/{collection}/points?wait=true",
            json={"points": points},
        )
        response.raise_for_status()


def qdrant_vectors_by_point_id(base_url: str, collection: str, point_ids: list[str]) -> dict[str, list[float]]:
    if not point_ids:
        return {}
    with httpx.Client(timeout=httpx.Timeout(120.0, connect=5.0)) as client:
        response = client.post(
            f"{base_url.rstrip('/')}/collections/{collection}/points",
            json={"ids": point_ids, "with_vector": True, "with_payload": False},
        )
        response.raise_for_status()
        data = response.json()
    vectors: dict[str, list[float]] = {}
    for point in data.get("result") or []:
        vector = point.get("vector")
        if isinstance(vector, dict):
            vector = vector.get("") or vector.get("default") or next(iter(vector.values()), None)
        if isinstance(vector, list):
            vectors[str(point.get("id"))] = vector
    return vectors


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return math.nan
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return math.nan
    return dot / (left_norm * right_norm)


def get_json(client: httpx.Client, url: str) -> dict[str, Any]:
    response = client.get(url)
    return {
        "url": url,
        "status_code": response.status_code,
        "ok": 200 <= response.status_code < 300,
        "body": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text[:500],
    }


def retrieval_text(crop: dict[str, Any]) -> str:
    entity = crop.get("candidate_entity") or {}
    name = entity.get("name") or "unknown entity"
    return (
        f"Watch realtime track observation for {name} in asset {crop.get('asset_uid')} "
        f"segment {crop.get('segment_id')} at {crop.get('media_time_seconds')} seconds. "
        "This is an observation with crop embedding and Qdrant pointer; identity remains inconclusive."
    )


def approved_reference_records(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for ref in manifest.get("references") or []:
        if str(ref.get("approval_status", "")).upper() == "APPROVED" and reference_local_path(ref):
            records.append(ref)
    for candidate in manifest.get("candidates") or []:
        for ref in candidate.get("approved_references") or []:
            if str(ref.get("approval_status", "APPROVED")).upper() != "APPROVED":
                continue
            if not reference_local_path(ref):
                continue
            merged = {
                "entity_id": candidate.get("entity_id"),
                "character_name": candidate.get("name"),
                "actor_name": candidate.get("actor_name"),
                **ref,
            }
            records.append(merged)
    return records


def reference_local_path(ref: dict[str, Any]) -> str | None:
    value = ref.get("local_path") or ref.get("crop_path") or ref.get("downloaded_artifact_ref")
    return str(value) if value else None


def watch_tags(record: dict[str, Any]) -> list[str]:
    entity = record.get("candidate_entity") or {}
    tags = [
        "watch",
        "watch:identity_tracking",
        "movie:bad_santa_2003",
        "asset:movie_bad_santa_2003_unrated",
    ]
    name = str(entity.get("name") or "").strip().lower()
    if name:
        tags.append(f"character:{name}")
    return tags


def loop_status(crop_receipt: dict[str, Any], memory_receipt: dict[str, Any], recall_receipt: dict[str, Any]) -> str:
    if crop_receipt.get("status") not in {"WRITTEN", "PARTIAL"}:
        return "FAILED_CROP_EMBEDDINGS"
    if memory_receipt.get("status") != "WRITTEN":
        return "FAILED_MEMORY_UPSERT"
    if recall_receipt.get("status") != "QUERIED":
        return "LIVE_RECEIPTS_PARTIAL"
    if recall_receipt.get("counts", {}).get("item_count", 0) <= 0:
        return "FAILED_MEMORY_RECALL_PROOF"
    return "LIVE_RECEIPTS_WRITTEN"


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: str | Path, value: Any) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def resolve_repo_path(value: str | None) -> Path:
    if not value:
        raise ValueError("missing path")
    path = Path(value)
    if path.is_absolute():
        return path
    repo_path = Path.cwd() / path
    if repo_path.exists():
        return repo_path
    watch_path = WATCH_SKILL_DIR / value
    if watch_path.exists():
        return watch_path
    watch_generated_path = DEFAULT_ARCH_DIR / value
    if watch_generated_path.exists():
        return watch_generated_path
    return repo_path


def point_id_for(kind: str, value: Any) -> str:
    return str(uuid.uuid5(WATCH_NAMESPACE_UUID, f"{kind}:{value}"))


def stable_id(prefix: str, value: Any) -> str:
    material = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"{prefix}:{hashlib.sha256(material.encode('utf-8')).hexdigest()[:32]}"


def key_for(value: Any) -> str:
    text = stable_id("watch", value)
    return re.sub(r"[^A-Za-z0-9_:-]", "_", text.replace(":", "_"))[:254]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def display_path(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
