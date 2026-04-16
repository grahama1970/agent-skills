"""Backfill multimodal embeddings for datalake_chunks in ArangoDB."""

from __future__ import annotations

import time
from pathlib import Path

import httpx
from loguru import logger

from .visual_score import embed_image

_ARANGO = "http://localhost:8601"
_ARANGO_TIMEOUT = httpx.Timeout(30.0, connect=5.0)
_EMBED_TIMEOUT = httpx.Timeout(60.0, connect=5.0)
_DEFAULT_ROOT = "/mnt/storage12tb/extractor_corpus/results"
_BATCH_SIZE = 10


def backfill_chunk_embeddings(
    chunk_keys: list[str],
    corpus_results_root: str = _DEFAULT_ROOT,
) -> dict:
    """Embed images for chunks and upsert multimodal vectors into ArangoDB."""
    stats = {"processed": 0, "embedded": 0, "skipped": 0, "errors": 0}
    client = httpx.Client(base_url=_ARANGO, timeout=_ARANGO_TIMEOUT)

    for i in range(0, len(chunk_keys), _BATCH_SIZE):
        batch = chunk_keys[i : i + _BATCH_SIZE]
        if i > 0:
            time.sleep(1)

        for key in batch:
            stats["processed"] += 1
            try:
                resp = client.post("/recall/by-keys", json={"collection": "datalake_chunks", "keys": [key]})
                resp.raise_for_status()
                docs = resp.json().get("documents") or resp.json().get("results", [])
                if not docs:
                    logger.warning("chunk {} not found", key)
                    stats["skipped"] += 1
                    continue

                doc = docs[0]
                source_meta = doc.get("source_meta", {})
                image_path = source_meta.get("image_path")
                source = doc.get("source", "")

                if not image_path:
                    logger.debug("chunk {} has no image_path", key)
                    stats["skipped"] += 1
                    continue

                full_path = Path(corpus_results_root) / source / image_path
                if not full_path.exists():
                    logger.debug("image missing: {}", full_path)
                    stats["skipped"] += 1
                    continue

                vector = embed_image(full_path)
                if vector is None:
                    stats["skipped"] += 1
                    continue

                up = client.post("/upsert", json={
                    "collection": "datalake_chunks",
                    "documents": [{"_key": key, "embedding_multimodal": vector}],
                })
                up.raise_for_status()
                stats["embedded"] += 1
                logger.debug("embedded chunk {}", key)

            except Exception as e:
                logger.warning("error processing chunk {}: {}", key, e)
                stats["errors"] += 1

    client.close()
    logger.info("backfill complete: {}", stats)
    return stats


def backfill_by_asset_type(
    asset_type: str,
    limit: int = 100,
    corpus_results_root: str = _DEFAULT_ROOT,
) -> dict:
    """Find chunks by asset_type and backfill their multimodal embeddings."""
    client = httpx.Client(base_url=_ARANGO, timeout=_ARANGO_TIMEOUT)
    try:
        resp = client.post("/list", json={
            "collection": "datalake_chunks",
            "filters": {"asset_type": asset_type},
            "k": limit,
        })
        resp.raise_for_status()
        docs = resp.json().get("documents") or resp.json().get("results", [])
    except Exception as e:
        logger.error("failed to list chunks for asset_type={}: {}", asset_type, e)
        return {"processed": 0, "embedded": 0, "skipped": 0, "errors": 1}
    finally:
        client.close()

    keys = [d["_key"] for d in docs if "_key" in d]
    logger.info("found {} {} chunks to backfill", len(keys), asset_type)
    return backfill_chunk_embeddings(keys, corpus_results_root)
