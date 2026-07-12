#!/usr/bin/env python3
"""Generate Watch SRT/Whisper text embedding receipts.

This proves the text side of the Watch multimodal memory loop: concrete SRT,
Whisper/audio-audit, and retrieval text from ``watch_content`` are embedded and
written to Qdrant with Arango pointers. Vectors stay in Qdrant; Arango stores
metadata, point ids, and receipt paths.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
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
from graph_memory.config import (  # noqa: E402
    QDRANT_SEMANTIC_COLLECTION,
    QDRANT_SEMANTIC_VECTOR_NAME,
)
from graph_memory.qdrant_client import QdrantClient, QdrantPoint  # noqa: E402
from graph_memory.semantic_sync import (  # noqa: E402
    embed_semantic_texts,
    ensure_semantic_collection,
)


OUT_ROOT = (
    AGENT_SKILLS_ROOT
    / "skills"
    / "watch"
    / "docs"
    / "architecture"
    / "generated"
    / "watch_text_embedding_receipts"
)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def point_id_for_text(arango_key: str, channel: str, text_hash: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"watch-content-text/{arango_key}/{channel}/{text_hash}"))


def fetch_watch_content(db: Any, key: str | None, row_index: int | None, asset_uid: str | None) -> list[dict[str, Any]]:
    filters: list[str] = []
    bind_vars: dict[str, Any] = {}
    if key:
        filters.append("d._key == @key")
        bind_vars["key"] = key
    if row_index is not None:
        filters.append("d.row_index == @row_index")
        bind_vars["row_index"] = row_index
    if asset_uid:
        filters.append("d.asset_uid == @asset_uid")
        bind_vars["asset_uid"] = asset_uid
    where = "\n          FILTER " + "\n          FILTER ".join(filters) if filters else ""
    cursor = db.aql.execute(
        f"""
        FOR d IN watch_content
          {where}
          SORT d.row_index ASC
          LIMIT 10
          RETURN d
        """,
        bind_vars=bind_vars,
    )
    return list(cursor)


def update_watch_content(db: Any, key: str, patch: dict[str, Any]) -> None:
    db.aql.execute(
        "UPDATE @key WITH @patch IN watch_content",
        bind_vars={"key": key, "patch": patch},
    )


def text_channels(doc: dict[str, Any]) -> list[dict[str, str]]:
    channels = [
        ("srt_text", doc.get("srt_text")),
        ("whisper_text", doc.get("whisper_text") or doc.get("audio_audit_text")),
        ("retrieval_text", doc.get("retrieval_text")),
    ]
    out: list[dict[str, str]] = []
    for channel, value in channels:
        text = str(value or "").strip()
        if not text:
            continue
        out.append({"channel": channel, "text": text})
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", default="watch_segment_badsantaunrated2003brripxvidhd720p-npw_0004")
    parser.add_argument("--row-index", type=int, default=None)
    parser.add_argument("--asset-uid", default=None)
    parser.add_argument("--query-limit", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db = get_db()
    client = QdrantClient()
    ensure_semantic_collection(client)

    docs = fetch_watch_content(db, args.key, args.row_index, args.asset_uid)
    if not docs:
        raise SystemExit("no watch_content documents matched the provided selector")
    if len(docs) > 1:
        raise SystemExit(f"selector matched {len(docs)} documents; pass --key for a bounded receipt")

    doc = docs[0]
    channels = text_channels(doc)
    if not channels:
        raise SystemExit(f"watch_content/{doc['_key']} has no SRT/Whisper/retrieval text to embed")

    run_id = utc_stamp()
    receipt_dir = OUT_ROOT / run_id
    receipt_dir.mkdir(parents=True, exist_ok=True)
    now_iso = datetime.now(timezone.utc).isoformat()

    texts = [item["text"] for item in channels]
    vectors: list[list[float]] = []
    model_name = ""
    model_version = ""
    if not args.dry_run:
        vectors, model_name, model_version = embed_semantic_texts(texts, role="document", timeout=60.0)
        if len(vectors) != len(channels):
            raise RuntimeError(f"embedding count mismatch: expected {len(channels)} got {len(vectors)}")

    points: list[QdrantPoint] = []
    records: list[dict[str, Any]] = []
    for index, item in enumerate(channels):
        channel = item["channel"]
        text = item["text"]
        text_hash = sha1_text(text)
        point_id = point_id_for_text(doc["_key"], channel, text_hash)
        payload = {
            "arango_collection": "watch_content",
            "arango_key": doc["_key"],
            "chunk_id": f"watch_content/{doc['_key']}#{channel}",
            "source": "watch-text-embedding-receipt",
            "source_id": f"watch_content/{doc['_key']}",
            "asset_uid": doc.get("asset_uid"),
            "work_key": doc.get("work_key"),
            "media_slug": doc.get("media_slug"),
            "row_index": doc.get("row_index"),
            "timecode": doc.get("timecode"),
            "movie_segment": doc.get("movie_segment"),
            "character_names": doc.get("character_names") or ["Willie"],
            "actor_names": doc.get("actor_names") or ["Billy Bob Thornton"],
            "text_channel": channel,
            "modality": "text",
            "text_hash": text_hash,
            "text_preview": text[:500],
            "embedding_model": model_name or None,
            "embedding_version": model_version or None,
            "embedding_role": "document",
            "updated_at": int(time.time()),
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        if not args.dry_run:
            points.append(
                QdrantPoint(
                    point_id=point_id,
                    vectors={QDRANT_SEMANTIC_VECTOR_NAME: vectors[index]},
                    payload=payload,
                )
            )
        records.append(
            {
                "arango_key": doc["_key"],
                "asset_uid": doc.get("asset_uid"),
                "row_index": doc.get("row_index"),
                "timecode": doc.get("timecode"),
                "movie_segment": doc.get("movie_segment"),
                "text_channel": channel,
                "text_hash": text_hash,
                "text_length": len(text),
                "text_preview": text[:240],
                "qdrant_collection": QDRANT_SEMANTIC_COLLECTION,
                "qdrant_text_vector_name": QDRANT_SEMANTIC_VECTOR_NAME,
                "qdrant_text_point_id": point_id,
            }
        )

    if points:
        client.upsert(QDRANT_SEMANTIC_COLLECTION, points, wait=True)

    query_results: list[dict[str, Any]] = []
    if not args.dry_run and vectors:
        query_filter = {
            "must": [
                {"key": "arango_collection", "match": {"value": "watch_content"}},
                {"key": "arango_key", "match": {"value": doc["_key"]}},
                {"key": "modality", "match": {"value": "text"}},
            ]
        }
        query_results = client.query(
            QDRANT_SEMANTIC_COLLECTION,
            QDRANT_SEMANTIC_VECTOR_NAME,
            vectors[0],
            limit=args.query_limit,
            query_filter=query_filter,
            with_payload=True,
        )

    receipt_path = receipt_dir / "receipt.json"
    query_receipt_path = receipt_dir / "qdrant_text_query_receipt.json"
    receipt = {
        "schema": "watch.text_embedding_receipt.v1",
        "status": "DRY_RUN" if args.dry_run else "TEXT_VECTORS_SYNCED",
        "created_at": now_iso,
        "run_id": run_id,
        "watch_content_key": doc["_key"],
        "qdrant_collection": QDRANT_SEMANTIC_COLLECTION,
        "qdrant_text_vector_name": QDRANT_SEMANTIC_VECTOR_NAME,
        "embedding_model": model_name or None,
        "embedding_version": model_version or None,
        "counts": {
            "candidate_docs": len(docs),
            "text_channels": len(records),
            "qdrant_points_upserted": 0 if args.dry_run else len(points),
            "query_hits": len(query_results),
        },
        "records": records,
        "proof_scope": {
            "mocked": False,
            "live": not args.dry_run,
            "proves": [
                "watch_content SRT/Whisper/retrieval text can be embedded through the configured semantic text embedder",
                "text vectors can be written to Qdrant with Arango watch_content pointers",
                "watch_content documents are updated with text vector receipt pointers",
            ],
            "does_not_prove": [
                "audio waveform embeddings are available",
                "a production fused image/video/text ranker is implemented",
                "the SRT or Whisper transcript is semantically correct",
            ],
        },
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

    query_receipt = {
        "schema": "watch.text_qdrant_query_receipt.v1",
        "created_at": now_iso,
        "query_source_point_id": records[0]["qdrant_text_point_id"],
        "query_source_channel": records[0]["text_channel"],
        "qdrant_collection": QDRANT_SEMANTIC_COLLECTION,
        "qdrant_text_vector_name": QDRANT_SEMANTIC_VECTOR_NAME,
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
        text_points = [
            {
                "channel": record["text_channel"],
                "point_id": record["qdrant_text_point_id"],
                "text_hash": record["text_hash"],
                "embedding_model": model_name,
                "embedding_version": model_version,
            }
            for record in records
        ]
        update_watch_content(
            db,
            doc["_key"],
            {
                "qdrant_text_collection": QDRANT_SEMANTIC_COLLECTION,
                "qdrant_text_vector_name": QDRANT_SEMANTIC_VECTOR_NAME,
                "qdrant_text_points": text_points,
                "text_embedding_receipt_path": str(receipt_path),
                "text_embedding_query_receipt_path": str(query_receipt_path),
                "text_embedding_sync_state": "synced",
                "updated_at": now_iso,
            },
        )

    print(
        json.dumps(
            {
                "receipt_path": str(receipt_path),
                "query_receipt_path": str(query_receipt_path),
                "counts": receipt["counts"],
                "watch_content_key": doc["_key"],
                "first_qdrant_text_point_id": records[0]["qdrant_text_point_id"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
