"""Tier 1: Memory & Data Health probes (auto-fix safe).

P01 embedding-coverage   — Check embedding gaps per scope
P02 taxonomy-coverage    — Check bridge_attributes coverage per scope
P03 source-qra-coverage  — Check QRA counts per source_title tag
P04 taxonomy-drift       — Detect new terms not in COLLECTION_VOCABULARIES
P10 backup-freshness     — Check ArangoDB backup recency
P11 edge-staleness       — Check lesson_edges last update
P12 duplicate-detection  — Check for duplicate lessons
P25 orphaned-lessons     — Lessons with embeddings but zero graph edges
P26 heuristic-taxonomy   — Lessons with heuristic-only taxonomy (no LLM enrichment)
P27 taxonomy-evolution   — Track tag usage trends, find new/deprecated tag candidates
P28 universal-embedding-coverage — Check embedding coverage across ALL collections

Inputs: ArangoDB via db.get_db(), filesystem for backups.
Outputs: ProbeResult per probe.
"""
from __future__ import annotations
import os

import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

import config
from probes import ProbeResult, ProbeStatus, register_probe
from probes.tier1_autofix import (
    autofix_backup,
    autofix_duplicates,
    autofix_edges,
    autofix_embeddings,
    autofix_heuristic_taxonomy,
    autofix_orphaned_lessons,
    autofix_taxonomy_batch,
    autofix_universal_embedding,
    check_embedding_service,
    log_autofix,
)


def _get_db():
    """Lazy import to avoid crashing if ArangoDB is unreachable at import time."""
    from db import get_db
    return get_db()


# ── P01: embedding-coverage ──────────────────────────────────────────────────


@register_probe("P01", "embedding-coverage", tier=1, auto_fixable=True)
def probe_embedding_coverage(autofix: bool = False) -> ProbeResult:
    """Check embedding gaps across scopes in lessons collection."""
    try:
        db = _get_db()
    except Exception as e:
        return ProbeResult(
            probe_id="P01", name="embedding-coverage", tier=1,
            status=ProbeStatus.SKIP, message=f"ArangoDB unreachable: {e}",
            details={"error": str(e)},
        )

    aql = """
    LET embedded_ids = (
        FOR emb IN lesson_embeddings
            RETURN DISTINCT emb.lesson_id
    )
    FOR l IN lessons
      COLLECT scope = l.scope,
              has_emb = (CONCAT("lessons/", l._key) IN embedded_ids)
      WITH COUNT INTO cnt
      RETURN {scope, has_embedding: has_emb, count: cnt}
    """
    try:
        # TODO: Silo violation — should use /memory instead of raw AQL.
        # Added max_runtime to prevent timeout on large collections.
        rows = list(db.aql.execute(aql, max_runtime=30))
    except Exception as e:
        return ProbeResult(
            probe_id="P01", name="embedding-coverage", tier=1,
            status=ProbeStatus.FAIL, message=f"AQL query failed: {e}",
            details={"error": str(e)}, auto_fixable=True,
        )

    scope_stats = {}
    for row in rows:
        scope = row.get("scope", "unknown")
        if scope not in scope_stats:
            scope_stats[scope] = {"embedded": 0, "missing": 0}
        if row.get("has_embedding"):
            scope_stats[scope]["embedded"] = row["count"]
        else:
            scope_stats[scope]["missing"] = row["count"]

    total_embedded = sum(s["embedded"] for s in scope_stats.values())
    total_missing = sum(s["missing"] for s in scope_stats.values())
    total = total_embedded + total_missing
    pct = (total_embedded / total * 100) if total > 0 else 100.0

    fix_applied = False
    if pct < config.EMBEDDING_WARN_PCT and autofix:
        fix_applied = autofix_embeddings()

    status = ProbeStatus.PASS if pct >= config.EMBEDDING_WARN_PCT else ProbeStatus.WARN
    if fix_applied:
        status = ProbeStatus.FIXED

    return ProbeResult(
        probe_id="P01", name="embedding-coverage", tier=1,
        status=status,
        message=f"{pct:.1f}% embedded ({total_embedded}/{total}), {total_missing} missing",
        details={"scope_stats": scope_stats, "pct": pct},
        auto_fixable=True, fix_applied=fix_applied,
    )


# ── P02: taxonomy-coverage ───────────────────────────────────────────────────


@register_probe("P02", "taxonomy-coverage", tier=1, auto_fixable=True)
def probe_taxonomy_coverage(autofix: bool = False) -> ProbeResult:
    """Check bridge_attributes coverage in lessons."""
    try:
        db = _get_db()
    except Exception as e:
        return ProbeResult(
            probe_id="P02", name="taxonomy-coverage", tier=1,
            status=ProbeStatus.SKIP, message=f"ArangoDB unreachable: {e}",
            details={"error": str(e)},
        )

    aql = """
    FOR l IN lessons
      COLLECT scope = l.scope,
              has_tax = (l.bridge_attributes != null AND LENGTH(l.bridge_attributes) > 0)
      WITH COUNT INTO cnt
      RETURN {scope, has_taxonomy: has_tax, count: cnt}
    """
    try:
        rows = list(db.aql.execute(aql))
    except Exception as e:
        return ProbeResult(
            probe_id="P02", name="taxonomy-coverage", tier=1,
            status=ProbeStatus.FAIL, message=f"AQL query failed: {e}",
            details={"error": str(e)}, auto_fixable=True,
        )

    scope_stats = {}
    for row in rows:
        scope = row.get("scope", "unknown")
        if scope not in scope_stats:
            scope_stats[scope] = {"tagged": 0, "untagged": 0}
        if row.get("has_taxonomy"):
            scope_stats[scope]["tagged"] = row["count"]
        else:
            scope_stats[scope]["untagged"] = row["count"]

    total_tagged = sum(s["tagged"] for s in scope_stats.values())
    total_untagged = sum(s["untagged"] for s in scope_stats.values())
    total = total_tagged + total_untagged
    pct = (total_tagged / total * 100) if total > 0 else 100.0

    fix_applied = False
    if pct < config.TAXONOMY_WARN_PCT and autofix:
        fix_applied = autofix_taxonomy_batch(db)

    status = ProbeStatus.PASS if pct >= config.TAXONOMY_WARN_PCT else ProbeStatus.WARN
    if fix_applied:
        status = ProbeStatus.FIXED

    return ProbeResult(
        probe_id="P02", name="taxonomy-coverage", tier=1,
        status=status,
        message=f"{pct:.1f}% tagged ({total_tagged}/{total}), {total_untagged} missing",
        details={"scope_stats": scope_stats, "pct": pct},
        auto_fixable=True, fix_applied=fix_applied,
    )


# ── P03: source-qra-coverage ────────────────────────────────────────────────


@register_probe("P03", "source-qra-coverage", tier=1, auto_fixable=False)
def probe_source_qra_coverage(autofix: bool = False) -> ProbeResult:
    """Check QRA counts per distinct source_title tag."""
    try:
        db = _get_db()
    except Exception as e:
        return ProbeResult(
            probe_id="P03", name="source-qra-coverage", tier=1,
            status=ProbeStatus.SKIP, message=f"ArangoDB unreachable: {e}",
            details={"error": str(e)},
        )

    aql = """
    FOR l IN lessons
      FILTER l.tags != null
      FOR t IN l.tags
        FILTER STARTS_WITH(t, "source_title:")
        COLLECT source = t WITH COUNT INTO cnt
        SORT cnt ASC
        RETURN {source, count: cnt}
    """
    try:
        rows = list(db.aql.execute(aql))
    except Exception as e:
        return ProbeResult(
            probe_id="P03", name="source-qra-coverage", tier=1,
            status=ProbeStatus.FAIL, message=f"AQL query failed: {e}",
            details={"error": str(e)},
        )

    low_coverage = [r for r in rows if r["count"] < 5]
    total_sources = len(rows)

    status = ProbeStatus.PASS
    if low_coverage:
        status = ProbeStatus.WARN

    return ProbeResult(
        probe_id="P03", name="source-qra-coverage", tier=1,
        status=status,
        message=f"{total_sources} sources tracked, {len(low_coverage)} with <5 QRAs",
        details={"total_sources": total_sources, "low_coverage": low_coverage[:10]},
    )


# ── P04: taxonomy-drift ─────────────────────────────────────────────────────


@register_probe("P04", "taxonomy-drift", tier=1, auto_fixable=False)
def probe_taxonomy_drift(autofix: bool = False) -> ProbeResult:
    """Sample recent lessons and detect taxonomy drift."""
    try:
        db = _get_db()
    except Exception as e:
        return ProbeResult(
            probe_id="P04", name="taxonomy-drift", tier=1,
            status=ProbeStatus.SKIP, message=f"ArangoDB unreachable: {e}",
            details={"error": str(e)},
        )

    aql = """
    FOR l IN lessons
      FILTER l.bridge_attributes != null AND LENGTH(l.bridge_attributes) > 0
      SORT l.created_at DESC
      LIMIT 100
      RETURN l.bridge_attributes
    """
    try:
        rows = list(db.aql.execute(aql))
    except Exception as e:
        return ProbeResult(
            probe_id="P04", name="taxonomy-drift", tier=1,
            status=ProbeStatus.FAIL, message=f"AQL query failed: {e}",
            details={"error": str(e)},
        )

    known_terms: set[str] = set()
    taxonomy_py = config.PROJECT_ROOT / ".pi/skills/taxonomy/taxonomy.py"
    if taxonomy_py.exists():
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("taxonomy", taxonomy_py)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            vocabs = getattr(mod, "COLLECTION_VOCABULARIES", {})
            for collection_terms in vocabs.values():
                for category_terms in collection_terms.values():
                    if isinstance(category_terms, set):
                        known_terms.update(category_terms)
            bridge_tags = getattr(mod, "BRIDGE_TAGS", set())
            known_terms.update(bridge_tags)
        except Exception as e:
            logger.warning("Could not load taxonomy vocabularies: {}", e)

    if not known_terms:
        return ProbeResult(
            probe_id="P04", name="taxonomy-drift", tier=1,
            status=ProbeStatus.SKIP,
            message="No taxonomy vocabularies loaded for drift comparison",
            details={},
        )

    term_counts: dict[str, int] = {}
    for attrs in rows:
        if isinstance(attrs, dict):
            for val in attrs.values():
                if isinstance(val, str) and val not in known_terms:
                    term_counts[val] = term_counts.get(val, 0) + 1
                elif isinstance(val, list):
                    for v in val:
                        if isinstance(v, str) and v not in known_terms:
                            term_counts[v] = term_counts.get(v, 0) + 1

    drifted = {k: v for k, v in term_counts.items() if v >= 3}
    status = ProbeStatus.PASS if not drifted else ProbeStatus.WARN

    return ProbeResult(
        probe_id="P04", name="taxonomy-drift", tier=1,
        status=status,
        message=f"{len(drifted)} drifted terms (appear 3+ times, not in vocabulary)",
        details={"drifted_terms": dict(sorted(drifted.items(), key=lambda x: -x[1])[:20])},
    )


# ── P10: backup-freshness ───────────────────────────────────────────────────


@register_probe("P10", "backup-freshness", tier=1, auto_fixable=True)
def probe_backup_freshness(autofix: bool = False) -> ProbeResult:
    """Check recency of ArangoDB backups."""
    backup_dir = config.BACKUP_DIR
    if not backup_dir.exists():
        if autofix:
            fix_applied = autofix_backup()
            status = ProbeStatus.FIXED if fix_applied else ProbeStatus.FAIL
            return ProbeResult(
                probe_id="P10", name="backup-freshness", tier=1,
                status=status,
                message="Backup dir missing" + (" (dump triggered)" if fix_applied else ""),
                details={"backup_dir": str(backup_dir)},
                auto_fixable=True, fix_applied=fix_applied,
            )
        return ProbeResult(
            probe_id="P10", name="backup-freshness", tier=1,
            status=ProbeStatus.FAIL,
            message=f"Backup directory not found: {backup_dir}",
            details={"backup_dir": str(backup_dir)},
            auto_fixable=True,
        )

    subdirs = [d for d in backup_dir.iterdir() if d.is_dir()]
    if not subdirs:
        return ProbeResult(
            probe_id="P10", name="backup-freshness", tier=1,
            status=ProbeStatus.FAIL,
            message="No backups found in backup directory",
            details={"backup_dir": str(backup_dir)},
            auto_fixable=True,
        )

    newest = max(subdirs, key=lambda d: d.stat().st_mtime)
    age_hours = (time.time() - newest.stat().st_mtime) / 3600

    fix_applied = False
    if age_hours > config.BACKUP_MAX_AGE_HOURS and autofix:
        fix_applied = autofix_backup()

    status = ProbeStatus.PASS if age_hours <= config.BACKUP_MAX_AGE_HOURS else ProbeStatus.WARN
    if fix_applied:
        status = ProbeStatus.FIXED

    return ProbeResult(
        probe_id="P10", name="backup-freshness", tier=1,
        status=status,
        message=f"Latest backup {age_hours:.1f}h old ({newest.name})",
        details={"age_hours": round(age_hours, 1), "newest": newest.name},
        auto_fixable=True, fix_applied=fix_applied,
    )


# ── P11: edge-staleness ──────────────────────────────────────────────────────


@register_probe("P11", "edge-staleness", tier=1, auto_fixable=True)
def probe_edge_staleness(autofix: bool = False) -> ProbeResult:
    """Check when lesson_edges were last updated."""
    try:
        db = _get_db()
    except Exception as e:
        return ProbeResult(
            probe_id="P11", name="edge-staleness", tier=1,
            status=ProbeStatus.SKIP, message=f"ArangoDB unreachable: {e}",
            details={"error": str(e)},
        )

    if not db.has_collection("lesson_edges"):
        return ProbeResult(
            probe_id="P11", name="edge-staleness", tier=1,
            status=ProbeStatus.SKIP,
            message="lesson_edges collection does not exist",
            details={},
        )

    aql = "RETURN MAX(FOR e IN lesson_edges RETURN e.updated_at)"
    try:
        results = list(db.aql.execute(aql))
        latest = results[0] if results else None
    except Exception as e:
        return ProbeResult(
            probe_id="P11", name="edge-staleness", tier=1,
            status=ProbeStatus.FAIL, message=f"AQL query failed: {e}",
            details={"error": str(e)}, auto_fixable=True,
        )

    if not latest:
        return ProbeResult(
            probe_id="P11", name="edge-staleness", tier=1,
            status=ProbeStatus.WARN,
            message="No edges found or no updated_at timestamps",
            details={}, auto_fixable=True,
        )

    try:
        dt = datetime.fromisoformat(latest.replace("Z", "+00:00"))
        age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except (ValueError, AttributeError):
        age_hours = float("inf")

    fix_applied = False
    if age_hours > config.EDGE_MAX_AGE_HOURS and autofix:
        fix_applied = autofix_edges()

    status = ProbeStatus.PASS if age_hours <= config.EDGE_MAX_AGE_HOURS else ProbeStatus.WARN
    if fix_applied:
        status = ProbeStatus.FIXED

    return ProbeResult(
        probe_id="P11", name="edge-staleness", tier=1,
        status=status,
        message=f"Latest edge update {age_hours:.1f}h ago",
        details={"age_hours": round(age_hours, 1), "latest": latest},
        auto_fixable=True, fix_applied=fix_applied,
    )


# ── P12: duplicate-detection ─────────────────────────────────────────────────


@register_probe("P12", "duplicate-detection", tier=1, auto_fixable=True)
def probe_duplicate_detection(autofix: bool = False) -> ProbeResult:
    """Check for duplicate lessons via ops-arango."""
    ops_arango = config.PROJECT_ROOT / ".pi/skills/ops-arango/run.sh"
    if not ops_arango.exists():
        return ProbeResult(
            probe_id="P12", name="duplicate-detection", tier=1,
            status=ProbeStatus.SKIP,
            message="ops-arango skill not found",
            details={},
        )

    try:
        result = subprocess.run(
            [str(ops_arango), "duplicates", "--json"],
            capture_output=True, text=True, timeout=60,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return ProbeResult(
            probe_id="P12", name="duplicate-detection", tier=1,
            status=ProbeStatus.FAIL, message=f"Duplicates check failed: {e}",
            details={"error": str(e)}, auto_fixable=True,
        )

    import json
    try:
        data = json.loads(result.stdout) if result.stdout.strip() else {}
    except json.JSONDecodeError:
        data = {}

    dup_count = data.get("duplicate_count", 0) if isinstance(data, dict) else 0

    fix_applied = False
    if dup_count > 0 and autofix:
        fix_applied = autofix_duplicates(ops_arango)

    if dup_count == 0:
        status = ProbeStatus.PASS
    elif fix_applied:
        status = ProbeStatus.FIXED
    else:
        status = ProbeStatus.WARN

    return ProbeResult(
        probe_id="P12", name="duplicate-detection", tier=1,
        status=status,
        message=f"{dup_count} duplicate(s) detected",
        details={"duplicate_count": dup_count},
        auto_fixable=True, fix_applied=fix_applied,
    )


# ── P25: orphaned-lessons (embeddings but no edges) ────────────────────────


@register_probe("P25", "orphaned-lessons", tier=1, auto_fixable=True)
def probe_orphaned_lessons(autofix: bool = False) -> ProbeResult:
    """Find lessons that have embeddings but zero graph edges."""
    try:
        db = _get_db()
    except Exception as e:
        return ProbeResult(
            probe_id="P25", name="orphaned-lessons", tier=1,
            status=ProbeStatus.SKIP, message=f"ArangoDB unreachable: {e}",
            details={"error": str(e)},
        )

    if not db.has_collection("lesson_edges") or not db.has_collection("lesson_embeddings"):
        return ProbeResult(
            probe_id="P25", name="orphaned-lessons", tier=1,
            status=ProbeStatus.SKIP,
            message="Required collections (lesson_edges, lesson_embeddings) missing",
            details={},
        )

    aql = """
    LET embedded_ids = (
        FOR emb IN lesson_embeddings
            RETURN DISTINCT emb.lesson_id
    )
    LET has_edge = (
        FOR e IN lesson_edges
            RETURN UNION_DISTINCT(
                [e._from],
                [e._to]
            )
    )
    LET edge_set = UNION_DISTINCT(FLATTEN(has_edge))
    FOR lid IN embedded_ids
        FILTER lid NOT IN edge_set
        RETURN lid
    """
    try:
        orphaned = list(db.aql.execute(aql))
    except Exception as e:
        return ProbeResult(
            probe_id="P25", name="orphaned-lessons", tier=1,
            status=ProbeStatus.FAIL, message=f"AQL query failed: {e}",
            details={"error": str(e)}, auto_fixable=True,
        )

    total_embedded = list(db.aql.execute(
        "RETURN LENGTH(FOR emb IN lesson_embeddings RETURN 1)"
    ))[0]
    orphan_count = len(orphaned)
    pct_orphaned = (orphan_count / total_embedded * 100) if total_embedded > 0 else 0.0

    fix_applied = False
    if orphan_count > 0 and autofix:
        fix_applied = autofix_orphaned_lessons(db, orphaned)

    if orphan_count == 0:
        status = ProbeStatus.PASS
    elif fix_applied:
        status = ProbeStatus.FIXED
    elif pct_orphaned > 10.0:
        status = ProbeStatus.FAIL
    else:
        status = ProbeStatus.WARN

    return ProbeResult(
        probe_id="P25", name="orphaned-lessons", tier=1,
        status=status,
        message=f"{orphan_count}/{total_embedded} lessons have embeddings but no edges ({pct_orphaned:.1f}%)",
        details={
            "orphan_count": orphan_count,
            "total_embedded": total_embedded,
            "pct_orphaned": round(pct_orphaned, 1),
            "sample_orphans": orphaned[:10],
        },
        auto_fixable=True, fix_applied=fix_applied,
    )


# ── P26: heuristic-taxonomy (no LLM enrichment) ───────────────────────────


@register_probe("P26", "heuristic-taxonomy", tier=1, auto_fixable=True)
def probe_heuristic_taxonomy(autofix: bool = False) -> ProbeResult:
    """Find lessons with heuristic-only taxonomy (method: 'none' or missing)."""
    try:
        db = _get_db()
    except Exception as e:
        return ProbeResult(
            probe_id="P26", name="heuristic-taxonomy", tier=1,
            status=ProbeStatus.SKIP, message=f"ArangoDB unreachable: {e}",
            details={"error": str(e)},
        )

    aql = """
    LET total = LENGTH(FOR l IN lessons RETURN 1)
    LET heuristic_only = LENGTH(
        FOR l IN lessons
            FILTER l.taxonomy == null
                OR l.taxonomy.method == null
                OR l.taxonomy.method == "none"
                OR l.taxonomy.method == "heuristic"
            RETURN 1
    )
    LET llm_enriched = total - heuristic_only
    RETURN {total, heuristic_only, llm_enriched}
    """
    try:
        result = list(db.aql.execute(aql))[0]
    except Exception as e:
        return ProbeResult(
            probe_id="P26", name="heuristic-taxonomy", tier=1,
            status=ProbeStatus.FAIL, message=f"AQL query failed: {e}",
            details={"error": str(e)}, auto_fixable=True,
        )

    total = result["total"]
    heuristic_only = result["heuristic_only"]
    llm_enriched = result["llm_enriched"]
    pct_heuristic = (heuristic_only / total * 100) if total > 0 else 0.0

    fix_applied = False
    if heuristic_only > 0 and autofix:
        fix_applied = autofix_heuristic_taxonomy(db, limit=config.TAXONOMY_FIX_BATCH)

    if pct_heuristic <= 20.0:
        status = ProbeStatus.PASS
    elif fix_applied:
        status = ProbeStatus.FIXED
    elif pct_heuristic > 50.0:
        status = ProbeStatus.FAIL
    else:
        status = ProbeStatus.WARN

    return ProbeResult(
        probe_id="P26", name="heuristic-taxonomy", tier=1,
        status=status,
        message=f"{heuristic_only}/{total} lessons have heuristic-only taxonomy ({pct_heuristic:.1f}%)",
        details={
            "total": total,
            "heuristic_only": heuristic_only,
            "llm_enriched": llm_enriched,
            "pct_heuristic": round(pct_heuristic, 1),
        },
        auto_fixable=True, fix_applied=fix_applied,
    )


# ── P28: universal-embedding-coverage ────────────────────────────────────────


@register_probe("P28", "universal-embedding-coverage", tier=1, auto_fixable=True)
def probe_universal_embedding_coverage(autofix: bool = False) -> ProbeResult:
    """Check embedding coverage across ALL embeddable collections."""
    try:
        db = _get_db()
    except Exception as e:
        return ProbeResult(
            probe_id="P28", name="universal-embedding-coverage", tier=1,
            status=ProbeStatus.SKIP, message=f"ArangoDB unreachable: {e}",
            details={"error": str(e)},
        )

    collection_stats = {}
    worst_collection = None
    worst_gap = 0
    total_missing = 0

    for coll_name, (text_fields, embed_coll) in config.EMBEDDABLE_COLLECTIONS.items():
        if not db.has_collection(coll_name):
            continue

        try:
            total = list(db.aql.execute(
                f"RETURN LENGTH(FOR d IN {coll_name} RETURN 1)"
            ))[0]
        except Exception:
            continue

        if total == 0:
            collection_stats[coll_name] = {"total": 0, "embedded": 0, "pct": 100.0}
            continue

        try:
            if embed_coll and db.has_collection(embed_coll):
                if coll_name == "lessons":
                    id_field = "lesson_id"
                else:
                    id_field = "source_id"
                embedded = list(db.aql.execute(
                    f"RETURN LENGTH(FOR e IN {embed_coll} COLLECT id = e.{id_field} RETURN 1)"
                ))[0]
            elif not text_fields:
                collection_stats[coll_name] = {"total": total, "embedded": total, "pct": 100.0}
                continue
            else:
                embedded = list(db.aql.execute(
                    f"RETURN LENGTH(FOR d IN {coll_name} FILTER d.embedding != null AND LENGTH(d.embedding) > 0 RETURN 1)"
                ))[0]
        except Exception:
            embedded = 0

        pct = (embedded / total * 100) if total > 0 else 100.0
        gap = total - embedded
        collection_stats[coll_name] = {"total": total, "embedded": embedded, "pct": round(pct, 1)}
        total_missing += gap
        if gap > worst_gap:
            worst_gap = gap
            worst_collection = coll_name

    fix_applied = False
    if worst_collection and autofix and worst_gap > 0:
        fix_applied = autofix_universal_embedding(db, worst_collection)

    all_good = all(s["pct"] >= 95.0 for s in collection_stats.values())
    any_bad = any(s["pct"] < 50.0 for s in collection_stats.values())

    if all_good:
        status = ProbeStatus.PASS
    elif fix_applied:
        status = ProbeStatus.FIXED
    elif any_bad:
        status = ProbeStatus.FAIL
    else:
        status = ProbeStatus.WARN

    msg_parts = []
    for name, stats in sorted(collection_stats.items(), key=lambda x: x[1]["pct"]):
        if stats["pct"] < 99.0:
            msg_parts.append(f"{name}={stats['pct']:.0f}%")
    summary = ", ".join(msg_parts[:5]) if msg_parts else "all collections ≥99%"

    return ProbeResult(
        probe_id="P28", name="universal-embedding-coverage", tier=1,
        status=status,
        message=f"{len(collection_stats)} collections checked, {total_missing} total missing. {summary}",
        details={"collections": collection_stats, "worst": worst_collection},
        auto_fixable=True, fix_applied=fix_applied,
    )


# P27 taxonomy-evolution is in tier1_taxonomy_evolution.py
