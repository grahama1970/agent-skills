"""Code-projection health probes for monitor-memory.

These probes are read-only health checks over the code projection produced by
ingest-code and Memory/GMO. They classify generation, Arango, semantic outbox,
Qdrant metadata, source freshness, derived summary, debugger recipe, and
delta-efficiency disagreement without activating projections or mutating data.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config
from probes import ProbeResult, ProbeStatus, register_probe

TIER = 8
REMEDIATIONS = {
    "observe": "observe",
    "retry_outbox": "retry_outbox",
    "reapply_projection": "reapply_projection",
    "reindex": "reindex",
    "human_review": "human_review",
}

_CORE_COLLECTIONS = ("code_indexes", "code_generations", "code_files", "code_symbols", "curate_edges")


def _get_db() -> Any:
    from db import get_db

    return get_db()


def _aql(db: Any, query: str, bind_vars: dict[str, Any] | None = None) -> list[Any]:
    return list(db.aql.execute(query, bind_vars=bind_vars or {}))


def _has_collection(db: Any, name: str) -> bool:
    try:
        return bool(db.has_collection(name))
    except Exception:
        return False


def _missing_collections(db: Any, names: tuple[str, ...] = _CORE_COLLECTIONS) -> list[str]:
    return [name for name in names if not _has_collection(db, name)]


def _skip_missing(probe_id: str, name: str, missing: list[str]) -> ProbeResult:
    return ProbeResult(
        probe_id=probe_id,
        name=name,
        tier=TIER,
        status=ProbeStatus.SKIP,
        message=f"Code projection collections missing: {', '.join(missing)}",
        details={
            "missing_collections": missing,
            "limitations": ["code projection has not been provisioned in this database"],
            "remediation": REMEDIATIONS["observe"],
        },
    )


def _db_or_skip(probe_id: str, name: str, collections: tuple[str, ...] = _CORE_COLLECTIONS) -> tuple[Any | None, ProbeResult | None]:
    try:
        db = _get_db()
    except Exception as exc:
        return None, ProbeResult(
            probe_id=probe_id,
            name=name,
            tier=TIER,
            status=ProbeStatus.SKIP,
            message=f"ArangoDB unreachable: {exc}",
            details={"error": str(exc), "remediation": REMEDIATIONS["observe"]},
        )
    missing = _missing_collections(db, collections)
    if missing:
        return None, _skip_missing(probe_id, name, missing)
    return db, None


def _count_issues(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    issues = []
    for row in rows:
        row_issues = [key for key in keys if row.get(key)]
        if row_issues:
            issue = {
                "scope": row.get("scope"),
                "code_index_id": row.get("code_index_id"),
                "branch": row.get("branch"),
                "generation_id": row.get("generation_id") or row.get("active_generation_id"),
                "issues": row_issues,
            }
            for key in keys:
                if row.get(key) is not None:
                    issue[key] = row.get(key)
            issues.append(issue)
    return issues


def _active_generation_rows(db: Any) -> list[dict[str, Any]]:
    return _aql(
        db,
        """
        /* monitor-memory: code-projection-active-generation */
        FOR idx IN code_indexes
          LET generations = (
            FOR g IN code_generations
              FILTER g.code_index_id == idx._key
              FILTER g.scope == idx.scope
              FILTER g.branch == idx.branch
              RETURN KEEP(g, "generation_id", "status", "accepted_bundle_digest", "expected_counts", "transform_fingerprint", "config_fingerprint")
          )
          LET active_generations = (
            FOR g IN generations
              FILTER g.status == "active"
              RETURN g
          )
          LET pointer_generation = FIRST(
            FOR g IN generations
              FILTER g.generation_id == idx.active_generation_id
              RETURN g
          )
          LET current_record_generations = UNIQUE(APPEND(
            (FOR d IN code_files FILTER d.scope == idx.scope AND d.code_index_id == idx._key AND d.active_for_retrieval != false RETURN d.generation_id),
            APPEND(
              (FOR d IN code_symbols FILTER d.scope == idx.scope AND d.code_index_id == idx._key AND d.active_for_retrieval != false RETURN d.generation_id),
              (FOR d IN curate_edges FILTER d.scope == idx.scope AND d.code_index_id == idx._key AND d.active_for_traversal == true RETURN d.generation_id)
            )
          ))
          LET stale_staging_count = LENGTH(
            FOR g IN generations
              FILTER g.status == "staging"
              RETURN 1
          )
          RETURN {
            scope: idx.scope,
            code_index_id: idx._key,
            branch: idx.branch,
            active_generation_id: idx.active_generation_id,
            pointer_status: pointer_generation.status,
            active_generation_count: LENGTH(active_generations),
            current_record_generation_ids: current_record_generations,
            mixed_current_records: LENGTH(current_record_generations) > 1,
            missing_active_pointer: idx.active_generation_id == null OR pointer_generation == null,
            stale_staging_count
          }
        """,
    )


def _bundle_rows(db: Any) -> list[dict[str, Any]]:
    return _aql(
        db,
        """
        /* monitor-memory: code-projection-bundle-reconciliation */
        FOR idx IN code_indexes
          LET g = FIRST(
            FOR gen IN code_generations
              FILTER gen.code_index_id == idx._key
              FILTER gen.generation_id == idx.active_generation_id
              RETURN gen
          )
          FILTER g != null
          LET observed_counts = {
            files: LENGTH(FOR d IN code_files FILTER d.scope == idx.scope AND d.code_index_id == idx._key AND d.generation_id == g.generation_id RETURN 1),
            symbols: LENGTH(FOR d IN code_symbols FILTER d.scope == idx.scope AND d.code_index_id == idx._key AND d.generation_id == g.generation_id RETURN 1),
            edges: LENGTH(FOR d IN curate_edges FILTER d.scope == idx.scope AND d.code_index_id == idx._key AND d.generation_id == g.generation_id AND d.active_for_traversal == true RETURN 1)
          }
          LET expected_counts = g.expected_counts || {}
          RETURN {
            scope: idx.scope,
            code_index_id: idx._key,
            branch: idx.branch,
            generation_id: g.generation_id,
            accepted_bundle_digest: g.accepted_bundle_digest,
            expected_counts,
            observed_counts,
            count_mismatch: expected_counts.files != observed_counts.files OR expected_counts.symbols != observed_counts.symbols OR expected_counts.edges != observed_counts.edges,
            missing_bundle_digest: g.accepted_bundle_digest == null OR g.accepted_bundle_digest == ""
          }
        """,
    )


def _incomplete_rows(db: Any) -> list[dict[str, Any]]:
    return _aql(
        db,
        """
        /* monitor-memory: code-projection-incomplete-immutability */
        FOR g IN code_generations
          FILTER g.status IN ["rejected", "incomplete", "failed"]
          SORT g.created_at DESC
          LIMIT 50
          RETURN {
            scope: g.scope,
            code_index_id: g.code_index_id,
            branch: g.branch,
            generation_id: g.generation_id,
            status: g.status,
            active_before_generation_id: g.active_before_generation_id,
            active_after_generation_id: g.active_after_generation_id,
            active_generation_mutated: g.active_before_generation_id != null AND g.active_after_generation_id != null AND g.active_before_generation_id != g.active_after_generation_id,
            current_keyset_mutated: g.current_keyset_mutated == true
          }
        """,
    )


def _semantic_parity_rows(db: Any) -> list[dict[str, Any]]:
    return _aql(
        db,
        """
        /* monitor-memory: code-projection-semantic-parity */
        FOR idx IN code_indexes
          LET active_symbols = (
            FOR d IN code_symbols
              FILTER d.scope == idx.scope
              FILTER d.code_index_id == idx._key
              FILTER d.generation_id == idx.active_generation_id
              FILTER d.active_for_retrieval != false
              RETURN d
          )
          LET missing_points = (
            FOR d IN active_symbols
              FILTER d.qdrant_point_id == null OR d.qdrant_point_id == "" OR d.semantic_sync_state != "synced"
              RETURN KEEP(d, "_key", "symbol_id", "generation_id", "qdrant_point_id", "semantic_sync_state")
          )
          LET stale_text = (
            FOR d IN active_symbols
              FILTER d.retrieval_text_sha256 != null
              FILTER d.text_hash != null
              FILTER d.retrieval_text_sha256 != d.text_hash
              RETURN KEEP(d, "_key", "symbol_id", "generation_id", "retrieval_text_sha256", "text_hash")
          )
          LET retired_with_points = (
            FOR d IN code_symbols
              FILTER d.scope == idx.scope
              FILTER d.code_index_id == idx._key
              FILTER d.generation_id != idx.active_generation_id
              FILTER d.active_for_retrieval == false
              FILTER d.qdrant_point_id != null AND d.qdrant_point_id != ""
              FILTER d.semantic_sync_state == "synced"
              RETURN KEEP(d, "_key", "symbol_id", "generation_id", "qdrant_point_id")
          )
          RETURN {
            scope: idx.scope,
            code_index_id: idx._key,
            branch: idx.branch,
            generation_id: idx.active_generation_id,
            active_symbol_count: LENGTH(active_symbols),
            missing_point_count: LENGTH(missing_points),
            stale_text_count: LENGTH(stale_text),
            retired_point_count: LENGTH(retired_with_points),
            missing_point_sample: SLICE(missing_points, 0, 10),
            stale_text_sample: SLICE(stale_text, 0, 10),
            retired_point_sample: SLICE(retired_with_points, 0, 10)
          }
        """,
    )


def _outbox_rows(db: Any) -> list[dict[str, Any]]:
    return _aql(
        db,
        """
        /* monitor-memory: code-projection-outbox-backlog */
        FOR d IN semantic_projection_outbox
          FILTER d.arango_collection == "code_symbols" OR d.collection == "code_symbols" OR d.target_collection == "code_symbols"
          COLLECT scope = d.scope, code_index_id = d.code_index_id, state = d.state INTO grouped = d
          LET oldest = MIN(grouped[*].created_at)
          LET last_error = FIRST(
            FOR item IN grouped
              FILTER item.last_error != null AND item.last_error != ""
              SORT item.updated_at DESC
              LIMIT 1
              RETURN item.last_error
          )
          RETURN {scope, code_index_id, state, count: LENGTH(grouped), oldest, last_error}
        """,
    )


def _retired_leakage_rows(db: Any) -> list[dict[str, Any]]:
    if not _has_collection(db, "code_recall_canaries"):
        return []
    return _aql(
        db,
        """
        /* monitor-memory: code-projection-retired-recall-leakage */
        FOR d IN code_recall_canaries
          FILTER d.kind == "retired_symbol_leakage"
          RETURN KEEP(d, "scope", "code_index_id", "generation_id", "symbol_id", "route", "leaked", "history_available", "receipt_ref")
        """,
    )


def _source_rows(db: Any, limit: int) -> list[dict[str, Any]]:
    return _aql(
        db,
        """
        /* monitor-memory: code-projection-source-freshness */
        FOR idx IN code_indexes
          FOR d IN code_symbols
            FILTER d.scope == idx.scope
            FILTER d.code_index_id == idx._key
            FILTER d.generation_id == idx.active_generation_id
            FILTER d.active_for_retrieval != false
            SORT d._key
            LIMIT @limit
            RETURN KEEP(d, "_key", "scope", "code_index_id", "generation_id", "repo", "root", "path", "symbol_id", "content_hash", "source_hash")
        """,
        {"limit": limit},
    )


def _drift_rows(db: Any) -> list[dict[str, Any]]:
    return _aql(
        db,
        """
        /* monitor-memory: code-projection-transform-drift */
        FOR idx IN code_indexes
          LET g = FIRST(
            FOR gen IN code_generations
              FILTER gen.code_index_id == idx._key
              FILTER gen.generation_id == idx.active_generation_id
              RETURN gen
          )
          FILTER g != null
          LET semantic_schemas = UNIQUE(
            FOR d IN code_symbols
              FILTER d.scope == idx.scope
              FILTER d.code_index_id == idx._key
              FILTER d.generation_id == idx.active_generation_id
              FILTER d.active_for_retrieval != false
              RETURN d.semantic_text_schema
          )
          RETURN {
            scope: idx.scope,
            code_index_id: idx._key,
            branch: idx.branch,
            generation_id: g.generation_id,
            transform_fingerprint: g.transform_fingerprint,
            config_fingerprint: g.config_fingerprint,
            semantic_text_schemas: semantic_schemas
          }
        """,
    )


def _doc_debug_rows(db: Any) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    if _has_collection(db, "code_symbols"):
        parts.extend(
            _aql(
                db,
                """
                /* monitor-memory: code-projection-derived-summary-status */
                FOR idx IN code_indexes
                  FOR d IN code_symbols
                    FILTER d.scope == idx.scope
                    FILTER d.code_index_id == idx._key
                    FILTER d.generation_id == idx.active_generation_id
                    FILTER d.active_for_retrieval != false
                    COLLECT scope = d.scope, code_index_id = d.code_index_id, status = d.derived_summary_status WITH COUNT INTO count
                    RETURN {kind: "derived_summary", scope, code_index_id, status, count}
                """,
            )
        )
    if _has_collection(db, "code_debug_recipes"):
        parts.extend(
            _aql(
                db,
                """
                /* monitor-memory: code-projection-debugger-recipe-status */
                FOR idx IN code_indexes
                  FOR d IN code_debug_recipes
                    FILTER d.scope == idx.scope
                    FILTER d.code_index_id == idx._key
                    FILTER d.generation_id == idx.active_generation_id
                    COLLECT scope = d.scope, code_index_id = d.code_index_id, status = d.status WITH COUNT INTO count
                    RETURN {kind: "debugger_recipe", scope, code_index_id, status, count}
                """,
            )
        )
    return parts


def _efficiency_rows(db: Any) -> list[dict[str, Any]]:
    if not _has_collection(db, "code_ingest_telemetry"):
        return []
    return _aql(
        db,
        """
        /* monitor-memory: code-projection-delta-efficiency */
        FOR d IN code_ingest_telemetry
          SORT d.created_at DESC
          LIMIT 25
          RETURN KEEP(d, "scope", "code_index_id", "generation_id", "run_id", "discovered_files", "parsed_files", "reused_files", "rebuilt_symbols", "rebuilt_edges", "embedding_reuse_count", "bytes_read", "duration_ms", "created_at")
        """,
    )


@register_probe("CP01", "code-projection-active-generation", tier=TIER, auto_fixable=False)
def probe_active_generation(autofix: bool = False) -> ProbeResult:
    db, skip = _db_or_skip("CP01", "code-projection-active-generation")
    if skip:
        return skip
    rows = _active_generation_rows(db)
    if not rows:
        return ProbeResult("CP01", "code-projection-active-generation", TIER, ProbeStatus.SKIP, "No code indexes found", {"remediation": REMEDIATIONS["observe"]})
    issues = _count_issues(rows, ("missing_active_pointer", "mixed_current_records", "stale_staging_count"))
    bad_active_counts = [row for row in rows if int(row.get("active_generation_count") or 0) != 1]
    if issues or bad_active_counts:
        return ProbeResult(
            "CP01",
            "code-projection-active-generation",
            TIER,
            ProbeStatus.FAIL,
            f"{len(issues) + len(bad_active_counts)} code index generation invariant issue(s)",
            {
                "rows": rows,
                "issues": issues,
                "bad_active_counts": bad_active_counts,
                "limitations": ["read-only monitor; projection activation remains owned by Memory/GMO"],
                "remediation": REMEDIATIONS["reapply_projection"],
            },
        )
    return ProbeResult("CP01", "code-projection-active-generation", TIER, ProbeStatus.PASS, f"{len(rows)} active code index pointer(s) unique", {"rows": rows, "remediation": REMEDIATIONS["observe"]})


@register_probe("CP02", "code-projection-bundle-reconciliation", tier=TIER, auto_fixable=False)
def probe_bundle_reconciliation(autofix: bool = False) -> ProbeResult:
    db, skip = _db_or_skip("CP02", "code-projection-bundle-reconciliation")
    if skip:
        return skip
    rows = _bundle_rows(db)
    if not rows:
        return ProbeResult("CP02", "code-projection-bundle-reconciliation", TIER, ProbeStatus.SKIP, "No active code generation rows found", {"remediation": REMEDIATIONS["observe"]})
    issues = _count_issues(rows, ("count_mismatch", "missing_bundle_digest"))
    status = ProbeStatus.FAIL if any("count_mismatch" in issue["issues"] for issue in issues) else (ProbeStatus.WARN if issues else ProbeStatus.PASS)
    message = "bundle/count reconciliation passed" if status == ProbeStatus.PASS else f"{len(issues)} bundle reconciliation issue(s)"
    return ProbeResult("CP02", "code-projection-bundle-reconciliation", TIER, status, message, {"rows": rows, "issues": issues, "remediation": REMEDIATIONS["reapply_projection"] if issues else REMEDIATIONS["observe"]})


@register_probe("CP03", "code-projection-incomplete-immutability", tier=TIER, auto_fixable=False)
def probe_incomplete_immutability(autofix: bool = False) -> ProbeResult:
    db, skip = _db_or_skip("CP03", "code-projection-incomplete-immutability", ("code_generations",))
    if skip:
        return skip
    rows = _incomplete_rows(db)
    if not rows:
        return ProbeResult("CP03", "code-projection-incomplete-immutability", TIER, ProbeStatus.SKIP, "No rejected/incomplete generation receipts found", {"remediation": REMEDIATIONS["observe"]})
    issues = _count_issues(rows, ("active_generation_mutated", "current_keyset_mutated"))
    status = ProbeStatus.FAIL if issues else ProbeStatus.PASS
    return ProbeResult("CP03", "code-projection-incomplete-immutability", TIER, status, "incomplete receipt immutability preserved" if not issues else f"{len(issues)} incomplete run mutation issue(s)", {"rows": rows, "issues": issues, "remediation": REMEDIATIONS["human_review"] if issues else REMEDIATIONS["observe"]})


@register_probe("CP04", "code-projection-semantic-parity", tier=TIER, auto_fixable=False)
def probe_semantic_parity(autofix: bool = False) -> ProbeResult:
    db, skip = _db_or_skip("CP04", "code-projection-semantic-parity", ("code_indexes", "code_symbols"))
    if skip:
        return skip
    rows = _semantic_parity_rows(db)
    if not rows:
        return ProbeResult("CP04", "code-projection-semantic-parity", TIER, ProbeStatus.SKIP, "No active code symbols found", {"remediation": REMEDIATIONS["observe"]})
    issues = [row for row in rows if int(row.get("missing_point_count") or 0) or int(row.get("stale_text_count") or 0) or int(row.get("retired_point_count") or 0)]
    status = ProbeStatus.FAIL if issues else ProbeStatus.PASS
    return ProbeResult("CP04", "code-projection-semantic-parity", TIER, status, "semantic parity claimable" if not issues else f"{len(issues)} code index semantic parity issue(s)", {"rows": rows, "issues": issues, "limitations": ["Qdrant point payload is inferred from Arango sync metadata unless GMO semantic diagnostics collection is present"], "remediation": REMEDIATIONS["retry_outbox"] if issues else REMEDIATIONS["observe"]})


@register_probe("CP05", "code-projection-outbox-backlog", tier=TIER, auto_fixable=True)
def probe_outbox_backlog(autofix: bool = False) -> ProbeResult:
    db, skip = _db_or_skip("CP05", "code-projection-outbox-backlog", ("semantic_projection_outbox",))
    if skip:
        return skip
    rows = _outbox_rows(db)
    pending = sum(int(row.get("count") or 0) for row in rows if row.get("state") in {"pending", "retrying", "failed"})
    failed = sum(int(row.get("count") or 0) for row in rows if row.get("state") == "failed")
    if failed or pending >= config.CODE_PROJECTION_OUTBOX_FAIL_COUNT:
        status = ProbeStatus.FAIL
    elif pending > config.CODE_PROJECTION_OUTBOX_WARN_COUNT:
        status = ProbeStatus.WARN
    else:
        status = ProbeStatus.PASS
    return ProbeResult("CP05", "code-projection-outbox-backlog", TIER, status, f"{pending} pending/retrying/failed code-symbol outbox row(s)", {"rows": rows, "pending_or_failed": pending, "failed": failed, "remediation": REMEDIATIONS["retry_outbox"] if pending else REMEDIATIONS["observe"]}, auto_fixable=True)


@register_probe("CP06", "code-projection-retired-recall-leakage", tier=TIER, auto_fixable=False)
def probe_retired_leakage(autofix: bool = False) -> ProbeResult:
    db, skip = _db_or_skip("CP06", "code-projection-retired-recall-leakage", ("code_symbols",))
    if skip:
        return skip
    rows = _retired_leakage_rows(db)
    if not rows:
        return ProbeResult("CP06", "code-projection-retired-recall-leakage", TIER, ProbeStatus.SKIP, "No retired recall canary receipts found", {"limitations": ["requires Memory/GMO recall canary receipts"], "remediation": REMEDIATIONS["observe"]})
    leaks = [row for row in rows if row.get("leaked")]
    missing_history = [row for row in rows if not row.get("history_available", True)]
    status = ProbeStatus.FAIL if leaks else (ProbeStatus.WARN if missing_history else ProbeStatus.PASS)
    return ProbeResult("CP06", "code-projection-retired-recall-leakage", TIER, status, "retired canaries absent from current recall" if not leaks else f"{len(leaks)} retired recall leakage route(s)", {"rows": rows, "leaks": leaks, "missing_history": missing_history, "remediation": REMEDIATIONS["reindex"] if leaks else REMEDIATIONS["observe"]})


@register_probe("CP07", "code-projection-source-freshness", tier=TIER, auto_fixable=False)
def probe_source_freshness(autofix: bool = False) -> ProbeResult:
    db, skip = _db_or_skip("CP07", "code-projection-source-freshness", ("code_indexes", "code_symbols"))
    if skip:
        return skip
    rows = _source_rows(db, config.CODE_PROJECTION_SOURCE_SAMPLE_LIMIT)
    if not rows:
        return ProbeResult("CP07", "code-projection-source-freshness", TIER, ProbeStatus.SKIP, "No active source rows found", {"remediation": REMEDIATIONS["observe"]})
    current = []
    stale = []
    missing = []
    for row in rows:
        root = Path(str(row.get("root") or ""))
        rel = str(row.get("path") or "")
        path = root / rel if root and rel else Path()
        if not root or not rel or not path.exists():
            missing.append(row)
            continue
        digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        expected = str(row.get("content_hash") or row.get("source_hash") or "")
        if expected and expected != digest:
            stale.append({**row, "observed_sha256": digest})
        else:
            current.append({**row, "observed_sha256": digest})
    status = ProbeStatus.WARN if stale or missing else ProbeStatus.PASS
    return ProbeResult("CP07", "code-projection-source-freshness", TIER, status, f"{len(current)} current, {len(stale)} stale, {len(missing)} missing source sample(s)", {"sampled": len(rows), "current_count": len(current), "stale": stale[:10], "missing": missing[:10], "limitations": ["sampled check; stale snippets must not be treated modification-ready"], "remediation": REMEDIATIONS["reindex"] if stale or missing else REMEDIATIONS["observe"]})


@register_probe("CP08", "code-projection-transform-drift", tier=TIER, auto_fixable=False)
def probe_transform_drift(autofix: bool = False) -> ProbeResult:
    db, skip = _db_or_skip("CP08", "code-projection-transform-drift", ("code_indexes", "code_generations", "code_symbols"))
    if skip:
        return skip
    rows = _drift_rows(db)
    drift = []
    for row in rows:
        if row.get("transform_fingerprint") != config.CODE_PROJECTION_EXPECTED_TRANSFORM_FINGERPRINT:
            drift.append({**row, "drift": "transform_fingerprint"})
            continue
        schemas = {value for value in row.get("semantic_text_schemas") or [] if value}
        if schemas and schemas != {config.CODE_PROJECTION_EXPECTED_SEMANTIC_TEXT_SCHEMA}:
            drift.append({**row, "drift": "semantic_text_schema"})
    status = ProbeStatus.WARN if drift else ProbeStatus.PASS
    return ProbeResult("CP08", "code-projection-transform-drift", TIER, status, "active generations match deployed fingerprints" if not drift else f"{len(drift)} transform/semantic fingerprint drift(s)", {"rows": rows, "drift": drift, "expected_transform_fingerprint": config.CODE_PROJECTION_EXPECTED_TRANSFORM_FINGERPRINT, "expected_semantic_text_schema": config.CODE_PROJECTION_EXPECTED_SEMANTIC_TEXT_SCHEMA, "remediation": REMEDIATIONS["reindex"] if drift else REMEDIATIONS["observe"]})


@register_probe("CP09", "code-projection-doc-debugger-staleness", tier=TIER, auto_fixable=False)
def probe_doc_debug_staleness(autofix: bool = False) -> ProbeResult:
    db, skip = _db_or_skip("CP09", "code-projection-doc-debugger-staleness", ("code_indexes", "code_symbols"))
    if skip:
        return skip
    rows = _doc_debug_rows(db)
    stale_statuses = {"stale", "rejected", "invalid", "unsafe_direct", "needs_fixture"}
    stale = [row for row in rows if str(row.get("status") or "") in stale_statuses and int(row.get("count") or 0) > 0]
    status = ProbeStatus.WARN if stale else ProbeStatus.PASS
    return ProbeResult("CP09", "code-projection-doc-debugger-staleness", TIER, status, "derived summaries and debugger recipes current enough" if not stale else f"{len(stale)} stale/rejected doc/debugger status bucket(s)", {"rows": rows, "stale": stale, "remediation": REMEDIATIONS["human_review"] if stale else REMEDIATIONS["observe"]})


@register_probe("CP10", "code-projection-delta-efficiency", tier=TIER, auto_fixable=False)
def probe_delta_efficiency(autofix: bool = False) -> ProbeResult:
    db, skip = _db_or_skip("CP10", "code-projection-delta-efficiency", ("code_indexes",))
    if skip:
        return skip
    rows = _efficiency_rows(db)
    if not rows:
        return ProbeResult("CP10", "code-projection-delta-efficiency", TIER, ProbeStatus.SKIP, "No code ingest delta-efficiency telemetry found", {"limitations": ["requires ingest-code#1347 telemetry receipts"], "remediation": REMEDIATIONS["observe"]})
    inefficient = []
    for row in rows:
        discovered = int(row.get("discovered_files") or 0)
        parsed = int(row.get("parsed_files") or 0)
        reused = int(row.get("reused_files") or 0)
        if discovered <= 0:
            continue
        reparse_pct = parsed / max(discovered, 1) * 100
        if reused == discovered:
            reparse_pct = 0.0
        if reparse_pct > config.CODE_PROJECTION_EFFICIENCY_WARN_REPARSE_PCT:
            inefficient.append({**row, "reparse_pct": round(reparse_pct, 2)})
    status = ProbeStatus.WARN if inefficient else ProbeStatus.PASS
    return ProbeResult("CP10", "code-projection-delta-efficiency", TIER, status, "delta efficiency within configured threshold" if not inefficient else f"{len(inefficient)} inefficient no-op/near-no-op ingest receipt(s)", {"rows": rows, "inefficient": inefficient, "warn_reparse_pct": config.CODE_PROJECTION_EFFICIENCY_WARN_REPARSE_PCT, "remediation": REMEDIATIONS["human_review"] if inefficient else REMEDIATIONS["observe"]})
