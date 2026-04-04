"""Backfill taxonomy on F-36 lessons that were ingested without bridge_attributes.

Usage:
    python -m sparta_stress_test.enrich_f36_taxonomy [--scope fort_worth_f36] [--limit 5000] [--dry-run]

Queries all lessons in the target scope missing bridge_attributes,
extracts taxonomy via fast keyword mode, and updates ArangoDB.
"""

from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

import typer
from loguru import logger

app = typer.Typer(no_args_is_help=True, add_completion=False)

# Import bridge extraction from store.py (canonical source)
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))
from graph_memory.lessons.store import BRIDGE_KEYWORDS, extract_bridges_fast


def _get_db() -> Any:
    """Get ArangoDB handle via memory project's client."""
    from graph_memory.arango_client import get_db
    return get_db()


def _query_missing_taxonomy(db: Any, scope: str, limit: int, *, force_all: bool = False) -> List[Dict]:
    """Find lessons in scope with empty/null/weak bridge_attributes.

    If force_all=True, re-enriches ALL lessons in scope (useful when
    existing taxonomy was low-quality heuristic with confidence 0.3).
    """
    if force_all:
        aql = """
        FOR d IN lessons
          FILTER d.scope == @scope
          LIMIT @limit
          RETURN { _key: d._key, problem: d.problem, solution: d.solution,
                   playbook: d.playbook, title: d.title, tags: d.tags,
                   bridge_attributes: d.bridge_attributes }
        """
    else:
        aql = """
        FOR d IN lessons
          FILTER d.scope == @scope
          FILTER d.bridge_attributes == null OR LENGTH(d.bridge_attributes) == 0
          LIMIT @limit
          RETURN { _key: d._key, problem: d.problem, solution: d.solution,
                   playbook: d.playbook, title: d.title, tags: d.tags,
                   bridge_attributes: d.bridge_attributes }
        """
    return list(db.aql.execute(aql, bind_vars={"scope": scope, "limit": limit}))


def _update_taxonomy(db: Any, key: str, bridges: List[str], tags: List[str]) -> None:
    """Update a lesson's bridge_attributes and tags in ArangoDB."""
    db.aql.execute(
        """UPDATE {_key: @key} WITH {
            bridge_attributes: @bridges,
            taxonomy_method: "backfill-keyword",
            tags: @tags,
            updated_at: @ts
        } IN lessons""",
        bind_vars={
            "key": key,
            "bridges": bridges,
            "tags": tags,
            "ts": int(time.time()),
        },
    )


@app.command()
def enrich(
    scope: str = typer.Option("fort_worth_f36", help="Scope to backfill"),
    limit: int = typer.Option(5000, help="Max docs to process"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Don't write to DB"),
    force_all: bool = typer.Option(False, "--force-all", help="Re-enrich ALL lessons, not just missing"),
):
    """Backfill taxonomy on lessons missing bridge_attributes."""
    db = _get_db()

    mode = "ALL" if force_all else "missing-only"
    logger.info(f"Querying lessons in scope={scope} ({mode}, limit={limit})...")
    docs = _query_missing_taxonomy(db, scope, limit, force_all=force_all)
    logger.info(f"Found {len(docs)} lessons needing taxonomy enrichment")

    if not docs:
        logger.info("Nothing to enrich.")
        return

    enriched = 0
    failed = 0
    bridge_counter: Counter = Counter()
    start = time.monotonic()

    for i, doc in enumerate(docs):
        # Build text from available fields
        parts = []
        for field in ("problem", "solution", "playbook", "title"):
            val = doc.get(field)
            if val and isinstance(val, str):
                parts.append(val)
        tag_vals = doc.get("tags") or []
        if tag_vals:
            parts.append(" ".join(str(t) for t in tag_vals))
        text = " ".join(parts)

        bridges = extract_bridges_fast(text)

        if not bridges:
            failed += 1
            if i < 5:
                logger.warning(f"No bridges for _key={doc['_key']}: {text[:100]}")
            continue

        bridge_counter.update(bridges)
        merged_tags = list(set(tag_vals + bridges))

        if not dry_run:
            _update_taxonomy(db, doc["_key"], bridges, merged_tags)

        enriched += 1

        if (i + 1) % 500 == 0:
            elapsed = time.monotonic() - start
            rate = (i + 1) / elapsed
            logger.info(f"Progress: {i+1}/{len(docs)} ({rate:.1f} docs/sec)")

    elapsed = time.monotonic() - start
    logger.info(f"Done in {elapsed:.1f}s: enriched={enriched}, no_bridges={failed}")
    logger.info(f"Bridge distribution: {dict(bridge_counter)}")

    if dry_run:
        logger.info("DRY RUN — no changes written to ArangoDB")

    # Verification query
    if not dry_run and enriched > 0:
        verify = list(db.aql.execute(
            """FOR d IN lessons
                 FILTER d.scope == @scope
                 FILTER d.bridge_attributes != null AND LENGTH(d.bridge_attributes) > 0
                 COLLECT WITH COUNT INTO c RETURN c""",
            bind_vars={"scope": scope},
        ))
        total = list(db.aql.execute(
            "FOR d IN lessons FILTER d.scope == @scope COLLECT WITH COUNT INTO c RETURN c",
            bind_vars={"scope": scope},
        ))
        with_tax = verify[0] if verify else 0
        total_count = total[0] if total else 0
        pct = (with_tax / total_count * 100) if total_count else 0
        logger.info(f"Verification: {with_tax}/{total_count} ({pct:.1f}%) now have taxonomy")


if __name__ == "__main__":
    app()
