#!/usr/bin/env python3
"""Generate Watch crop/reference image similarity receipts.

This queries Qdrant image vectors for provisional reference images against
human/ML keyframe crop vectors. It records similarity evidence only; it does not
promote character identity automatically.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AGENT_SKILLS_ROOT = Path(__file__).resolve().parents[3]
MEMORY_ROOT = AGENT_SKILLS_ROOT.parent / "memory"
if str(MEMORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(MEMORY_ROOT / "src"))


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env(MEMORY_ROOT / ".env")

from graph_memory.arango_client import get_db  # noqa: E402
from graph_memory.config import QDRANT_SEMANTIC_COLLECTION  # noqa: E402
from graph_memory.qdrant_client import QdrantClient  # noqa: E402
from graph_memory.semantic_sync import QDRANT_SEMANTIC_IMAGE_VECTOR_NAME  # noqa: E402


OUT_ROOT = (
    AGENT_SKILLS_ROOT
    / "skills"
    / "watch"
    / "docs"
    / "architecture"
    / "generated"
    / "watch_crop_reference_similarity_receipts"
)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def fetch_reference_docs(db: Any, character: str, limit: int) -> list[dict[str, Any]]:
    return list(
        db.aql.execute(
            """
            FOR d IN watch_reference_images
              FILTER d.character_name == @character
              FILTER d.multimodal_sync_state == 'synced'
              FILTER IS_STRING(d.qdrant_image_point_id) AND d.qdrant_image_point_id != ''
              SORT d.updated_at DESC
              LIMIT @limit
              RETURN d
            """,
            bind_vars={"character": character, "limit": limit},
        )
    )


def fetch_crop_docs(db: Any, character: str, limit: int) -> list[dict[str, Any]]:
    return list(
        db.aql.execute(
            """
            FOR d IN watch_keyframe_annotations
              FILTER d.character_name == @character
              FILTER d.lifecycle_status != 'superseded'
              FILTER d.multimodal_sync_state == 'synced'
              FILTER IS_STRING(d.qdrant_image_point_id) AND d.qdrant_image_point_id != ''
              SORT d.updated_at DESC
              LIMIT @limit
              RETURN d
            """,
            bind_vars={"character": character, "limit": limit},
        )
    )


def image_vector(point: dict[str, Any] | None) -> list[float] | None:
    if not point:
        return None
    vector = point.get("vector")
    if isinstance(vector, dict):
        candidate = vector.get(QDRANT_SEMANTIC_IMAGE_VECTOR_NAME)
        if isinstance(candidate, list):
            return candidate
    if isinstance(vector, list):
        return vector
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character", default="Willie")
    parser.add_argument("--reference-limit", type=int, default=6)
    parser.add_argument("--crop-limit", type=int, default=5)
    parser.add_argument("--query-limit", type=int, default=5)
    args = parser.parse_args()

    db = get_db()
    qdrant = QdrantClient()
    references = fetch_reference_docs(db, args.character, args.reference_limit)
    crops = fetch_crop_docs(db, args.character, args.crop_limit)
    if not references:
        raise SystemExit(f"no synced reference images found for {args.character}")
    if not crops:
        raise SystemExit(f"no synced keyframe crops found for {args.character}")

    crop_point_ids = {doc["qdrant_image_point_id"] for doc in crops}
    run_id = utc_stamp()
    receipt_dir = OUT_ROOT / run_id
    receipt_dir.mkdir(parents=True, exist_ok=True)
    now_iso = datetime.now(timezone.utc).isoformat()

    reference_results: list[dict[str, Any]] = []
    best_hits: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for ref in references:
        point = qdrant.get_point(QDRANT_SEMANTIC_COLLECTION, ref["qdrant_image_point_id"])
        vector = image_vector(point)
        if vector is None:
            skipped.append({"reference_key": ref["_key"], "reason": "reference_vector_missing"})
            continue
        query_filter = {
            "must": [
                {"key": "arango_collection", "match": {"value": "watch_keyframe_annotations"}},
                {"key": "modality", "match": {"value": "image_crop"}},
                {"key": "character_name", "match": {"value": args.character}},
            ]
        }
        hits = qdrant.query(
            QDRANT_SEMANTIC_COLLECTION,
            QDRANT_SEMANTIC_IMAGE_VECTOR_NAME,
            vector,
            limit=args.query_limit,
            query_filter=query_filter,
            with_payload=True,
        )
        relevant_hits = [hit for hit in hits if hit.get("id") in crop_point_ids]
        normalized_hits = []
        for hit in relevant_hits:
            payload = hit.get("payload") or {}
            normalized_hits.append(
                {
                    "score": hit.get("score"),
                    "crop_qdrant_point_id": hit.get("id"),
                    "crop_arango_key": payload.get("arango_key"),
                    "crop_path": payload.get("crop_path"),
                    "crop_sha256": payload.get("crop_sha256"),
                    "movie_segment": payload.get("movie_segment"),
                    "timecode": payload.get("timecode"),
                    "row_index": payload.get("row_index"),
                }
            )
        best = normalized_hits[0] if normalized_hits else None
        if best:
            best_hits.append(
                {
                    "reference_key": ref["_key"],
                    "reference_qdrant_point_id": ref["qdrant_image_point_id"],
                    "reference_artifact_path": ref.get("reference_artifact_path"),
                    "best_crop": best,
                }
            )
        reference_results.append(
            {
                "reference_key": ref["_key"],
                "reference_id": ref.get("reference_id"),
                "reference_artifact_path": ref.get("reference_artifact_path"),
                "reference_qdrant_point_id": ref.get("qdrant_image_point_id"),
                "approval_status": ref.get("approval_status"),
                "identity_promotion_allowed": ref.get("identity_promotion_allowed"),
                "hit_count": len(normalized_hits),
                "hits": normalized_hits,
            }
        )

    receipt = {
        "schema": "watch.crop_reference_similarity_receipt.v1",
        "status": "SIMILARITY_QUERIES_COMPLETE",
        "created_at": now_iso,
        "run_id": run_id,
        "character_name": args.character,
        "qdrant_collection": QDRANT_SEMANTIC_COLLECTION,
        "qdrant_image_vector_name": QDRANT_SEMANTIC_IMAGE_VECTOR_NAME,
        "counts": {
            "reference_docs": len(references),
            "crop_docs": len(crops),
            "references_queried": len(reference_results),
            "references_with_crop_hits": len(best_hits),
            "skipped": len(skipped),
        },
        "best_hits": best_hits,
        "reference_results": reference_results,
        "skipped": skipped,
        "proof_scope": {
            "mocked": False,
            "live": True,
            "proves": [
                "Qdrant image vectors for reference images can query Qdrant image vectors for Watch keyframe crops",
                "crop/reference similarity receipts can point back to Arango reference and keyframe records",
            ],
            "does_not_prove": [
                "identity is confirmed",
                "reference images are human-approved clean solo references",
                "a production identity threshold has been calibrated",
            ],
        },
    }
    receipt_path = receipt_dir / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

    for hit in best_hits:
        db.aql.execute(
            """
            UPDATE @key WITH {
              crop_reference_similarity_receipt_path: @receipt_path,
              best_crop_match: @best_crop_match,
              updated_at: @updated_at
            } IN watch_reference_images
            """,
            bind_vars={
                "key": hit["reference_key"],
                "receipt_path": str(receipt_path),
                "best_crop_match": hit["best_crop"],
                "updated_at": now_iso,
            },
        )

    print(json.dumps({"receipt_path": str(receipt_path), "counts": receipt["counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
