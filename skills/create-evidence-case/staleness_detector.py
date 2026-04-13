"""Staleness detection for QRA lineage tracking.

Detects when QRAs become stale due to:
1. Graph changes (edges added/removed)
2. Entity deprecation (control retired)
3. Upstream QRA changes (prior_qra_evidence modified)
4. Embedding model changes
5. Source document updates

Usage:
    python staleness_detector.py scan --limit 1000
    python staleness_detector.py mark-stale --keys key1,key2,key3
    python staleness_detector.py cascade --control CWE-79
"""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

import httpx
from loguru import logger


SOCKET_PATH = "/run/user/1000/embry/memory.sock"
TIMEOUT = httpx.Timeout(60.0, connect=5.0)


def _get_client() -> httpx.Client:
    transport = httpx.HTTPTransport(uds=SOCKET_PATH)
    return httpx.Client(transport=transport, base_url="http://localhost", timeout=TIMEOUT)


@dataclass
class StalenessResult:
    qra_key: str
    is_stale: bool
    reasons: list[str] = field(default_factory=list)
    entity_ids: list[str] = field(default_factory=list)
    upstream_stale: list[str] = field(default_factory=list)
    review_status: str = "pending"
    assembled_at: str = ""


# ---------------------------------------------------------------------------
# Graph State Queries
# ---------------------------------------------------------------------------

def get_current_graph_version() -> dict[str, Any]:
    """Get current graph state: edge count, version hash."""
    with _get_client() as c:
        # Count edges in sparta_relationships
        r = c.post("/list", json={
            "collection": "sparta_relationships",
            "limit": 1,
        })
        r.raise_for_status()
        total = r.json().get("total", 0)

        # Simple version: edge count as proxy for graph state
        # Future: compute hash of edge set
        return {
            "edge_count": total,
            "version": f"v_{total}_{int(time.time()) // 86400}",
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }


def get_deprecated_controls() -> set[str]:
    """Get set of control IDs that have been deprecated/retired.

    Returns control IDs with status='deprecated' or status='retired'.
    """
    deprecated = set()
    with _get_client() as c:
        for status in ["deprecated", "retired", "superseded"]:
            r = c.post("/list", json={
                "collection": "sparta_controls",
                "limit": 10000,
                "filters": {"status": status},
            })
            if r.status_code == 200:
                for doc in r.json().get("documents", []):
                    cid = doc.get("control_id")
                    if cid:
                        deprecated.add(cid)
    return deprecated


def get_stale_qra_keys() -> set[str]:
    """Get set of QRA keys that are already marked stale."""
    stale = set()
    with _get_client() as c:
        r = c.post("/list", json={
            "collection": "sparta_qra",
            "limit": 100000,
            "filters": {"review_status": "stale"},
        })
        if r.status_code == 200:
            for doc in r.json().get("documents", []):
                key = doc.get("_key")
                if key:
                    stale.add(key)
    return stale


# ---------------------------------------------------------------------------
# Staleness Detection
# ---------------------------------------------------------------------------

def check_qra_staleness(
    qra: dict[str, Any],
    current_graph: dict[str, Any],
    deprecated_controls: set[str],
    stale_upstream_keys: set[str],
) -> StalenessResult:
    """Check if a single QRA is stale.

    Args:
        qra: The QRA document with lineage field
        current_graph: Current graph state from get_current_graph_version()
        deprecated_controls: Set of deprecated control IDs
        stale_upstream_keys: Set of upstream QRA keys that are stale

    Returns:
        StalenessResult with is_stale flag and reasons
    """
    lineage = qra.get("lineage", {})
    result = StalenessResult(
        qra_key=qra.get("_key", ""),
        is_stale=False,
        entity_ids=lineage.get("entity_ids", []),
        review_status=qra.get("review_status", "pending"),
        assembled_at=lineage.get("assembled_at", ""),
    )

    # Check 1: Graph version changed significantly
    old_edge_count = lineage.get("graph_edge_count")
    new_edge_count = current_graph.get("edge_count", 0)
    if old_edge_count is not None and new_edge_count:
        # >10% change in edge count suggests significant graph update
        change_pct = abs(new_edge_count - old_edge_count) / max(old_edge_count, 1)
        if change_pct > 0.10:
            result.is_stale = True
            result.reasons.append(
                f"graph_changed: edges {old_edge_count}→{new_edge_count} ({change_pct:.1%})"
            )

    # Check 2: Entity deprecated
    for eid in lineage.get("entity_ids", []):
        if eid in deprecated_controls:
            result.is_stale = True
            result.reasons.append(f"entity_deprecated: {eid}")

    # Check 3: Upstream QRA is stale
    for upstream_key in lineage.get("upstream_qra_keys", []):
        if upstream_key in stale_upstream_keys:
            result.is_stale = True
            result.upstream_stale.append(upstream_key)
            result.reasons.append(f"upstream_stale: {upstream_key}")

    # Check 4: Embedding model changed (future)
    # For now, we don't track embedding model versions

    # Check 5: Age-based staleness (>90 days without review)
    if lineage.get("assembled_at"):
        try:
            assembled_ts = time.strptime(
                lineage["assembled_at"], "%Y-%m-%dT%H:%M:%SZ"
            )
            age_days = (time.time() - time.mktime(assembled_ts)) / 86400
            if age_days > 90 and result.review_status == "pending":
                result.is_stale = True
                result.reasons.append(f"age_stale: {age_days:.0f} days without review")
        except (ValueError, TypeError):
            pass

    return result


def scan_for_staleness(
    limit: int = 1000,
    collection: str = "sparta_qra",
    only_approved: bool = False,
) -> dict[str, Any]:
    """Scan QRAs for staleness.

    Args:
        limit: Max QRAs to scan
        collection: Collection to scan
        only_approved: If True, only check approved QRAs (highest priority)

    Returns:
        {
            "total_scanned": int,
            "stale_count": int,
            "stale_by_reason": {reason: count},
            "stale_qras": [StalenessResult...],
            "graph_version": current graph state,
        }
    """
    # Get current state
    current_graph = get_current_graph_version()
    deprecated_controls = get_deprecated_controls()
    stale_upstream = get_stale_qra_keys()

    logger.info(
        "Staleness scan: graph_edges={}, deprecated_controls={}, stale_upstream={}",
        current_graph.get("edge_count"),
        len(deprecated_controls),
        len(stale_upstream),
    )

    # Scan QRAs
    stale_results: list[StalenessResult] = []
    stale_by_reason: dict[str, int] = {}

    with _get_client() as c:
        filters = {}
        if only_approved:
            filters["review_status"] = "approved"

        r = c.post("/list", json={
            "collection": collection,
            "limit": limit,
            "filters": filters if filters else None,
        })
        r.raise_for_status()
        docs = r.json().get("documents", [])

        for doc in docs:
            result = check_qra_staleness(
                doc, current_graph, deprecated_controls, stale_upstream
            )
            if result.is_stale:
                stale_results.append(result)
                for reason in result.reasons:
                    reason_type = reason.split(":")[0]
                    stale_by_reason[reason_type] = stale_by_reason.get(reason_type, 0) + 1

    return {
        "total_scanned": len(docs),
        "stale_count": len(stale_results),
        "stale_by_reason": stale_by_reason,
        "stale_qras": stale_results,
        "graph_version": current_graph,
        "deprecated_control_count": len(deprecated_controls),
    }


# ---------------------------------------------------------------------------
# Cascade Analysis
# ---------------------------------------------------------------------------

def _paginated_list(
    client: httpx.Client,
    collection: str,
    filters: dict | None = None,
    max_docs: int | None = 10000,
) -> list[dict]:
    """Paginate through /list endpoint to get all matching documents."""
    PAGE_SIZE = 500
    docs = []
    offset = 0

    while max_docs is None or len(docs) < max_docs:
        payload = {
            "collection": collection,
            "limit": PAGE_SIZE,
            "offset": offset,
        }
        if filters:
            payload["filters"] = filters

        r = client.post("/list", json=payload)
        if r.status_code != 200:
            logger.warning("paginated_list failed at offset {}: {}", offset, r.status_code)
            break

        batch = r.json().get("documents", [])
        if not batch:
            break

        docs.extend(batch)
        offset += PAGE_SIZE

        # Check if we've got all
        total = r.json().get("total", 0)
        if offset >= total:
            break

    return docs[:max_docs]


def cascade_from_control(control_id: str, max_scan: int = 50000) -> dict[str, Any]:
    """Analyze cascade impact if a control is deprecated.

    Shows: "If we deprecate {control_id}, these QRAs become stale,
    and these downstream artifacts need re-review."

    Args:
        control_id: The control to simulate deprecation for
        max_scan: Maximum QRAs to scan for lineage/indirect impact

    Returns:
        {
            "control_id": str,
            "direct_impact": [QRA keys that reference this control],
            "indirect_impact": [QRA keys that reference impacted QRAs],
            "total_impact": int,
            "by_review_status": {status: count},
        }
    """
    direct_impact: list[str] = []
    indirect_impact: list[str] = []
    by_status: dict[str, int] = {}

    with _get_client() as c:
        # Find QRAs that directly reference this control (paginated)
        direct_docs = _paginated_list(c, "sparta_qra", {"source_control_id": control_id})
        logger.debug("cascade direct filter: found {} docs", len(direct_docs))

        for doc in direct_docs:
            key = doc.get("_key")
            status = doc.get("review_status", "pending")
            if key:
                direct_impact.append(key)
                by_status[status] = by_status.get(status, 0) + 1

        # Find QRAs that have entity_ids containing this control (paginated scan)
        all_docs = _paginated_list(c, "sparta_qra", max_docs=max_scan)
        direct_set = set(direct_impact)

        for doc in all_docs:
            key = doc.get("_key")
            if key in direct_set:
                continue
            lineage = doc.get("lineage", {})
            entity_ids = lineage.get("entity_ids", [])
            if control_id in entity_ids:
                direct_impact.append(key)
                direct_set.add(key)
                status = doc.get("review_status", "pending")
                by_status[status] = by_status.get(status, 0) + 1

        # Find indirect impact (QRAs that use impacted QRAs as upstream evidence)
        for doc in all_docs:
            key = doc.get("_key")
            if key in direct_set:
                continue
            lineage = doc.get("lineage", {})
            upstream = lineage.get("upstream_qra_keys", [])
            if any(u in direct_set for u in upstream):
                indirect_impact.append(key)
                status = doc.get("review_status", "pending")
                by_status[f"indirect_{status}"] = by_status.get(f"indirect_{status}", 0) + 1

    return {
        "control_id": control_id,
        "direct_impact": direct_impact,
        "direct_count": len(direct_impact),
        "indirect_impact": indirect_impact,
        "indirect_count": len(indirect_impact),
        "total_impact": len(direct_impact) + len(indirect_impact),
        "by_review_status": by_status,
        "scanned": len(all_docs) if 'all_docs' in dir() else 0,
    }


# ---------------------------------------------------------------------------
# Mark Stale
# ---------------------------------------------------------------------------

def mark_qras_stale(keys: list[str], reason: str) -> dict[str, Any]:
    """Mark QRAs as stale by updating review_status.

    Args:
        keys: QRA keys to mark stale
        reason: Reason for staleness (stored in _staleness_reason)

    Returns:
        {ok: bool, updated: int, errors: list}
    """
    updated = 0
    errors = []

    with _get_client() as c:
        for key in keys:
            # Fetch current document
            r = c.post("/recall/by-keys", json={
                "keys": [key],
                "collection": "sparta_qra",
            })
            if r.status_code != 200:
                errors.append({"key": key, "error": "not found"})
                continue

            docs = r.json().get("documents", [])
            if not docs:
                errors.append({"key": key, "error": "not found"})
                continue

            doc = docs[0]

            # Only mark stale if not already stale or rejected
            current_status = doc.get("review_status", "pending")
            if current_status in ("stale", "rejected"):
                continue

            # Update to stale
            doc["review_status"] = "stale"
            doc["_staleness_reason"] = reason
            doc["_marked_stale_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            store_r = c.post("/store", json={
                "document": doc,
                "collection": "sparta_qra",
            })
            if store_r.status_code == 200:
                updated += 1
            else:
                errors.append({"key": key, "error": store_r.text[:100]})

    return {
        "ok": len(errors) == 0,
        "updated": updated,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Lineage Backfill
# ---------------------------------------------------------------------------

def _get_embedding(text: str) -> list[float] | None:
    """Get embedding for text from embedding service."""
    try:
        resp = httpx.post(
            "http://localhost:8602/embed",
            json={"text": text[:2000]},  # Truncate long texts
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json().get("embedding")
    except Exception as e:
        logger.warning("Embedding failed: {}", e)
    return None


def _process_batch_lineage(
    docs: list[dict],
    dry_run: bool,
    enrich_v43,
    assemble_evidence_batch,
) -> list[dict[str, Any]]:
    """Process a batch of documents for lineage backfill.

    Uses daemon batch endpoint for evidence assembly (much faster).
    Returns list of {key, status, embedded, error?}
    """
    # Build batch items: (question, control_id)
    items = []
    doc_map = {}  # Map question to doc for result matching
    skipped = []

    for doc in docs:
        key = doc.get("_key", "")
        question = doc.get("question", doc.get("problem", ""))
        control_id = doc.get("control_id", "")

        if not question:
            skipped.append({"key": key, "status": "skipped"})
            continue

        items.append((question, control_id))
        doc_map[question] = doc

    if not items:
        return skipped

    # Batch assemble evidence
    batch_results = assemble_evidence_batch(items, max_workers=8)

    results = list(skipped)

    # Process batch results
    docs_to_store = []
    for br in batch_results:
        question = br.get("question", "")
        doc = doc_map.get(question)
        if not doc:
            continue

        key = doc.get("_key", "")
        control_id = doc.get("control_id", "")
        evidence = br.get("evidence", {})

        try:
            if br.get("error") or evidence.get("error"):
                # Can't enrich without evidence, but we can add minimal lineage
                doc["lineage"] = {
                    "graph_version": "unknown",
                    "graph_edge_count": None,
                    "entity_ids": [],
                    "entity_frameworks": [],
                    "upstream_qra_keys": [],
                    "source_doc_hashes": [],
                    "embedding_model": "unknown",
                    "extractor_version": "v43",
                    "assembled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "_backfill_error": br.get("error") or evidence.get("error"),
                }
            else:
                # Enrich with full lineage
                enriched = enrich_v43(
                    evidence=evidence,
                    question=question,
                    source_control_id=control_id if control_id else None,
                )
                doc["lineage"] = enriched.get("lineage", {})

            # Add embedding if missing
            embedded = False
            if not doc.get("embedding"):
                emb = _get_embedding(question)
                if emb:
                    doc["embedding"] = emb
                    embedded = True

            # Remove system fields that can't be written back
            doc.pop("_rev", None)
            doc.pop("_id", None)
            docs_to_store.append(doc)
            results.append({"key": key, "status": "updated", "embedded": embedded})

        except Exception as exc:
            results.append({"key": key, "status": "error", "error": str(exc)[:200], "embedded": False})

    # Batch store all docs
    if not dry_run and docs_to_store:
        try:
            with _get_client() as c:
                store_r = c.post("/upsert", json={
                    "documents": docs_to_store,
                    "collection": "sparta_qra",
                })
                if store_r.status_code != 200:
                    logger.warning("Batch store failed: {}", store_r.text[:200])
        except Exception as exc:
            logger.warning("Batch store exception: {}", exc)

    return results


def backfill_lineage(
    batch_size: int = 100,
    max_docs: int = 1000,
    dry_run: bool = True,
    max_workers: int = 16,
) -> dict[str, Any]:
    """Backfill lineage field for QRAs that don't have it.

    Incrementally processes QRAs missing lineage and enriches them with:
    - entity_ids, entity_frameworks
    - upstream_qra_keys
    - graph_version, embedding_model
    - assembled_at timestamp
    - embedding (if missing)

    Uses daemon batch endpoint + ThreadPoolExecutor for parallel batches.

    Args:
        batch_size: Number of QRAs to process per daemon batch call
        max_docs: Maximum total QRAs to process
        dry_run: If True, don't persist changes
        max_workers: Number of concurrent batch workers

    Returns:
        {processed, updated, skipped, errors, dry_run}
    """
    from daemon_client import assemble_evidence_batch, enrich_v43

    processed = 0
    updated = 0
    skipped = 0
    embedded = 0
    errors_list = []

    from queue import Queue, Empty
    from threading import Thread

    logger.info("Lineage backfill: batch_size={}, max_docs={}, dry_run={}, workers={}",
                batch_size, max_docs, dry_run, max_workers)

    # Producer-consumer: fetch and process concurrently
    PAGE_SIZE = batch_size
    batch_queue: Queue = Queue(maxsize=max_workers * 2)  # Buffer 2x workers
    total_estimate = [None]  # Use list for mutability in thread
    fetch_done = [False]
    batches_fetched = [0]
    lock = Lock()

    start_time = time.time()
    completed_batches = [0]
    all_results = []

    def fetch_batches():
        """Producer: page through documents and queue batches."""
        offset = 0
        with _get_client() as c:
            while max_docs is None or offset < max_docs:
                payload = {
                    "collection": "sparta_qra",
                    "limit": PAGE_SIZE,
                    "offset": offset,
                    "filters": {"lineage": None},
                }
                try:
                    r = c.post("/list", json=payload, timeout=30.0)
                    if r.status_code != 200:
                        logger.warning("Pagination failed at offset {}: {}", offset, r.status_code)
                        break

                    data = r.json()
                    batch = data.get("documents", [])
                    if not batch:
                        break

                    batch_queue.put(batch)
                    offset += len(batch)
                    batches_fetched[0] += 1

                    # Get total estimate on first page
                    if total_estimate[0] is None:
                        total_estimate[0] = data.get("total", 0)
                        if max_docs is not None:
                            total_estimate[0] = min(total_estimate[0], max_docs)
                        logger.info("{} QRAs missing lineage (will process up to {})",
                                   data.get("total", 0), max_docs or "all")

                    # Stop if we've got enough
                    if max_docs and offset >= max_docs:
                        break

                except Exception as exc:
                    logger.warning("Fetch error at offset {}: {}", offset, exc)
                    break

        fetch_done[0] = True

    def process_batch(batch_docs):
        """Process a single batch."""
        results = _process_batch_lineage(batch_docs, dry_run, enrich_v43, assemble_evidence_batch)
        with lock:
            completed_batches[0] += 1
            elapsed = time.time() - start_time
            docs_done = completed_batches[0] * batch_size
            rate = docs_done / elapsed if elapsed > 0 else 0
            est_total = total_estimate[0] or batches_fetched[0] * batch_size
            eta = (est_total - docs_done) / rate if rate > 0 else 0
            logger.info("Batch {}: {:.1f}/s, ETA {:.0f}s",
                        completed_batches[0], rate, eta)
        return results

    # Start producer thread
    fetch_thread = Thread(target=fetch_batches, daemon=True)
    fetch_thread.start()

    # Process batches as they arrive
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        while True:
            try:
                batch = batch_queue.get(timeout=0.5)
                futures.append(executor.submit(process_batch, batch))
            except Empty:
                if fetch_done[0] and batch_queue.empty():
                    break

        for future in as_completed(futures):
            try:
                batch_results = future.result()
                all_results.extend(batch_results)
            except Exception as exc:
                errors_list.append({"key": "batch", "error": str(exc)[:200]})

    fetch_thread.join(timeout=5.0)

    # Aggregate results
    for result in all_results:
        processed += 1
        status = result.get("status")
        if status == "updated":
            updated += 1
            if result.get("embedded"):
                embedded += 1
        elif status == "skipped":
            skipped += 1
        elif status == "error":
            errors_list.append({"key": result.get("key"), "error": result.get("error")})

    elapsed = time.time() - start_time
    logger.info("Completed {} docs in {:.1f}s ({:.1f}/s)", processed, elapsed, processed/elapsed if elapsed > 0 else 0)

    return {
        "processed": processed,
        "updated": updated,
        "skipped": skipped,
        "embedded": embedded,
        "errors": errors_list,
        "error_count": len(errors_list),
        "dry_run": dry_run,
        "elapsed_seconds": elapsed,
        "rate_per_second": processed / elapsed if elapsed > 0 else 0,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python staleness_detector.py scan [--limit N] [--approved-only]")
        print("  python staleness_detector.py cascade <control_id>")
        print("  python staleness_detector.py mark-stale <key1,key2,...> <reason>")
        print("  python staleness_detector.py backfill-lineage [--limit N] [--workers N] [--execute]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "scan":
        limit = 1000
        approved_only = False
        for i, arg in enumerate(sys.argv[2:]):
            if arg == "--limit" and i + 3 < len(sys.argv):
                limit = int(sys.argv[i + 3])
            if arg == "--approved-only":
                approved_only = True

        result = scan_for_staleness(limit=limit, only_approved=approved_only)
        print(f"\n{'='*60}")
        print("STALENESS SCAN REPORT")
        print(f"{'='*60}")
        print(f"\nScanned: {result['total_scanned']} QRAs")
        print(f"Stale: {result['stale_count']} ({result['stale_count']/max(1,result['total_scanned']):.1%})")
        print(f"\nGraph version: {result['graph_version']['version']}")
        print(f"Deprecated controls in corpus: {result['deprecated_control_count']}")
        print("\nStale by reason:")
        for reason, count in sorted(result["stale_by_reason"].items(), key=lambda x: -x[1]):
            print(f"  {reason}: {count}")

        if result["stale_qras"][:10]:
            print("\nSample stale QRAs:")
            for sr in result["stale_qras"][:10]:
                print(f"  {sr.qra_key}: {', '.join(sr.reasons)}")

    elif cmd == "cascade":
        if len(sys.argv) < 3:
            print("Usage: python staleness_detector.py cascade <control_id>")
            sys.exit(1)

        control_id = sys.argv[2]
        result = cascade_from_control(control_id)

        print(f"\n{'='*60}")
        print(f"CASCADE ANALYSIS: {control_id}")
        print(f"{'='*60}")
        print(f"\nIf {control_id} is deprecated:")
        print(f"  Direct impact: {result['direct_count']} QRAs")
        print(f"  Indirect impact: {result['indirect_count']} QRAs")
        print(f"  Total impact: {result['total_impact']} QRAs")
        print("\nBy review status:")
        for status, count in sorted(result["by_review_status"].items()):
            print(f"  {status}: {count}")

        if result["direct_impact"][:5]:
            print("\nSample direct impact QRA keys:")
            for key in result["direct_impact"][:5]:
                print(f"  {key}")

    elif cmd == "mark-stale":
        if len(sys.argv) < 4:
            print("Usage: python staleness_detector.py mark-stale <key1,key2,...> <reason>")
            sys.exit(1)

        keys = sys.argv[2].split(",")
        reason = sys.argv[3]
        result = mark_qras_stale(keys, reason)
        print(json.dumps(result, indent=2))

    elif cmd == "backfill-lineage":
        limit = 100
        dry_run = True
        workers = 16
        for i, arg in enumerate(sys.argv[2:]):
            if arg == "--limit" and i + 3 < len(sys.argv):
                limit = int(sys.argv[i + 3])
            if arg == "--workers" and i + 3 < len(sys.argv):
                workers = int(sys.argv[i + 3])
            if arg == "--execute":
                dry_run = False

        result = backfill_lineage(max_docs=limit, dry_run=dry_run, max_workers=workers)

        print(f"\n{'='*60}")
        print("LINEAGE BACKFILL REPORT")
        print(f"{'='*60}")
        print(f"\nMode: {'DRY RUN' if result['dry_run'] else 'EXECUTE'}")
        print(f"Workers: {workers}")
        print(f"Processed: {result['processed']} QRAs")
        print(f"Updated: {result['updated']}")
        print(f"Embedded: {result.get('embedded', 0)} (new embeddings added)")
        print(f"Skipped: {result['skipped']}")
        print(f"Errors: {result['error_count']}")
        if result.get('elapsed_seconds'):
            print(f"Elapsed: {result['elapsed_seconds']:.1f}s ({result.get('rate_per_second', 0):.1f}/s)")

        if result["errors"][:5]:
            print("\nSample errors:")
            for err in result["errors"][:5]:
                print(f"  {err['key']}: {err['error'][:80]}")

        if result["dry_run"]:
            print("\n*** DRY RUN: No changes written. Use --execute to apply. ***")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
