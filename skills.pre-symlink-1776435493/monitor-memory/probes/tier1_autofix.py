"""Tier 1 auto-fix helpers for embedding, taxonomy, edges, and orphans.

Extracted from tier1_data.py to keep probe files under 800 LOC.
All functions are imported by tier1_data.py probes.

Inputs: ArangoDB db handle, config thresholds.
Outputs: bool (whether fix was applied).
"""
from __future__ import annotations
import os

import subprocess
import time

from loguru import logger

import config


def _get_db():
    """Lazy import to avoid crashing if ArangoDB is unreachable at import time."""
    from db import get_db
    return get_db()


# ── Shared helpers ───────────────────────────────────────────────────────────


def check_embedding_service() -> bool:
    """Pre-flight health check before batch embedding."""
    import httpx
    try:
        resp = httpx.get(f"{config.EMBEDDING_SERVICE_URL}/health", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def log_autofix(probe_id: str, fixed: int, remaining: int, duration_s: float):
    """Track auto-fix progress over time."""
    import json as _json
    entry = {"ts": int(time.time()), "probe": probe_id, "fixed": fixed,
             "remaining": remaining, "duration_s": round(duration_s, 1)}
    log = config.STATE_DIR / "autofix_log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a") as f:
        f.write(_json.dumps(entry) + "\n")


def batch_embed_and_insert(db, texts: list[dict], collection: str,
                           embed_collection: str | None, text_fields: list[str]) -> int:
    """Embed a batch of documents and insert into the appropriate collection.

    Returns number of documents successfully embedded.
    """
    import httpx
    fixed = 0
    batch_size = 64
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        for doc in batch:
            text_parts = [str(doc.get(f) or "") for f in text_fields]
            text = " ".join(t for t in text_parts if t).strip()
            if not text:
                continue
            try:
                resp = httpx.post(
                    f"{config.EMBEDDING_SERVICE_URL.rstrip('/')}/embed",
                    json={"text": text},
                    timeout=30,
                )
                if resp.status_code != 200:
                    continue
                vec = resp.json().get("vector", [])
                if not vec:
                    continue
            except Exception as e:
                logger.warning("Embedding failed for {}/{}: {}", collection, doc["_key"], e)
                continue

            ts = int(time.time())
            if embed_collection:
                embed_doc = {
                    "_key": f"{doc['_key']}_embed",
                    "lesson_id": f"{collection}/{doc['_key']}",
                    "vector": vec,
                    "dim": len(vec),
                    "updated_at": ts,
                }
                try:
                    db.collection(embed_collection).insert(embed_doc)
                except Exception:
                    try:
                        db.collection(embed_collection).update(embed_doc)
                    except Exception:
                        continue
            else:
                try:
                    db.aql.execute(
                        f"UPDATE {{_key: @key}} WITH {{embedding: @vec, _embedding_pending: null, updated_at: @ts}} IN {collection}",
                        bind_vars={"key": doc["_key"], "vec": vec, "ts": ts},
                    )
                except Exception:
                    continue
            fixed += 1
    return fixed


# ── P01 autofix: embeddings ──────────────────────────────────────────────────


def autofix_embeddings() -> bool:
    """Batch-embed lessons missing from lesson_embeddings."""
    if not check_embedding_service():
        logger.warning("Embedding service unreachable, skipping autofix")
        return False
    db = _get_db()
    t0 = time.time()
    missing = list(db.aql.execute("""
        LET embedded = (FOR e IN lesson_embeddings RETURN DISTINCT e.lesson_id)
        FOR l IN lessons
            FILTER CONCAT("lessons/", l._key) NOT IN embedded
            LIMIT @limit
            RETURN {_key: l._key, problem: l.problem, playbook: l.playbook}
    """, bind_vars={"limit": config.EMBEDDING_FIX_BATCH}))
    if not missing:
        return False
    fixed = batch_embed_and_insert(
        db, missing, "lessons", "lesson_embeddings", ["problem", "playbook"],
    )
    log_autofix("P01", fixed, len(missing) - fixed, time.time() - t0)
    logger.info("P01 autofix: embedded {}/{} lessons", fixed, len(missing))
    return fixed > 0


# ── P02 autofix: taxonomy ────────────────────────────────────────────────────


def autofix_taxonomy_batch(db, limit: int | None = None) -> bool:
    """Batch-fix lessons with empty bridge_attributes using taxonomy extraction."""
    limit = limit or config.TAXONOMY_FIX_BATCH
    t0 = time.time()
    aql = """
    FOR l IN lessons
        FILTER l.bridge_attributes == null OR LENGTH(l.bridge_attributes) == 0
        SORT l.created_at DESC
        LIMIT @limit
        RETURN {_key: l._key, problem: l.problem, solution: l.playbook, tags: l.tags}
    """
    try:
        lessons = list(db.aql.execute(aql, bind_vars={"limit": limit}))
    except Exception:
        return False

    if not lessons:
        return False

    try:
        from common.taxonomy import extract_taxonomy_features, ContentType
    except ImportError:
        logger.warning("P02 autofix: common.taxonomy not available")
        return False

    fixed = 0
    now = int(time.time())
    for lesson in lessons:
        try:
            description = f"{lesson.get('problem', '')}\n\n{lesson.get('solution', '')}"
            tax = extract_taxonomy_features(
                content_type=ContentType.OPERATIONAL,
                description=description,
                tags=lesson.get("tags", []),
                high_fidelity=True,
            )
            bridge = tax.get("bridge_attributes", [])
            tactical = tax.get("tactical_tags", [])
            existing_tags = lesson.get("tags", []) or []
            merged_tags = list(set(existing_tags + bridge + tactical))

            db.aql.execute(
                """UPDATE {_key: @key} WITH {
                    taxonomy: @tax, bridge_attributes: @bridge,
                    tags: @tags, updated_at: @ts
                } IN lessons""",
                bind_vars={
                    "key": lesson["_key"], "tax": tax,
                    "bridge": bridge, "tags": merged_tags, "ts": now,
                },
            )
            fixed += 1
        except Exception as e:
            logger.warning("P02 autofix failed for {}: {}", lesson["_key"], e)

    log_autofix("P02", fixed, len(lessons) - fixed, time.time() - t0)
    logger.info("P02 autofix: enriched {}/{} lessons", fixed, len(lessons))
    return fixed > 0


# ── P10 autofix: backup ──────────────────────────────────────────────────────


def autofix_backup() -> bool:
    """Trigger ops-arango dump."""
    ops_arango = config.PROJECT_ROOT / ".pi/skills/ops-arango/run.sh"
    if not ops_arango.exists():
        logger.warning("ops-arango not found, cannot auto-fix backup")
        return False
    try:
        result = subprocess.run(
            [str(ops_arango), "dump"],
            capture_output=True, text=True, timeout=300,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.error("Backup autofix failed: {}", e)
        return False


# ── P11 autofix: edges ───────────────────────────────────────────────────────


def autofix_edges() -> bool:
    """Run edge-verifier hint-sweep via /assistant cascade."""
    edge_verifier = config.PROJECT_ROOT / ".pi/skills/edge-verifier/run.sh"
    if not edge_verifier.exists():
        return _autofix_edges_fallback()
    try:
        result = subprocess.run(
            [str(edge_verifier), "hint-sweep", "--task-monitor", "--json-stream"],
            capture_output=True, text=True, timeout=config.EDGE_FIX_TIMEOUT,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.error("Edge autofix via edge-verifier failed: {}", e)
        return False


def _autofix_edges_fallback() -> bool:
    """Fallback: run memory-agent propose if edge-verifier unavailable."""
    try:
        result = subprocess.run(
            ["memory-agent", "propose"],
            capture_output=True, text=True, timeout=config.EDGE_FIX_TIMEOUT,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        logger.error("Edge autofix fallback failed: {}", e)
        return False


# ── P12 autofix: duplicates ──────────────────────────────────────────────────


def autofix_duplicates(ops_arango) -> bool:
    """Run ops-arango duplicates --fix."""
    try:
        result = subprocess.run(
            [str(ops_arango), "duplicates", "--fix"],
            capture_output=True, text=True, timeout=120,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.error("Duplicates autofix failed: {}", e)
        return False


# ── P25 autofix: orphaned lessons ────────────────────────────────────────────


def autofix_orphaned_lessons(db, orphaned_ids: list[str]) -> bool:
    """Create edges for orphaned lessons by finding similar lessons via embedding cosine similarity."""
    fixed = 0
    now = int(time.time())
    for lesson_id in orphaned_ids[:config.ORPHAN_FIX_BATCH]:
        try:
            emb_rows = list(db.aql.execute("""
                FOR emb IN lesson_embeddings
                    FILTER emb.lesson_id == @lid
                    LET v = emb.embedding != null ? emb.embedding : emb.vector
                    FILTER v != null
                    LIMIT 1
                    RETURN v
            """, bind_vars={"lid": lesson_id}))
            if not emb_rows:
                continue
            vec = emb_rows[0]

            similar = list(db.aql.execute("""
                FOR emb IN lesson_embeddings
                    FILTER emb.lesson_id != @lid
                    LET v = emb.embedding != null ? emb.embedding : emb.vector
                    FILTER v != null
                    LET sim = COSINE_SIMILARITY(v, @vec)
                    FILTER sim >= 0.65
                    SORT sim DESC
                    LIMIT 5
                    RETURN {lesson_id: emb.lesson_id, similarity: sim}
            """, bind_vars={"lid": lesson_id, "vec": vec}))

            for hit in similar:
                target_id = hit["lesson_id"]
                sim = hit["similarity"]
                for frm, to in [(lesson_id, target_id), (target_id, lesson_id)]:
                    try:
                        db.aql.execute(
                            """UPSERT {_from: @f, _to: @t, type: "related"}
                               INSERT {_from: @f, _to: @t, type: "related", weight: @w,
                                       confidence: @w, approved: true, status: "active",
                                       source: "monitor-memory-P25",
                                       created_at: @ts, updated_at: @ts}
                               UPDATE {weight: @w, confidence: @w, updated_at: @ts}
                               IN lesson_edges""",
                            bind_vars={"f": frm, "t": to, "w": sim, "ts": now},
                        )
                    except Exception as e:
                        logger.debug("db failed: {}", e)
            fixed += 1
        except Exception as e:
            logger.warning("P25 autofix failed for {}: {}", lesson_id, e)
    logger.info("P25 autofix: created edges for {}/{} orphaned lessons", fixed, len(orphaned_ids))
    return fixed > 0


# ── P26 autofix: heuristic taxonomy ──────────────────────────────────────────


def autofix_heuristic_taxonomy(db, limit: int = 25) -> bool:
    """Re-run high-fidelity taxonomy extraction on lessons with heuristic-only taxonomy."""
    aql = """
    FOR l IN lessons
        FILTER l.taxonomy == null
            OR l.taxonomy.method == null
            OR l.taxonomy.method == "none"
            OR l.taxonomy.method == "heuristic"
        SORT l.created_at DESC
        LIMIT @limit
        RETURN {_key: l._key, problem: l.problem, solution: l.playbook, tags: l.tags}
    """
    try:
        lessons = list(db.aql.execute(aql, bind_vars={"limit": limit}))
    except Exception:
        return False

    if not lessons:
        return False

    fixed = 0
    try:
        from common.taxonomy import extract_taxonomy_features, ContentType
    except ImportError:
        logger.warning("P26 autofix: common.taxonomy not available")
        return False

    now = int(time.time())
    for lesson in lessons:
        try:
            description = f"{lesson.get('problem', '')}\n\n{lesson.get('solution', '')}"
            tax = extract_taxonomy_features(
                content_type=ContentType.OPERATIONAL,
                description=description,
                tags=lesson.get("tags", []),
                high_fidelity=True,
            )
            bridge = tax.get("bridge_attributes", [])
            tactical = tax.get("tactical_tags", [])
            existing_tags = lesson.get("tags", []) or []
            merged_tags = list(set(existing_tags + bridge + tactical))

            db.aql.execute(
                """UPDATE {_key: @key} WITH {
                    taxonomy: @tax,
                    bridge_attributes: @bridge,
                    tags: @tags,
                    updated_at: @ts
                } IN lessons""",
                bind_vars={
                    "key": lesson["_key"],
                    "tax": tax,
                    "bridge": bridge,
                    "tags": merged_tags,
                    "ts": now,
                },
            )
            fixed += 1
        except Exception as e:
            logger.warning("P26 autofix failed for {}: {}", lesson["_key"], e)

    logger.info("P26 autofix: re-enriched {}/{} lessons", fixed, len(lessons))
    return fixed > 0


# ── P28 autofix: universal embedding ─────────────────────────────────────────


def autofix_universal_embedding(db, collection: str) -> bool:
    """Embed missing documents for the worst-coverage collection."""
    coll_config = config.EMBEDDABLE_COLLECTIONS.get(collection)
    if not coll_config:
        return False
    text_fields, embed_coll = coll_config

    if not text_fields:
        return False
    if not check_embedding_service():
        logger.warning("Embedding service unreachable, skipping P28 autofix")
        return False

    t0 = time.time()
    if embed_coll and db.has_collection(embed_coll):
        if collection == "lessons":
            id_field = "lesson_id"
            prefix = "lessons/"
        else:
            id_field = "source_id"
            prefix = f"{collection}/"
        missing = list(db.aql.execute(f"""
            LET embedded = (FOR e IN {embed_coll} RETURN DISTINCT e.{id_field})
            FOR d IN {collection}
                FILTER CONCAT("{prefix}", d._key) NOT IN embedded
                LIMIT @limit
                RETURN KEEP(d, APPEND(["_key"], @fields))
        """, bind_vars={"limit": config.EMBEDDING_FIX_BATCH, "fields": text_fields}))
    else:
        field_list = ", ".join(f'"{f}"' for f in text_fields)
        missing = list(db.aql.execute(f"""
            FOR d IN {collection}
                FILTER d.embedding == null OR LENGTH(d.embedding) == 0
                LIMIT @limit
                RETURN KEEP(d, APPEND(["_key"], [{field_list}]))
        """, bind_vars={"limit": config.EMBEDDING_FIX_BATCH}))

    if not missing:
        return False

    fixed = batch_embed_and_insert(db, missing, collection, embed_coll, text_fields)
    log_autofix("P28", fixed, len(missing) - fixed, time.time() - t0)
    logger.info("P28 autofix: embedded {}/{} docs in {}", fixed, len(missing), collection)
    return fixed > 0
