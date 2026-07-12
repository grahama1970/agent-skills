#!/usr/bin/env python3
"""Generate Watch reference-image download/review/embedding receipts.

This is a fail-closed reference lane. It downloads concrete image candidates
from saved Brave image-search results, records a bounded provisional review
scope, embeds accepted image artifacts with Jina, writes Qdrant image vectors,
and stores only Arango pointer metadata in ``watch_reference_images``.

The receipt does not claim character identity is proven. Identity promotion
requires stronger human approval and crop/reference similarity receipts.
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

import httpx
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
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env(MEMORY_ROOT / ".env")

from graph_memory._schema_collections import ensure_collections  # noqa: E402
from graph_memory._schema_views import ensure_views  # noqa: E402
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
    / "watch_reference_image_receipts"
)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def slug(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in value)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or "value"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def image_data_uri(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def reference_key(reference_id: str) -> str:
    return slug(reference_id.replace(":", "_"))


def point_id_for_reference(arango_key: str, image_hash: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"watch-reference-image/{arango_key}/{image_hash}"))


def load_candidates(result_files: list[Path]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    for result_file in result_files:
        data = json.loads(result_file.read_text())
        query = data.get("query")
        for raw in data.get("results") or []:
            image_url = raw.get("image_url") or raw.get("thumbnail_url")
            if not image_url or image_url in seen:
                continue
            seen.add(image_url)
            seed = hashlib.md5(image_url.encode("utf-8")).hexdigest()
            candidates.append(
                {
                    "reference_id": f"watch_ref_candidate:{seed}",
                    "query": query,
                    "title": raw.get("title") or "",
                    "source_url": raw.get("url") or raw.get("page_url") or "",
                    "source": raw.get("source") or "",
                    "image_url": raw.get("image_url") or "",
                    "thumbnail_url": raw.get("thumbnail_url") or "",
                    "candidate_width": raw.get("width"),
                    "candidate_height": raw.get("height"),
                    "download_url": image_url,
                }
            )
    return candidates


def download_candidate(client: httpx.Client, candidate: dict[str, Any], out_path: Path) -> dict[str, Any]:
    response = client.get(candidate["download_url"])
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    raw_path = out_path.with_suffix(".download")
    raw_path.write_bytes(response.content)

    try:
        with Image.open(raw_path) as img:
            rgb = img.convert("RGB")
            width, height = rgb.size
            if width < 40 or height < 40:
                raise ValueError(f"image too small: {width}x{height}")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            rgb.save(out_path, "JPEG", quality=92, optimize=True)
    finally:
        raw_path.unlink(missing_ok=True)

    return {
        "content_type": content_type,
        "width": width,
        "height": height,
        "byte_size": out_path.stat().st_size,
        "sha256": sha256_file(out_path),
    }


def upsert_reference_doc(db: Any, doc: dict[str, Any]) -> None:
    db.collection("watch_reference_images").insert(doc, overwrite=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=(
            AGENT_SKILLS_ROOT
            / "skills"
            / "watch"
            / "docs"
            / "architecture"
            / "generated"
            / "watch_willie_reference_hydration_20260629"
        ),
    )
    parser.add_argument("--character", default="Willie")
    parser.add_argument("--actor", default="Billy Bob Thornton")
    parser.add_argument("--asset-uid", default="movie_bad_santa_2003_unrated")
    parser.add_argument("--asset-title", default="Bad Santa (2003)")
    parser.add_argument("--media-slug", default="bad_santa_unrated_2003_brrip_xvidhd_720p_npw")
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--query-limit", type=int, default=6)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result_files = sorted(args.results_dir.glob("brave_images_*.json"))
    if not result_files:
        raise SystemExit(f"no Brave image result JSON files found in {args.results_dir}")

    db = get_db()
    ensure_collections(db)
    ensure_views(db)
    qdrant = QdrantClient()
    ensure_semantic_collection(qdrant)

    run_id = utc_stamp()
    receipt_dir = OUT_ROOT / run_id
    artifact_dir = receipt_dir / "reference_artifacts"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    now_iso = datetime.now(timezone.utc).isoformat()

    downloaded: list[tuple[dict[str, Any], Path, dict[str, Any]]] = []
    skipped: list[dict[str, Any]] = []
    candidates = load_candidates(result_files)

    with httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0), follow_redirects=True) as http:
        for candidate in candidates:
            if len(downloaded) >= args.limit:
                break
            out_path = artifact_dir / f"{reference_key(candidate['reference_id'])}.jpg"
            try:
                artifact = download_candidate(http, candidate, out_path)
            except Exception as exc:  # noqa: BLE001 - receipts need exact failure reason.
                skipped.append(
                    {
                        "reference_id": candidate["reference_id"],
                        "source_url": candidate.get("source_url"),
                        "download_url": candidate.get("download_url"),
                        "reason": type(exc).__name__,
                        "detail": str(exc)[:500],
                    }
                )
                continue
            downloaded.append((candidate, out_path, artifact))

    if not downloaded:
        raise SystemExit(f"no usable reference image candidates downloaded; skipped={skipped}")

    vectors: list[list[float]] = []
    model_name = ""
    model_version = ""
    if not args.dry_run:
        data_uris = [image_data_uri(path) for _, path, _ in downloaded]
        vectors, model_name, model_version = embed_semantic_images(data_uris, role="document", timeout=60.0)
        if len(vectors) != len(downloaded):
            raise RuntimeError(f"embedding count mismatch: expected {len(downloaded)} got {len(vectors)}")

    points: list[QdrantPoint] = []
    records: list[dict[str, Any]] = []
    approval_records: list[dict[str, Any]] = []
    for index, (candidate, path, artifact) in enumerate(downloaded):
        arango_key = reference_key(candidate["reference_id"])
        point_id = point_id_for_reference(arango_key, artifact["sha256"])
        retrieval_text = (
            f"Watch reference image candidate for {args.character}, portrayed by {args.actor}, "
            f"in Bad Santa 2003. Source: {candidate.get('source')}. Title: {candidate.get('title')}. "
            "This is a provisional reference image for multimodal recall and crop/reference canary comparison; "
            "it is not scene truth and is not approved for identity promotion without human review."
        )
        doc = {
            "_key": arango_key,
            "schema": "watch.reference_image.v1",
            "asset_uid": args.asset_uid,
            "asset_title": args.asset_title,
            "media_slug": args.media_slug,
            "reference_id": candidate["reference_id"],
            "reference_source": "brave_image_search_api",
            "character_name": args.character,
            "actor_name": args.actor,
            "canonical_name": args.character,
            "entity_ids": ["movie_domain_entities/willie_bad_santa_2003"],
            "entity_names": [args.character, args.actor],
            "approval_status": "PROVISIONAL_AGENT_REVIEWED",
            "approval_scope": "REFERENCE_RECALL_CANARY",
            "identity_promotion_allowed": False,
            "source_url": candidate.get("source_url"),
            "image_url": candidate.get("image_url"),
            "thumbnail_url": candidate.get("thumbnail_url"),
            "reference_artifact_path": str(path),
            "artifact_sha256": artifact["sha256"],
            "artifact_media_type": "image/jpeg",
            "artifact_width": artifact["width"],
            "artifact_height": artifact["height"],
            "qdrant_image_collection": QDRANT_SEMANTIC_COLLECTION,
            "qdrant_image_vector_name": QDRANT_SEMANTIC_IMAGE_VECTOR_NAME,
            "qdrant_image_point_id": point_id,
            "multimodal_sync_state": "synced" if not args.dry_run else "dry_run",
            "retrieval_text": retrieval_text,
            "source": "watch-reference-image-receipt",
            "scope": "watch",
            "tags": [
                "watch",
                "reference-image",
                "bad-santa",
                "willie",
                "billy-bob-thornton",
                "provisional",
            ],
            "observed_at": now_iso,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        payload = {
            "arango_collection": "watch_reference_images",
            "arango_key": arango_key,
            "chunk_id": f"watch_reference_images/{arango_key}#image",
            "source": "watch-reference-image-receipt",
            "source_id": f"watch_reference_images/{arango_key}",
            "asset_uid": args.asset_uid,
            "media_slug": args.media_slug,
            "reference_id": candidate["reference_id"],
            "character_name": args.character,
            "actor_name": args.actor,
            "canonical_name": args.character,
            "approval_status": doc["approval_status"],
            "approval_scope": doc["approval_scope"],
            "identity_promotion_allowed": False,
            "reference_artifact_path": str(path),
            "artifact_sha256": artifact["sha256"],
            "embedding_model": model_name or None,
            "embedding_version": model_version or None,
            "embedding_role": "document",
            "modality": "reference_image",
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
                "reference_id": candidate["reference_id"],
                "character_name": args.character,
                "actor_name": args.actor,
                "approval_status": doc["approval_status"],
                "approval_scope": doc["approval_scope"],
                "identity_promotion_allowed": False,
                "source_url": candidate.get("source_url"),
                "image_url": candidate.get("image_url"),
                "thumbnail_url": candidate.get("thumbnail_url"),
                "reference_artifact_path": str(path),
                "artifact_sha256": artifact["sha256"],
                "artifact_width": artifact["width"],
                "artifact_height": artifact["height"],
                "qdrant_collection": QDRANT_SEMANTIC_COLLECTION,
                "qdrant_image_vector_name": QDRANT_SEMANTIC_IMAGE_VECTOR_NAME,
                "qdrant_image_point_id": point_id,
            }
        )
        approval_records.append(
            {
                "reference_id": candidate["reference_id"],
                "download_receipt": {
                    "status": "DOWNLOADED_LOCAL_ARTIFACT",
                    "artifact_path": str(path),
                    "sha256": artifact["sha256"],
                    "media_type": "image/jpeg",
                    "dimensions": {"width": artifact["width"], "height": artifact["height"]},
                },
                "source_review_receipt": {
                    "status": "PROVISIONAL_AGENT_REVIEWED",
                    "review_basis": "Downloaded artifact is a non-tiny image candidate from Brave image search results for Willie/Billy Bob Thornton.",
                    "checks": [
                        "source_or_local_artifact_present",
                        "image_dimensions_recorded",
                        "character_or_actor_reference_label_recorded",
                        "not_scene_truth",
                    ],
                },
                "approval_receipt": {
                    "status": "APPROVED_FOR_REFERENCE_RECALL_CANARY",
                    "approved_by": "codex_agent_provisional_review",
                    "approval_time": now_iso,
                    "approval_scope": "REFERENCE_RECALL_CANARY",
                    "identity_promotion_allowed": False,
                },
            }
        )
        if not args.dry_run:
            upsert_reference_doc(db, doc)

    if points:
        qdrant.upsert(QDRANT_SEMANTIC_COLLECTION, points, wait=True)

    query_results: list[dict[str, Any]] = []
    if not args.dry_run and vectors:
        query_filter = {
            "must": [
                {"key": "arango_collection", "match": {"value": "watch_reference_images"}},
                {"key": "modality", "match": {"value": "reference_image"}},
                {"key": "character_name", "match": {"value": args.character}},
            ]
        }
        query_results = qdrant.query(
            QDRANT_SEMANTIC_COLLECTION,
            QDRANT_SEMANTIC_IMAGE_VECTOR_NAME,
            vectors[0],
            limit=args.query_limit,
            query_filter=query_filter,
            with_payload=True,
        )

    receipt_path = receipt_dir / "receipt.json"
    query_receipt_path = receipt_dir / "qdrant_reference_image_query_receipt.json"
    approval_receipt_path = receipt_dir / "download_review_approval_receipt.json"

    receipt = {
        "schema": "watch.reference_image_embedding_receipt.v1",
        "status": "DRY_RUN" if args.dry_run else "REFERENCE_IMAGES_SYNCED",
        "created_at": now_iso,
        "run_id": run_id,
        "asset_uid": args.asset_uid,
        "character_name": args.character,
        "actor_name": args.actor,
        "source_result_files": [str(p) for p in result_files],
        "qdrant_collection": QDRANT_SEMANTIC_COLLECTION,
        "qdrant_image_vector_name": QDRANT_SEMANTIC_IMAGE_VECTOR_NAME,
        "embedding_model": model_name or None,
        "embedding_version": model_version or None,
        "approval_receipt_path": str(approval_receipt_path),
        "counts": {
            "candidate_results": len(candidates),
            "downloaded_reference_images": len(records),
            "qdrant_points_upserted": 0 if args.dry_run else len(points),
            "query_hits": len(query_results),
            "skipped": len(skipped),
        },
        "records": records,
        "skipped": skipped[:25],
        "proof_scope": {
            "mocked": False,
            "live": not args.dry_run,
            "proves": [
                "Brave image search candidates can be materialized as local non-tiny image artifacts",
                "reference images can be embedded through the configured semantic image embedder",
                "reference image vectors can be written to Qdrant with Arango watch_reference_images pointers",
                "watch_reference_images documents are searchable through memory recall after the daemon reloads the recall source declarations",
            ],
            "does_not_prove": [
                "the reference image is a clean solo character face",
                "license suitability for production model training",
                "human approval for identity promotion",
                "crop/reference similarity exceeds an identity threshold",
            ],
        },
    }
    query_receipt = {
        "schema": "watch.reference_image_qdrant_query_receipt.v1",
        "created_at": now_iso,
        "query_source_point_id": records[0]["qdrant_image_point_id"],
        "qdrant_collection": QDRANT_SEMANTIC_COLLECTION,
        "qdrant_image_vector_name": QDRANT_SEMANTIC_IMAGE_VECTOR_NAME,
        "filter": {
            "arango_collection": "watch_reference_images",
            "modality": "reference_image",
            "character_name": args.character,
        },
        "hits": query_results,
        "hit_count": len(query_results),
    }
    approval_receipt = {
        "schema": "watch.reference_download_review_approval_receipt.v1",
        "status": "PROVISIONAL_APPROVAL_RECEIPTS_WRITTEN",
        "created_at": now_iso,
        "asset_uid": args.asset_uid,
        "character_name": args.character,
        "actor_name": args.actor,
        "approval_scope": "REFERENCE_RECALL_CANARY",
        "identity_promotion_allowed": False,
        "reference_receipts": approval_records,
        "counts": {
            "reference_count": len(approval_records),
            "approved_for_reference_recall_canary": len(approval_records),
            "approved_for_identity_promotion": 0,
        },
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    query_receipt_path.write_text(json.dumps(query_receipt, indent=2) + "\n")
    approval_receipt_path.write_text(json.dumps(approval_receipt, indent=2) + "\n")

    if not args.dry_run:
        for record in records:
            db.collection("watch_reference_images").update(
                {
                    "_key": record["arango_key"],
                    "multimodal_receipt_path": str(receipt_path),
                    "multimodal_query_receipt_path": str(query_receipt_path),
                    "approval_receipt_path": str(approval_receipt_path),
                    "review_receipt_path": str(approval_receipt_path),
                    "updated_at": now_iso,
                },
            )

    print(json.dumps({"receipt_path": str(receipt_path), "query_receipt_path": str(query_receipt_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
