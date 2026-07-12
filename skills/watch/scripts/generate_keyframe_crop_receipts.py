#!/usr/bin/env python3
"""Generate Watch keyframe crop + multimodal Qdrant receipts.

This script is intentionally receipt-first. It does not claim identity
recognition; it proves that human/ML keyframe boxes can become concrete crop
artifacts with Qdrant image vectors and Arango pointers.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


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
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_env(MEMORY_ROOT / ".env")

# Imported after env load so memory config sees the same runtime as the daemon.
from graph_memory.arango_client import get_db  # noqa: E402
from graph_memory.config import QDRANT_SEMANTIC_COLLECTION  # noqa: E402
from graph_memory.qdrant_client import QdrantClient, QdrantPoint  # noqa: E402
from graph_memory.semantic_sync import (  # noqa: E402
    QDRANT_SEMANTIC_IMAGE_VECTOR_NAME,
    embed_semantic_images,
    ensure_semantic_collection,
)


OUT_ROOT = (
    AGENT_SKILLS_ROOT
    / "skills"
    / "watch"
    / "docs"
    / "architecture"
    / "generated"
    / "watch_multimodal_keyframe_receipts"
)
CROP_ROOT = OUT_ROOT / "crops"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def slug(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in value)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or "value"


def clamp(value: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, value))


def crop_bbox(frame_path: Path, bbox: list[float], crop_path: Path) -> dict[str, Any]:
    with Image.open(frame_path) as img:
        rgb = img.convert("RGB")
        width, height = rgb.size
        x1, y1, x2, y2 = [float(v) for v in bbox]
        x1 = clamp(x1, 0.0, 1.0)
        y1 = clamp(y1, 0.0, 1.0)
        x2 = clamp(x2, 0.0, 1.0)
        y2 = clamp(y2, 0.0, 1.0)
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1
        left = max(0, min(width - 1, round(x1 * width)))
        top = max(0, min(height - 1, round(y1 * height)))
        right = max(left + 1, min(width, round(x2 * width)))
        bottom = max(top + 1, min(height, round(y2 * height)))
        crop = rgb.crop((left, top, right, bottom))
        crop_path.parent.mkdir(parents=True, exist_ok=True)
        crop.save(crop_path, "JPEG", quality=92, optimize=True)
        return {
            "source_width": width,
            "source_height": height,
            "pixel_bbox_xyxy": [left, top, right, bottom],
            "crop_width": right - left,
            "crop_height": bottom - top,
        }


def image_data_uri(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def point_id_for_crop(arango_key: str, crop_hash: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"watch-keyframe-crop/{arango_key}/{crop_hash}"))


def fetch_keyframes(db: Any, character: str, limit: int) -> list[dict[str, Any]]:
    cursor = db.aql.execute(
        """
        FOR d IN watch_keyframe_annotations
          FILTER d.character_name == @character
          FILTER d.lifecycle_status != 'superseded'
          FILTER IS_STRING(d.frame_path) AND d.frame_path != ''
          FILTER IS_ARRAY(d.bbox) AND LENGTH(d.bbox) == 4
          SORT d.updated_at DESC
          LIMIT @limit
          RETURN d
        """,
        bind_vars={"character": character, "limit": limit},
    )
    return list(cursor)


def update_keyframe_doc(db: Any, key: str, patch: dict[str, Any]) -> None:
    db.aql.execute(
        """
        UPDATE @key WITH @patch IN watch_keyframe_annotations
        """,
        bind_vars={"key": key, "patch": patch},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character", default="Willie")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--query-limit", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db = get_db()
    client = QdrantClient()
    ensure_semantic_collection(client)

    docs = fetch_keyframes(db, args.character, args.limit)
    if not docs:
        raise SystemExit(f"no current keyframe annotations found for character={args.character!r}")

    run_id = utc_stamp()
    receipt_dir = OUT_ROOT / run_id
    crop_dir = CROP_ROOT / run_id
    receipt_dir.mkdir(parents=True, exist_ok=True)
    crop_dir.mkdir(parents=True, exist_ok=True)

    crop_inputs: list[tuple[dict[str, Any], Path, dict[str, Any], str]] = []
    skipped: list[dict[str, Any]] = []
    for doc in docs:
        frame_path = Path(str(doc.get("frame_path") or ""))
        if not frame_path.exists():
            skipped.append({"_key": doc.get("_key"), "reason": "frame_path_missing", "frame_path": str(frame_path)})
            continue
        bbox = doc.get("bbox") or []
        crop_name = f"{slug(doc.get('_key', 'keyframe'))}.jpg"
        crop_path = crop_dir / crop_name
        crop_meta = crop_bbox(frame_path, bbox, crop_path)
        crop_hash = sha256_file(crop_path)
        crop_inputs.append((doc, crop_path, crop_meta, crop_hash))

    if not crop_inputs:
        raise SystemExit(f"no crops generated; skipped={skipped}")

    vectors: list[list[float]] = []
    model_name = ""
    model_version = ""
    if not args.dry_run:
        data_uris = [image_data_uri(crop_path) for _, crop_path, _, _ in crop_inputs]
        vectors, model_name, model_version = embed_semantic_images(data_uris, role="document", timeout=60.0)
        if len(vectors) != len(crop_inputs):
            raise RuntimeError(f"embedding count mismatch: expected {len(crop_inputs)} got {len(vectors)}")

    points: list[QdrantPoint] = []
    records: list[dict[str, Any]] = []
    now_iso = datetime.now(timezone.utc).isoformat()
    for index, (doc, crop_path, crop_meta, crop_hash) in enumerate(crop_inputs):
        arango_key = str(doc["_key"])
        point_id = point_id_for_crop(arango_key, crop_hash)
        payload = {
            "arango_collection": "watch_keyframe_annotations",
            "arango_key": arango_key,
            "chunk_id": f"watch_keyframe_annotations/{arango_key}#crop",
            "source": "watch-keyframe-crop-receipt",
            "source_id": f"watch_keyframe_annotations/{arango_key}",
            "asset_uid": doc.get("asset_uid"),
            "row_index": doc.get("row_index"),
            "timecode": doc.get("timecode"),
            "movie_segment": doc.get("movie_segment"),
            "character_name": doc.get("character_name"),
            "actor_name": doc.get("actor_name"),
            "crop_path": str(crop_path),
            "crop_sha256": crop_hash,
            "embedding_model": model_name or None,
            "embedding_version": model_version or None,
            "embedding_role": "document",
            "modality": "image_crop",
            "updated_at": int(time.time()),
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        if not args.dry_run:
            points.append(
                QdrantPoint(
                    point_id=point_id,
                    vectors={QDRANT_SEMANTIC_IMAGE_VECTOR_NAME: vectors[index]},
                    payload=payload,
                )
            )
        records.append(
            {
                "arango_key": arango_key,
                "asset_uid": doc.get("asset_uid"),
                "row_index": doc.get("row_index"),
                "timecode": doc.get("timecode"),
                "movie_segment": doc.get("movie_segment"),
                "character_name": doc.get("character_name"),
                "actor_name": doc.get("actor_name"),
                "bbox": doc.get("bbox"),
                "frame_path": doc.get("frame_path"),
                "crop_path": str(crop_path),
                "crop_sha256": crop_hash,
                "crop_meta": crop_meta,
                "qdrant_collection": QDRANT_SEMANTIC_COLLECTION,
                "qdrant_image_vector_name": QDRANT_SEMANTIC_IMAGE_VECTOR_NAME,
                "qdrant_image_point_id": point_id,
            }
        )

    if points:
        client.upsert(QDRANT_SEMANTIC_COLLECTION, points, wait=True)

    receipt_path = receipt_dir / "receipt.json"
    query_receipt_path = receipt_dir / "qdrant_image_query_receipt.json"
    query_results: list[dict[str, Any]] = []
    if not args.dry_run and vectors:
        query_filter = {
            "must": [
                {"key": "arango_collection", "match": {"value": "watch_keyframe_annotations"}},
                {"key": "character_name", "match": {"value": args.character}},
                {"key": "modality", "match": {"value": "image_crop"}},
            ]
        }
        query_results = client.query(
            QDRANT_SEMANTIC_COLLECTION,
            QDRANT_SEMANTIC_IMAGE_VECTOR_NAME,
            vectors[0],
            limit=args.query_limit,
            query_filter=query_filter,
            with_payload=True,
        )

    receipt = {
        "schema": "watch.keyframe_crop_multimodal_receipt.v1",
        "status": "DRY_RUN" if args.dry_run else "CROP_IMAGE_VECTORS_SYNCED",
        "created_at": now_iso,
        "run_id": run_id,
        "character": args.character,
        "qdrant_collection": QDRANT_SEMANTIC_COLLECTION,
        "qdrant_image_vector_name": QDRANT_SEMANTIC_IMAGE_VECTOR_NAME,
        "embedding_model": model_name or None,
        "embedding_version": model_version or None,
        "counts": {
            "candidate_docs": len(docs),
            "crops_generated": len(records),
            "qdrant_points_upserted": 0 if args.dry_run else len(points),
            "skipped": len(skipped),
            "query_hits": len(query_results),
        },
        "records": records,
        "skipped": skipped,
        "proof_scope": {
            "mocked": False,
            "live": not args.dry_run,
            "proves": [
                "human/ML keyframe bbox records can be converted into concrete image crop artifacts",
                "crop artifacts can be embedded through the configured Jina/local multimodal embedder",
                "crop image vectors can be written to Qdrant with Arango key pointers",
                "watch_keyframe_annotations documents are updated with crop/vector receipt pointers",
            ],
            "does_not_prove": [
                "the character identity classifier is correct",
                "YOLO/ByteTrack is tracking the character across all frames",
                "audio vectors and SRT/Whisper vectors are fused into a final production ranker",
            ],
        },
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

    query_receipt = {
        "schema": "watch.keyframe_crop_qdrant_image_query_receipt.v1",
        "created_at": now_iso,
        "query_source_point_id": records[0]["qdrant_image_point_id"],
        "query_source_crop_path": records[0]["crop_path"],
        "qdrant_collection": QDRANT_SEMANTIC_COLLECTION,
        "qdrant_image_vector_name": QDRANT_SEMANTIC_IMAGE_VECTOR_NAME,
        "hits": [
            {
                "id": hit.get("id"),
                "score": hit.get("score"),
                "payload": hit.get("payload"),
            }
            for hit in query_results
        ],
    }
    query_receipt_path.write_text(json.dumps(query_receipt, indent=2) + "\n")

    if not args.dry_run:
        for record in records:
            update_keyframe_doc(
                db,
                record["arango_key"],
                {
                    "crop_path": record["crop_path"],
                    "crop_sha256": record["crop_sha256"],
                    "qdrant_image_collection": record["qdrant_collection"],
                    "qdrant_image_vector_name": record["qdrant_image_vector_name"],
                    "qdrant_image_point_id": record["qdrant_image_point_id"],
                    "multimodal_receipt_path": str(receipt_path),
                    "multimodal_query_receipt_path": str(query_receipt_path),
                    "multimodal_sync_state": "synced",
                    "updated_at": now_iso,
                },
            )

    print(
        json.dumps(
            {
                "receipt_path": str(receipt_path),
                "query_receipt_path": str(query_receipt_path),
                "counts": receipt["counts"],
                "first_crop_path": records[0]["crop_path"],
                "first_qdrant_image_point_id": records[0]["qdrant_image_point_id"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
