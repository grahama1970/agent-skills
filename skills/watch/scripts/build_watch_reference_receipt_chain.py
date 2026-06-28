#!/usr/bin/env python3
"""Build Watch reference download, approval, embedding, and similarity receipts.

The functions in this module turn candidate reference manifests into explicit
receipt plans. They intentionally do not download files, approve images,
compute embeddings, write Qdrant/Arango, or promote identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


DOWNLOAD_REVIEW_APPROVAL_SCHEMA = "watch.reference_download_review_approval_receipt_plan.v1"
REFERENCE_EMBEDDING_SCHEMA = "watch.reference_candidate_embedding_receipt_plan.v1"
CROP_REFERENCE_SIMILARITY_SCHEMA = "watch.crop_reference_candidate_similarity_receipt_plan.v1"


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, value: Any) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def stable_id(prefix: str, value: Any) -> str:
    material = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


def qdrant_point_id(value: Any) -> str:
    return stable_id("qdrant_point", value)


def assert_no_raw_vectors(value: Any, path: str = "$") -> None:
    forbidden = {"vector", "vectors", "embedding", "embeddings", "dense_vector"}
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key) in forbidden:
                raise ValueError(f"raw vector field is forbidden at {child_path}")
            assert_no_raw_vectors(child, child_path)
    elif isinstance(value, list):
        if len(value) > 8 and all(isinstance(item, (int, float)) for item in value):
            raise ValueError(f"raw numeric vector array is forbidden at {path}")
        for idx, child in enumerate(value):
            assert_no_raw_vectors(child, f"{path}[{idx}]")


def build_download_review_approval_plan(reference_manifest: dict[str, Any]) -> dict[str, Any]:
    if reference_manifest.get("schema") != "watch.reference_manifest.v1":
        raise ValueError(f"unsupported reference manifest schema: {reference_manifest.get('schema')!r}")

    asset_id = str(reference_manifest["asset_id"])
    receipt_items: list[dict[str, Any]] = []
    for ref in reference_manifest.get("references", []):
        reference_id = str(ref["reference_id"])
        receipt_items.append(
            {
                "reference_id": reference_id,
                "entity_id": ref.get("entity_id"),
                "actor_name": ref.get("actor_name"),
                "provider": ref.get("provider"),
                "source_url": ref.get("source_url"),
                "image_url": ref.get("image_url"),
                "thumbnail_url": ref.get("thumbnail_url"),
                "download_receipt": {
                    "receipt_id": stable_id("watch_ref_download_receipt", reference_id),
                    "status": "PLANNED_NOT_RUN",
                    "required": True,
                    "downloaded_artifact_ref": None,
                    "sha256": None,
                },
                "source_review_receipt": {
                    "receipt_id": stable_id("watch_ref_source_review_receipt", reference_id),
                    "status": "BLOCKED_PENDING_DOWNLOAD",
                    "required": True,
                    "checks": [
                        "source_url_accessible",
                        "license_or_source_policy_reviewed",
                        "image_matches_target_actor_or_character",
                        "solo_or_useful_reference_image",
                        "not_group_shot_or_poster_only",
                        "not_scene_truth",
                    ],
                },
                "approval_receipt": {
                    "receipt_id": stable_id("watch_ref_approval_receipt", reference_id),
                    "status": "BLOCKED_PENDING_SOURCE_REVIEW",
                    "required": True,
                    "approved_by": None,
                    "approval_time": None,
                },
                "approved_reference_status": "NOT_APPROVED",
                "candidate_only": True,
                "scene_truth_claimed": False,
                "identity_promotion_allowed": False,
            }
        )

    plan = {
        "schema": DOWNLOAD_REVIEW_APPROVAL_SCHEMA,
        "status": "PLANNED_NOT_RUN",
        "asset_id": asset_id,
        "source_reference_manifest_schema": reference_manifest.get("schema"),
        "reference_receipts": receipt_items,
        "receipt_requirements": {
            "download_receipts_required": True,
            "source_review_receipts_required": True,
            "approval_receipts_required": True,
            "approved_before_embedding": True,
        },
        "promotion_policy": {
            "candidate_url_can_promote_identity": False,
            "download_without_approval_can_promote_identity": False,
            "approval_without_crop_similarity_can_promote_identity": False,
            "scene_truth_claim_allowed": False,
        },
        "counts": {
            "candidate_reference_count": len(receipt_items),
            "downloaded_reference_count": 0,
            "approved_reference_count": 0,
            "blocked_reference_count": len(receipt_items),
        },
        "proof_scope": [
            "reference_download_review_approval_receipt_contract",
            "planned_not_run",
        ],
        "claims": {
            "proves": [
                "candidate references have deterministic download, source-review, and approval receipt ids",
                "candidate references are blocked from embedding and identity promotion until approval receipts exist",
            ],
            "does_not_prove": [
                "image download success",
                "license suitability",
                "human approval",
                "reference embedding success",
                "crop/reference similarity",
                "supported character identity",
            ],
        },
    }
    assert_no_raw_vectors(plan)
    return plan


def build_reference_embedding_receipt_plan(approval_plan: dict[str, Any]) -> dict[str, Any]:
    if approval_plan.get("schema") != DOWNLOAD_REVIEW_APPROVAL_SCHEMA:
        raise ValueError(f"unsupported approval plan schema: {approval_plan.get('schema')!r}")

    asset_id = str(approval_plan["asset_id"])
    reference_points: list[dict[str, Any]] = []
    for item in approval_plan.get("reference_receipts", []):
        point_id = qdrant_point_id(
            {
                "asset_id": asset_id,
                "reference_id": item["reference_id"],
                "modality": "reference_image",
                "model": "jina_clip_planned",
            }
        )
        reference_points.append(
            {
                "reference_id": item["reference_id"],
                "entity_id": item.get("entity_id"),
                "provider": item.get("provider"),
                "source_url": item.get("source_url"),
                "image_url": item.get("image_url"),
                "approval_receipt_id": item["approval_receipt"]["receipt_id"],
                "embedding_receipt_id": stable_id("watch_ref_embedding_receipt", item["reference_id"]),
                "embedding_receipt_status": "BLOCKED_PENDING_APPROVAL_RECEIPT",
                "qdrant_point_plan": {
                    "collection": "watch_reference_image_embeddings",
                    "point_id": point_id,
                    "write_status": "BLOCKED_PENDING_APPROVAL_RECEIPT",
                    "modality": "reference_image",
                    "embedding_model": "jina-clip-or-current-watch-multimodal-model",
                    "payload": {
                        "asset_id": asset_id,
                        "reference_id": item["reference_id"],
                        "entity_id": item.get("entity_id"),
                        "provider": item.get("provider"),
                        "scene_truth_claimed": False,
                    },
                },
                "scene_truth_claimed": False,
                "identity_promotion_allowed": False,
            }
        )

    plan = {
        "schema": REFERENCE_EMBEDDING_SCHEMA,
        "status": "BLOCKED_PENDING_APPROVAL_RECEIPTS",
        "asset_id": asset_id,
        "source_approval_plan_schema": approval_plan.get("schema"),
        "reference_embedding_receipts": reference_points,
        "qdrant_reference_point_plan": {
            "collection": "watch_reference_image_embeddings",
            "write_status": "BLOCKED_PENDING_APPROVAL_RECEIPTS",
            "raw_vectors_in_plan": False,
            "points": [point["qdrant_point_plan"] for point in reference_points],
        },
        "receipt_requirements": {
            "approval_receipts_required": True,
            "jina_embedding_receipts_required": True,
            "qdrant_write_receipts_required": True,
        },
        "promotion_policy": {
            "reference_embedding_without_crop_similarity_can_promote_identity": False,
            "reference_embedding_without_memory_recall_can_promote_identity": False,
            "scene_truth_claim_allowed": False,
        },
        "counts": {
            "reference_embedding_receipt_count": len(reference_points),
            "qdrant_reference_point_plan_count": len(reference_points),
            "ready_reference_embedding_count": 0,
        },
        "proof_scope": [
            "reference_embedding_receipt_contract",
            "planned_not_written",
        ],
        "claims": {
            "proves": [
                "approved references are the only path to planned Jina/Qdrant embedding receipts",
                "Qdrant point ids are deterministic and no raw vectors are present",
            ],
            "does_not_prove": [
                "Jina embedding success",
                "Qdrant write success",
                "crop/reference similarity",
                "supported character identity",
            ],
        },
    }
    assert_no_raw_vectors(plan)
    return plan


def build_crop_reference_similarity_plan(crop_manifest: dict[str, Any], embedding_plan: dict[str, Any]) -> dict[str, Any]:
    if embedding_plan.get("schema") != REFERENCE_EMBEDDING_SCHEMA:
        raise ValueError(f"unsupported embedding plan schema: {embedding_plan.get('schema')!r}")

    asset_id = str(embedding_plan["asset_id"])
    crops = crop_manifest.get("crops") or []
    reference_points = embedding_plan.get("reference_embedding_receipts") or []
    comparisons: list[dict[str, Any]] = []
    for crop in crops:
        crop_entity_id = (crop.get("candidate_entity") or {}).get("entity_id")
        for ref in reference_points:
            if crop_entity_id and ref.get("entity_id") and crop_entity_id != ref.get("entity_id"):
                continue
            comparison_id = stable_id(
                "watch_crop_reference_similarity_receipt",
                {
                    "asset_id": asset_id,
                    "overlay_id": crop.get("overlay_id"),
                    "reference_id": ref.get("reference_id"),
                },
            )
            crop_point_id = qdrant_point_id(
                {
                    "asset_id": asset_id,
                    "overlay_id": crop.get("overlay_id"),
                    "crop_path": crop.get("crop_path"),
                    "modality": "track_crop",
                }
            )
            comparisons.append(
                {
                    "comparison_id": comparison_id,
                    "entity_id": ref.get("entity_id") or crop_entity_id,
                    "overlay_id": crop.get("overlay_id"),
                    "track_id": crop.get("track_id"),
                    "crop_path": crop.get("crop_path"),
                    "reference_id": ref.get("reference_id"),
                    "crop_embedding_point": {
                        "collection": "watch_track_crop_embeddings",
                        "point_id": crop_point_id,
                        "write_status": "PLANNED_NOT_WRITTEN",
                    },
                    "reference_embedding_point": ref.get("qdrant_point_plan"),
                    "similarity_receipt_status": "BLOCKED_PENDING_EMBEDDINGS",
                    "negative_control_required": True,
                    "text_scene_corroboration_required": True,
                    "memory_recall_required": True,
                    "scene_truth_claimed": False,
                    "identity_promotion_allowed": False,
                }
            )

    plan = {
        "schema": CROP_REFERENCE_SIMILARITY_SCHEMA,
        "status": "BLOCKED_PENDING_EMBEDDINGS",
        "asset_id": asset_id,
        "source_crop_manifest_schema": crop_manifest.get("schema_version") or crop_manifest.get("schema"),
        "source_reference_embedding_schema": embedding_plan.get("schema"),
        "similarity_receipts": comparisons,
        "receipt_requirements": {
            "crop_embedding_receipts_required": True,
            "reference_embedding_receipts_required": True,
            "positive_similarity_receipts_required": True,
            "negative_control_receipts_required": True,
            "text_scene_corroboration_receipts_required": True,
            "memory_recall_receipts_required": True,
        },
        "promotion_policy": {
            "similarity_without_negative_control_can_promote_identity": False,
            "similarity_without_text_scene_corroboration_can_promote_identity": False,
            "similarity_without_memory_recall_can_promote_identity": False,
            "scene_truth_claim_allowed": False,
        },
        "counts": {
            "candidate_crop_count": len(crops),
            "reference_embedding_receipt_count": len(reference_points),
            "planned_similarity_receipt_count": len(comparisons),
            "ready_similarity_receipt_count": 0,
        },
        "proof_scope": [
            "crop_reference_similarity_receipt_contract",
            "planned_not_run",
        ],
        "claims": {
            "proves": [
                "track crops are joined to reference embedding plans through deterministic similarity receipt ids",
                "similarity cannot promote identity without negative controls, text/scene corroboration, and memory recall",
            ],
            "does_not_prove": [
                "crop embedding success",
                "reference embedding success",
                "similarity score correctness",
                "supported character identity",
                "real-time annotation tracking",
            ],
        },
    }
    assert_no_raw_vectors(plan)
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-manifest", required=True, type=Path)
    parser.add_argument("--crop-manifest", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    manifest = load_json(args.reference_manifest)
    approval_plan = build_download_review_approval_plan(manifest)
    embedding_plan = build_reference_embedding_receipt_plan(approval_plan)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "watch_reference_download_review_approval_receipt_plan.json", approval_plan)
    write_json(args.out_dir / "watch_reference_candidate_embedding_receipt_plan.json", embedding_plan)
    if args.crop_manifest:
        similarity_plan = build_crop_reference_similarity_plan(load_json(args.crop_manifest), embedding_plan)
        write_json(args.out_dir / "watch_crop_reference_candidate_similarity_receipt_plan.json", similarity_plan)
        print("similarity_receipt_plan_ok", similarity_plan["counts"]["planned_similarity_receipt_count"])
    print("download_review_approval_receipt_plan_ok", approval_plan["counts"]["candidate_reference_count"])
    print("reference_candidate_embedding_receipt_plan_ok", embedding_plan["counts"]["reference_embedding_receipt_count"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
