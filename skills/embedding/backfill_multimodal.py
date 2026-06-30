"""Backfill multimodal embeddings on ArangoDB documents via vLLM.

Two fields:
  - embedding_multimodal: 2048d text embedding (Qwen3-VL text path)
  - embedding_visual:     2048d image embedding (Qwen3-VL image path)

For datalake_chunks with source_meta.image_path → embeds the actual PNG image.
For text-only collections → embeds extracted text.

Naturally resumable: queries for docs missing the target field.

Usage:
    uv run python backfill_multimodal.py status
    uv run python backfill_multimodal.py embed --dry-run
    uv run python backfill_multimodal.py embed
    uv run python backfill_multimodal.py embed-images --dry-run
    uv run python backfill_multimodal.py embed-images
    uv run python backfill_multimodal.py verify
"""
from __future__ import annotations

import base64
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

import httpx
import numpy as np
import typer
from loguru import logger
from tqdm import tqdm

app = typer.Typer(help="Backfill multimodal embeddings via vLLM (Qwen3-VL-Embedding-2B)")

FIELD_TEXT = "embedding_multimodal"
FIELD_VISUAL = "embedding_visual"
CONTAINER_NAME = os.environ.get("EMBEDDING_CONTAINER_MM", "embry-embedding-mm")
SERVICE_URL = os.environ.get("EMBEDDING_MULTIMODAL_URL", "http://127.0.0.1:8603")
MODEL_NAME = "Qwen/Qwen3-VL-Embedding-2B"
EXPECTED_DIMS = int(os.environ.get("EMBEDDING_MULTIMODAL_DIMENSIONS", "2048"))

# Base path for extractor output images on 12TB
EXTRACTOR_CORPUS_BASE = Path(os.environ.get(
    "EXTRACTOR_CORPUS_BASE", "/mnt/storage12tb/extractor_corpus/results"
))

MAX_RETRIES = 5
RETRY_BACKOFF_S = 10.0
MAX_TEXT_CHARS = 2048

# ---------------------------------------------------------------------------
# Text extractors per collection
# ---------------------------------------------------------------------------

COLLECTION_TEXT_EXTRACTORS: Dict[str, Callable[[dict], str]] = {
    "lessons": lambda d: f"{d.get('title', '')} {d.get('problem', '')} {d.get('solution', '')}".strip(),
    "doc_chunks": lambda d: f"{d.get('title', '')} {d.get('content', '')}".strip(),
    "code_symbols": lambda d: f"{d.get('name', '')} {d.get('kind', '')} {d.get('signature', '')} {d.get('docstring', '')}".strip(),
    "agent_conversations": lambda d: f"{d.get('topic', '')} {d.get('body', '')} {d.get('summary', '')}".strip(),
    "lean_theorems": lambda d: f"{d.get('lean_code', '')} {d.get('notes', '')} {d.get('error', '')}".strip(),
    "task_states": lambda d: f"{d.get('task', '')} {d.get('status', '')} {d.get('notes', '')}".strip(),
    "sparta_qra": lambda d: f"{d.get('question', '')} {d.get('answer', '')} {d.get('reasoning', '')}".strip(),
    "sparta_url_knowledge": lambda d: f"{d.get('text', '')} {d.get('topic', '')} {d.get('name', '')} {d.get('description', '')}".strip(),
    "sparta_controls": lambda d: f"{d.get('name', '')} {d.get('description', '')}".strip(),
    "datalake_chunks": lambda d: d.get("text", "").strip(),
}

# ---------------------------------------------------------------------------
# Service interaction
# ---------------------------------------------------------------------------


def _restart_container() -> bool:
    """Restart the vLLM Docker container. Returns True if healthy."""
    logger.warning("Service down — restarting container '{}'...", CONTAINER_NAME)
    try:
        result = subprocess.run(
            ["docker", "restart", CONTAINER_NAME],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            logger.error("docker restart failed: {}", result.stderr.strip())
            return False
        for attempt in range(60):
            time.sleep(3)
            try:
                resp = httpx.get(f"{SERVICE_URL}/health", timeout=3.0)
                if resp.status_code == 200:
                    logger.info("Container healthy after {}s", (attempt + 1) * 3)
                    return True
            except Exception:
                continue
        logger.error("Container restarted but not healthy after 180s")
        return False
    except Exception as e:
        logger.error("Failed to restart container: {}", e)
        return False


def _encode_text_batch(texts: List[str]) -> List[List[float]]:
    """Encode texts via vLLM /v1/embeddings with retry."""
    texts = [t[:MAX_TEXT_CHARS] for t in texts]
    payload = {"model": MODEL_NAME, "input": texts, "encoding_format": "float"}

    for attempt in range(MAX_RETRIES):
        try:
            resp = httpx.post(f"{SERVICE_URL}/v1/embeddings", json=payload, timeout=120.0)
            if resp.status_code == 200:
                data = resp.json()
                vectors = [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]
                if len(vectors) != len(texts):
                    raise ValueError(f"Expected {len(texts)} vectors, got {len(vectors)}")
                return vectors
            raise ConnectionError(f"vLLM returned {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            remaining = MAX_RETRIES - attempt - 1
            if remaining > 0:
                wait = RETRY_BACKOFF_S * (attempt + 1)
                logger.warning("Text batch failed: {}. Retrying in {:.0f}s ({} left)...", e, wait, remaining)
                time.sleep(wait)
                if attempt >= 1:
                    _restart_container()
            else:
                raise RuntimeError(f"vLLM text embedding failed after {MAX_RETRIES} attempts: {e}") from e
    return []


def _mean_pool_and_normalize(token_vectors: list) -> List[float]:
    """Mean-pool per-token vectors and L2-normalize."""
    arr = np.array(token_vectors, dtype=np.float32)
    pooled = arr.mean(axis=0)
    norm = np.linalg.norm(pooled)
    return (pooled / norm).tolist() if norm > 0 else pooled.tolist()


def _encode_image(image_path: str) -> Optional[List[float]]:
    """Encode a single image via vLLM /pooling endpoint. Returns mean-pooled 2048d vector."""
    p = Path(image_path)
    if not p.exists():
        logger.debug("Image not found: {}", image_path)
        return None

    with open(p, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    suffix = p.suffix.lstrip(".").lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(suffix, "image/png")
    data_uri = f"data:{mime};base64,{b64}"

    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": data_uri}},
        ]}],
    }

    for attempt in range(MAX_RETRIES):
        try:
            resp = httpx.post(f"{SERVICE_URL}/pooling", json=payload, timeout=120.0)
            if resp.status_code == 200:
                data = resp.json()
                token_vectors = data["data"][0]["data"]
                return _mean_pool_and_normalize(token_vectors)
            raise ConnectionError(f"vLLM pooling returned {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            remaining = MAX_RETRIES - attempt - 1
            if remaining > 0:
                wait = RETRY_BACKOFF_S * (attempt + 1)
                logger.warning("Image embed failed: {}. Retrying in {:.0f}s ({} left)...", e, wait, remaining)
                time.sleep(wait)
                if attempt >= 1:
                    _restart_container()
            else:
                logger.error("Image embedding failed after {} attempts: {}", MAX_RETRIES, e)
                return None
    return None


def _resolve_image_path(doc: dict, doc_path_cache: dict) -> Optional[str]:
    """Resolve the full image path from a datalake_chunks document.

    source_meta.image_path is relative to the extractor output dir.
    The parent datalake_docs.path gives the output dir base.
    """
    sm = doc.get("source_meta", {})
    rel_path = sm.get("image_path")
    if not rel_path:
        return None

    # Get the parent doc's output dir from cache (populated by _get_image_page)
    output_dir = doc_path_cache.get(doc.get("doc_id"))
    if output_dir:
        full_path = Path(output_dir) / rel_path
        if full_path.exists():
            return str(full_path)

    # Fallback: try under extractor corpus base with source hash as dir name
    source = doc.get("source", "")
    if source:
        for base in [EXTRACTOR_CORPUS_BASE, Path("${HOME}/workspace/experiments/pi-mono/.pi/skills/review-pdf/extracted_runs")]:
            full_path = base / source / rel_path
            if full_path.exists():
                return str(full_path)

    # Fallback: try as absolute path
    if Path(rel_path).exists():
        return rel_path

    return None


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _get_db():
    """Get ArangoDB connection."""
    sys.path.insert(0, os.path.expanduser("~/workspace/experiments/memory/src"))
    from graph_memory.arango_client import get_db
    return get_db()


def _count_without_field(db, collection_name: str, field: str) -> int:
    aql = """
    RETURN LENGTH(
        FOR doc IN @@collection
            FILTER NOT HAS(doc, @field) OR doc.@field == null
            RETURN 1
    )
    """
    return list(db.aql.execute(aql, bind_vars={"@collection": collection_name, "field": field}))[0]


def _get_page(db, collection_name: str, field: str, page_size: int) -> List[dict]:
    aql = """
    FOR doc IN @@collection
        FILTER NOT HAS(doc, @field) OR doc.@field == null
        LIMIT @page_size
        RETURN UNSET(doc, "embedding", "embedding_2", "embedding_old",
                     "embedding_multimodal", "embedding_visual")
    """
    return list(db.aql.execute(aql, bind_vars={
        "@collection": collection_name, "field": field, "page_size": page_size,
    }))


def _get_image_page(db, page_size: int) -> List[dict]:
    """Get datalake_chunks that have source_meta.image_path but no embedding_visual."""
    aql = """
    FOR doc IN datalake_chunks
        FILTER doc.source_meta.image_path != null
        FILTER NOT HAS(doc, @field) OR doc.@field == null
        LIMIT @page_size
        RETURN UNSET(doc, "embedding", "embedding_2", "embedding_old",
                     "embedding_multimodal", "embedding_visual")
    """
    return list(db.aql.execute(aql, bind_vars={"field": FIELD_VISUAL, "page_size": page_size}))


def _count_image_docs(db) -> int:
    """Count datalake_chunks with image_path but no embedding_visual."""
    aql = """
    RETURN LENGTH(
        FOR doc IN datalake_chunks
            FILTER doc.source_meta.image_path != null
            FILTER NOT HAS(doc, @field) OR doc.@field == null
            RETURN 1
    )
    """
    return list(db.aql.execute(aql, bind_vars={"field": FIELD_VISUAL}))[0]


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def embed(
    collection: Optional[str] = typer.Option(None, "-c", "--collection", help="Specific collection (default: all)"),
    batch_size: int = typer.Option(32, "-b", "--batch-size", help="Batch size"),
    limit: int = typer.Option(0, "-l", "--limit", help="Max docs per collection (0=all)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done"),
):
    """Backfill embedding_multimodal (text) field on all collections."""
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)

    db = _get_db()

    try:
        resp = httpx.get(f"{SERVICE_URL}/health", timeout=5.0)
        resp.raise_for_status()
        logger.info("vLLM service healthy at {}", SERVICE_URL)
    except Exception as e:
        logger.warning("vLLM service unreachable at {}: {}", SERVICE_URL, e)

    if not dry_run:
        try:
            test_resp = httpx.post(
                f"{SERVICE_URL}/v1/embeddings",
                json={"model": MODEL_NAME, "input": ["dimension test"], "encoding_format": "float"},
                timeout=30.0,
            )
            if test_resp.status_code == 200:
                test_dim = len(test_resp.json()["data"][0]["embedding"])
                logger.info("Text: {}-dim vectors (expected {})", test_dim, EXPECTED_DIMS)
        except Exception as e:
            logger.warning("Could not verify dimensions: {}", e)

    collections = [collection] if collection else list(COLLECTION_TEXT_EXTRACTORS.keys())
    total_embedded = 0
    total_skipped = 0
    total_errors = 0
    page_size = batch_size * 20

    for coll_name in collections:
        if not db.has_collection(coll_name):
            logger.info("Collection '{}' does not exist, skipping", coll_name)
            continue

        extractor = COLLECTION_TEXT_EXTRACTORS.get(coll_name)
        if not extractor:
            continue

        need_count = _count_without_field(db, coll_name, FIELD_TEXT)
        if need_count == 0:
            logger.info("{}: all docs have '{}'", coll_name, FIELD_TEXT)
            continue

        if limit:
            need_count = min(need_count, limit)

        logger.info("{}: {} docs need '{}'", coll_name, need_count, FIELD_TEXT)

        if dry_run:
            sample = _get_page(db, coll_name, FIELD_TEXT, 3)
            for doc in sample:
                text = extractor(doc)
                print(f"  Would embed text: {text[:80]}...")
            if need_count > 3:
                print(f"  ... and {need_count - 3} more")
            continue

        embedded = 0
        skipped = 0
        errors = 0
        pbar = tqdm(total=need_count, desc=f"  {coll_name}")

        while embedded + skipped + errors < need_count:
            remaining = need_count - embedded - skipped - errors
            fetch_size = min(page_size, remaining)
            docs = _get_page(db, coll_name, FIELD_TEXT, fetch_size)
            if not docs:
                break

            for i in range(0, len(docs), batch_size):
                batch = docs[i:i + batch_size]
                texts = []
                valid_docs = []

                for doc in batch:
                    text = extractor(doc)
                    if text.strip():
                        texts.append(text)
                        valid_docs.append(doc)
                    else:
                        skipped += 1
                        pbar.update(1)

                if not texts:
                    continue

                try:
                    embeddings = _encode_text_batch(texts)
                    coll = db.collection(coll_name)
                    for doc, emb in zip(valid_docs, embeddings):
                        try:
                            coll.update({"_key": doc["_key"], FIELD_TEXT: emb})
                            embedded += 1
                        except Exception as e:
                            logger.error("Error updating {}/{}: {}", coll_name, doc["_key"], e)
                            errors += 1
                        pbar.update(1)
                except Exception as e:
                    logger.error("FATAL batch error in {}: {}", coll_name, e)
                    errors += len(texts)
                    pbar.update(len(texts))
                    break
            else:
                continue
            break

        pbar.close()
        logger.info("Done: {} embedded, {} skipped, {} errors", embedded, skipped, errors)
        total_embedded += embedded
        total_skipped += skipped
        total_errors += errors

    print(f"\n{'DRY RUN - ' if dry_run else ''}Total: {total_embedded} text embedded, {total_skipped} skipped, {total_errors} errors")


@app.command("embed-images")
def embed_images(
    limit: int = typer.Option(0, "-l", "--limit", help="Max docs (0=all)"),
    workers: int = typer.Option(16, "-w", "--workers", help="Concurrent embedding workers"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done"),
):
    """Backfill embedding_visual field on datalake_chunks that have source_meta.image_path.

    Uses concurrent workers to saturate the GPU. Each worker: read PNG → base64 → POST /pooling → mean pool → write ArangoDB.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)

    db = _get_db()

    try:
        resp = httpx.get(f"{SERVICE_URL}/health", timeout=5.0)
        resp.raise_for_status()
        logger.info("vLLM service healthy at {}", SERVICE_URL)
    except Exception as e:
        logger.warning("vLLM service unreachable at {}: {}", SERVICE_URL, e)

    need_count = _count_image_docs(db)
    if need_count == 0:
        logger.info("All image docs already have '{}'", FIELD_VISUAL)
        return

    if limit:
        need_count = min(need_count, limit)

    logger.info("datalake_chunks: {} docs with images need '{}' ({} workers)", need_count, FIELD_VISUAL, workers)

    # Build cache: doc_id → output dir path from datalake_docs
    logger.info("Building doc_id → output_dir cache from datalake_docs...")
    doc_path_cache = {}
    aql_paths = """
    FOR doc IN datalake_docs
        FILTER doc.path != null
        RETURN { _key: doc._key, path: doc.path }
    """
    for row in db.aql.execute(aql_paths):
        doc_path_cache[row["_key"]] = row["path"]
    logger.info("Cached {} doc output dirs", len(doc_path_cache))

    if dry_run:
        sample = _get_image_page(db, 5)
        for doc in sample:
            rel_path = doc.get("source_meta", {}).get("image_path", "?")
            full_path = _resolve_image_path(doc, doc_path_cache)
            exists = "EXISTS" if full_path else "NOT FOUND"
            print(f"  {rel_path} → {full_path or '?'} [{exists}]")
        if need_count > 5:
            print(f"  ... and {need_count - 5} more")
        return

    embedded = 0
    skipped = 0
    errors = 0
    not_found = 0
    page_size = workers * 10  # Fetch enough docs to keep all workers busy
    pbar = tqdm(total=need_count, desc="  embed-images")

    def _process_one(doc: dict) -> tuple:
        """Worker: resolve path → encode image → return (key, vector, status)."""
        full_path = _resolve_image_path(doc, doc_path_cache)
        if not full_path:
            return (doc["_key"], None, "not_found")
        try:
            vec = _encode_image(full_path)
            if vec is None:
                return (doc["_key"], None, "skipped")
            return (doc["_key"], vec, "ok")
        except Exception as e:
            logger.error("Error embedding {}: {}", full_path, e)
            return (doc["_key"], None, "error")

    coll = db.collection("datalake_chunks")

    while embedded + skipped + errors + not_found < need_count:
        docs = _get_image_page(db, page_size)
        if not docs:
            break

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_process_one, doc): doc for doc in docs}

            for future in as_completed(futures):
                key, vec, status = future.result()
                if status == "ok" and vec is not None:
                    try:
                        coll.update({"_key": key, FIELD_VISUAL: vec})
                        embedded += 1
                    except Exception as e:
                        logger.error("DB update failed for {}: {}", key, e)
                        errors += 1
                elif status == "not_found":
                    not_found += 1
                elif status == "skipped":
                    skipped += 1
                else:
                    errors += 1
                pbar.update(1)

    pbar.close()
    logger.info("Done: {} embedded, {} skipped, {} not_found, {} errors", embedded, skipped, not_found, errors)
    if not_found > 0:
        logger.warning("{} images not found on disk — check EXTRACTOR_CORPUS_BASE={}", not_found, EXTRACTOR_CORPUS_BASE)


@app.command()
def status():
    """Show embedding coverage for both text and visual fields."""
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)

    db = _get_db()

    try:
        resp = httpx.get(f"{SERVICE_URL}/health", timeout=3.0)
        svc = "RUNNING" if resp.status_code == 200 else f"ERROR ({resp.status_code})"
    except Exception as e:
        svc = f"UNREACHABLE ({e})"
    print(f"vLLM Service: {svc} ({SERVICE_URL})")
    print(f"Model: {MODEL_NAME} | Dimensions: {EXPECTED_DIMS}")
    print()

    # Text embeddings
    print(f"=== Text Embeddings (field: '{FIELD_TEXT}') ===")
    print(f"{'Collection':25} {'Coverage':>15}  {'%':>6}  Status")
    print("-" * 65)

    total_docs = 0
    total_with = 0

    for coll_name in COLLECTION_TEXT_EXTRACTORS.keys():
        if not db.has_collection(coll_name):
            print(f"  {coll_name:25} NOT EXISTS")
            continue

        coll = db.collection(coll_name)
        count = coll.count()
        total_docs += count

        aql = """
        RETURN LENGTH(
            FOR doc IN @@collection
                FILTER doc.@field != null AND HAS(doc, @field)
                RETURN 1
        )
        """
        with_emb = list(db.aql.execute(aql, bind_vars={"@collection": coll_name, "field": FIELD_TEXT}))[0]
        total_with += with_emb

        pct = (with_emb / count * 100) if count > 0 else 0
        icon = "DONE" if pct == 100 else "PARTIAL" if pct > 0 else "NONE"
        print(f"  {coll_name:25} {with_emb:>6}/{count:<6}  {pct:5.1f}%  {icon}")

    print("-" * 65)
    total_pct = (total_with / total_docs * 100) if total_docs > 0 else 0
    print(f"  {'TOTAL':25} {total_with:>6}/{total_docs:<6}  {total_pct:5.1f}%")

    # Visual embeddings
    print()
    print(f"=== Visual Embeddings (field: '{FIELD_VISUAL}') ===")
    if db.has_collection("datalake_chunks"):
        # Count docs with image_path
        aql_with_img = """
        RETURN LENGTH(
            FOR doc IN datalake_chunks
                FILTER doc.source_meta.image_path != null
                RETURN 1
        )
        """
        total_with_img = list(db.aql.execute(aql_with_img))[0]

        aql_with_vis = """
        RETURN LENGTH(
            FOR doc IN datalake_chunks
                FILTER doc.source_meta.image_path != null
                FILTER doc.embedding_visual != null AND HAS(doc, "embedding_visual")
                RETURN 1
        )
        """
        with_vis = list(db.aql.execute(aql_with_vis))[0]

        pct = (with_vis / total_with_img * 100) if total_with_img > 0 else 0
        icon = "DONE" if pct == 100 else "PARTIAL" if pct > 0 else "NONE"
        print(f"  {'datalake_chunks (images)':25} {with_vis:>6}/{total_with_img:<6}  {pct:5.1f}%  {icon}")
    else:
        print("  datalake_chunks collection not found")


@app.command()
def verify():
    """Verify vLLM service works for both text and image embedding."""
    print(f"1. Service health ({SERVICE_URL})...")
    try:
        resp = httpx.get(f"{SERVICE_URL}/health", timeout=5.0)
        print(f"   OK: status {resp.status_code}")
    except Exception as e:
        print(f"   FAIL: {e}")
        raise typer.Exit(1)

    print("2. Text embedding...")
    try:
        resp = httpx.post(
            f"{SERVICE_URL}/v1/embeddings",
            json={"model": MODEL_NAME, "input": ["test query"], "encoding_format": "float"},
            timeout=30.0,
        )
        vec = resp.json()["data"][0]["embedding"]
        print(f"   OK: {len(vec)}-dim vector")
    except Exception as e:
        print(f"   FAIL: {e}")
        raise typer.Exit(1)

    print("3. Image embedding (synthetic test image)...")
    try:
        from PIL import Image
        import io
        img = Image.new("RGB", (100, 100), color="red")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        data_uri = f"data:image/png;base64,{b64}"

        resp = httpx.post(f"{SERVICE_URL}/pooling", json={
            "model": MODEL_NAME,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": data_uri}},
            ]}],
        }, timeout=60.0)
        token_vecs = resp.json()["data"][0]["data"]
        pooled = _mean_pool_and_normalize(token_vecs)
        print(f"   OK: {len(pooled)}-dim vector (mean-pooled from {len(token_vecs)} tokens)")
    except Exception as e:
        print(f"   FAIL: {e}")
        raise typer.Exit(1)

    print("\nAll checks passed.")


if __name__ == "__main__":
    app()
