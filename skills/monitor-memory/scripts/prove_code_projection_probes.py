#!/usr/bin/env python3
"""Live Arango fixture campaign for monitor-memory code-projection probes."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from arango import ArangoClient

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

import config  # noqa: E402
from probes import ProbeStatus, registry  # noqa: E402
from probes import tier_code_projection as cp  # noqa: E402

COLLECTIONS = (
    "code_indexes",
    "code_generations",
    "code_files",
    "code_symbols",
    "curate_edges",
    "semantic_projection_outbox",
    "code_recall_canaries",
    "code_debug_recipes",
    "code_ingest_telemetry",
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _refuse_production(db_name: str) -> None:
    profile = " ".join(
        str(os.environ.get(name, ""))
        for name in ("MEMORY_ENV", "APP_ENV", "ENVIRONMENT", "GRAPH_MEMORY_PROFILE")
    ).lower()
    if "prod" in profile or os.environ.get("GRAPH_MEMORY_PRODUCTION") == "1":
        raise SystemExit("refusing to run monitor-memory code projection proof against production profile")
    if not db_name.startswith("monitor_memory_issue1354_"):
        raise SystemExit(f"refusing non-proof database name: {db_name}")


def _client() -> ArangoClient:
    return ArangoClient(hosts=config.ARANGO_URL)


def _system_db(client: ArangoClient):
    return client.db(
        "_system",
        username=os.environ.get("ARANGO_USER", "root"),
        password=os.environ.get("ARANGO_PASS", ""),
    )


def _reset_database(db_name: str):
    client = _client()
    system = _system_db(client)
    if system.has_database(db_name):
        system.delete_database(db_name)
    system.create_database(db_name)
    db = client.db(
        db_name,
        username=os.environ.get("ARANGO_USER", "root"),
        password=os.environ.get("ARANGO_PASS", ""),
    )
    for name in COLLECTIONS:
        if not db.has_collection(name):
            db.create_collection(name)
    config.ARANGO_DB = db_name
    return db


def _insert(db: Any, collection: str, docs: list[dict[str, Any]]) -> None:
    col = db.collection(collection)
    for doc in docs:
        col.insert(doc, overwrite=True)


def _base_projection(
    db: Any,
    *,
    scope: str,
    case_id: str,
    root: Path,
    files: int = 1,
    symbols: int = 1,
    edges: int = 1,
    active: str = "cg_current",
    transform: str | None = None,
    semantic_schema: str | None = None,
    synced: bool = True,
    expected_counts: dict[str, int] | None = None,
) -> dict[str, str]:
    code_index_id = f"ci_{case_id}"
    generation_id = f"{active}_{case_id}"
    root.mkdir(parents=True, exist_ok=True)
    source = root / f"{case_id}.py"
    source.write_text(f"def {case_id.replace('-', '_')}():\n    return {case_id!r}\n", encoding="utf-8")
    file_docs = [
        {
            "_key": f"cf_{case_id}_{i}",
            "scope": scope,
            "code_index_id": code_index_id,
            "generation_id": generation_id,
            "path": source.name,
            "root": str(root),
            "active_for_retrieval": True,
        }
        for i in range(files)
    ]
    symbol_docs = [
        {
            "_key": f"cs_{case_id}_{i}",
            "scope": scope,
            "code_index_id": code_index_id,
            "generation_id": generation_id,
            "symbol_id": f"sym_{case_id}_{i}",
            "root": str(root),
            "path": source.name,
            "content_hash": _sha256(source),
            "active_for_retrieval": True,
            "qdrant_point_id": f"qp_{case_id}_{i}" if synced else "",
            "semantic_sync_state": "synced" if synced else "pending",
            "retrieval_text_sha256": f"sha256:text-{case_id}-{i}",
            "text_hash": f"sha256:text-{case_id}-{i}",
            "semantic_text_schema": semantic_schema or config.CODE_PROJECTION_EXPECTED_SEMANTIC_TEXT_SCHEMA,
            "derived_summary_status": "current",
        }
        for i in range(symbols)
    ]
    edge_docs = [
        {
            "_key": f"ce_{case_id}_{i}",
            "_from": f"code_files/cf_{case_id}_0",
            "_to": f"code_symbols/cs_{case_id}_0",
            "scope": scope,
            "code_index_id": code_index_id,
            "generation_id": generation_id,
            "active_for_retrieval": True,
            "active_for_traversal": True,
            "status": "resolved",
        }
        for i in range(edges)
    ]
    counts = expected_counts or {"files": files, "symbols": symbols, "edges": edges}
    _insert(
        db,
        "code_indexes",
        [
            {
                "_key": code_index_id,
                "scope": scope,
                "branch": "main",
                "root": str(root),
                "repo": "monitor-memory-proof",
                "active_generation_id": generation_id,
                "updated_at": _now(),
            }
        ],
    )
    _insert(
        db,
        "code_generations",
        [
            {
                "_key": generation_id,
                "scope": scope,
                "branch": "main",
                "code_index_id": code_index_id,
                "generation_id": generation_id,
                "status": "active",
                "accepted_bundle_digest": f"sha256:bundle-{case_id}",
                "expected_counts": counts,
                "transform_fingerprint": transform or config.CODE_PROJECTION_EXPECTED_TRANSFORM_FINGERPRINT,
                "config_fingerprint": "sha256:config",
                "created_at": _now(),
            }
        ],
    )
    _insert(db, "code_files", file_docs)
    _insert(db, "code_symbols", symbol_docs)
    _insert(db, "curate_edges", edge_docs)
    return {"scope": scope, "code_index_id": code_index_id, "generation_id": generation_id, "source_path": str(source)}


def _run_case(
    db: Any,
    *,
    case_id: str,
    description: str,
    probe_name: str,
    expected_status: ProbeStatus,
    setup: Callable[[Any, Path, str], dict[str, Any]],
    out_dir: Path,
    fixture_root: Path,
) -> dict[str, Any]:
    case_root = fixture_root / case_id
    context = setup(db, case_root, case_id)
    probe = registry.get_probes(probe_name=probe_name)[0]["fn"]
    result = probe(autofix=False)
    receipt = {
        "case_id": case_id,
        "description": description,
        "probe": probe_name,
        "expected_status": expected_status.value,
        "observed_status": result.status.value,
        "passed": result.status == expected_status,
        "context": context,
        "result": {
            "probe_id": result.probe_id,
            "name": result.name,
            "tier": result.tier,
            "status": result.status.value,
            "message": result.message,
            "details": result.details,
        },
        "mocked": False,
        "live": True,
    }
    _write_json(out_dir / f"{case_id}.json", receipt)
    return receipt


def main() -> int:
    run_id = os.environ.get("PROOF_RUN_ID") or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    db_name = f"monitor_memory_issue1354_{run_id.lower().replace('-', '_')}"
    _refuse_production(db_name)
    out_dir = Path("reports/monitor-memory/issue1354-live") / run_id
    if out_dir.exists():
        shutil.rmtree(out_dir)
    fixture_root = out_dir / "fixture-repos"
    db = _reset_database(db_name)
    config.ARANGO_DB = db_name

    def healthy(db: Any, root: Path, case_id: str) -> dict[str, Any]:
        return _base_projection(db, scope=case_id, case_id=case_id, root=root)

    def two_active(db: Any, root: Path, case_id: str) -> dict[str, Any]:
        ctx = _base_projection(db, scope=case_id, case_id=case_id, root=root)
        second = f"cg_second_{case_id}"
        _insert(
            db,
            "code_generations",
            [{
                "_key": second,
                "scope": case_id,
                "branch": "main",
                "code_index_id": ctx["code_index_id"],
                "generation_id": second,
                "status": "active",
                "expected_counts": {"files": 1, "symbols": 1, "edges": 1},
                "accepted_bundle_digest": f"sha256:second-{case_id}",
                "transform_fingerprint": config.CODE_PROJECTION_EXPECTED_TRANSFORM_FINGERPRINT,
            }],
        )
        _insert(
            db,
            "code_symbols",
            [{
                "_key": f"cs_mixed_{case_id}",
                "scope": case_id,
                "code_index_id": ctx["code_index_id"],
                "generation_id": second,
                "symbol_id": f"sym_mixed_{case_id}",
                "active_for_retrieval": True,
                "qdrant_point_id": f"qp_mixed_{case_id}",
                "semantic_sync_state": "synced",
            }],
        )
        return ctx

    def count_mismatch(db: Any, root: Path, case_id: str) -> dict[str, Any]:
        return _base_projection(db, scope=case_id, case_id=case_id, root=root, expected_counts={"files": 9, "symbols": 9, "edges": 9})

    def incomplete_preserves(db: Any, root: Path, case_id: str) -> dict[str, Any]:
        ctx = _base_projection(db, scope=case_id, case_id=case_id, root=root)
        _insert(
            db,
            "code_generations",
            [{
                "_key": f"cg_rejected_{case_id}",
                "scope": case_id,
                "branch": "main",
                "code_index_id": ctx["code_index_id"],
                "generation_id": f"cg_rejected_{case_id}",
                "status": "rejected",
                "active_before_generation_id": ctx["generation_id"],
                "active_after_generation_id": ctx["generation_id"],
                "current_keyset_mutated": False,
            }],
        )
        return ctx

    def orphan_symbol(db: Any, root: Path, case_id: str) -> dict[str, Any]:
        return _base_projection(db, scope=case_id, case_id=case_id, root=root, synced=False)

    def retired_qdrant(db: Any, root: Path, case_id: str) -> dict[str, Any]:
        ctx = _base_projection(db, scope=case_id, case_id=case_id, root=root)
        _insert(
            db,
            "code_symbols",
            [{
                "_key": f"cs_retired_{case_id}",
                "scope": case_id,
                "code_index_id": ctx["code_index_id"],
                "generation_id": f"cg_old_{case_id}",
                "symbol_id": f"sym_retired_{case_id}",
                "active_for_retrieval": False,
                "qdrant_point_id": f"qp_retired_{case_id}",
                "semantic_sync_state": "synced",
            }],
        )
        return ctx

    def outbox_backlog(db: Any, root: Path, case_id: str) -> dict[str, Any]:
        ctx = _base_projection(db, scope=case_id, case_id=case_id, root=root)
        _insert(
            db,
            "semantic_projection_outbox",
            [{
                "_key": f"spo_{case_id}",
                "scope": case_id,
                "code_index_id": ctx["code_index_id"],
                "generation_id": ctx["generation_id"],
                "arango_collection": "code_symbols",
                "state": "failed",
                "last_error": "simulated qdrant outage",
                "created_at": _now(),
            }],
        )
        return ctx

    def retired_leakage(db: Any, root: Path, case_id: str) -> dict[str, Any]:
        ctx = _base_projection(db, scope=case_id, case_id=case_id, root=root)
        _insert(
            db,
            "code_recall_canaries",
            [{
                "_key": f"crc_{case_id}",
                "kind": "retired_symbol_leakage",
                "scope": case_id,
                "code_index_id": ctx["code_index_id"],
                "generation_id": ctx["generation_id"],
                "symbol_id": f"sym_retired_{case_id}",
                "route": "generic_bm25",
                "leaked": True,
                "history_available": True,
                "receipt_ref": f"proof/{case_id}",
            }],
        )
        return ctx

    def stale_source(db: Any, root: Path, case_id: str) -> dict[str, Any]:
        ctx = _base_projection(db, scope=case_id, case_id=case_id, root=root)
        path = Path(ctx["source_path"])
        path.write_text("def changed():\n    return 'changed'\n", encoding="utf-8")
        return ctx

    def transform_drift(db: Any, root: Path, case_id: str) -> dict[str, Any]:
        return _base_projection(db, scope=case_id, case_id=case_id, root=root, transform="old-transform")

    def stale_doc_debug(db: Any, root: Path, case_id: str) -> dict[str, Any]:
        ctx = _base_projection(db, scope=case_id, case_id=case_id, root=root)
        db.aql.execute(
            """
            FOR d IN code_symbols
              FILTER d.scope == @scope
              UPDATE d WITH {derived_summary_status: "stale"} IN code_symbols
            """,
            bind_vars={"scope": case_id},
        )
        _insert(
            db,
            "code_debug_recipes",
            [{
                "_key": f"cdr_{case_id}",
                "scope": case_id,
                "code_index_id": ctx["code_index_id"],
                "generation_id": ctx["generation_id"],
                "status": "needs_fixture",
            }],
        )
        return ctx

    def inefficient(db: Any, root: Path, case_id: str) -> dict[str, Any]:
        ctx = _base_projection(db, scope=case_id, case_id=case_id, root=root)
        _insert(
            db,
            "code_ingest_telemetry",
            [{
                "_key": f"cit_{case_id}",
                "scope": case_id,
                "code_index_id": ctx["code_index_id"],
                "generation_id": ctx["generation_id"],
                "discovered_files": 100,
                "parsed_files": 80,
                "reused_files": 20,
                "rebuilt_symbols": 80,
                "rebuilt_edges": 80,
                "embedding_reuse_count": 20,
                "bytes_read": 1024,
                "duration_ms": 1200,
                "created_at": _now(),
            }],
        )
        return ctx

    cases = [
        ("healthy", "fully healthy active generation and semantic parity", "code-projection-active-generation", ProbeStatus.PASS, healthy),
        ("two-active", "two active generations and mixed current records", "code-projection-active-generation", ProbeStatus.FAIL, two_active),
        ("count-mismatch", "active bundle expected counts mismatch observed Arango rows", "code-projection-bundle-reconciliation", ProbeStatus.FAIL, count_mismatch),
        ("incomplete-preserves", "rejected generation preserves prior active pointer and keyset", "code-projection-incomplete-immutability", ProbeStatus.PASS, incomplete_preserves),
        ("orphan-symbol", "active Arango symbol lacks current semantic point metadata", "code-projection-semantic-parity", ProbeStatus.FAIL, orphan_symbol),
        ("retired-qdrant", "retired symbol still has active Qdrant sync metadata", "code-projection-semantic-parity", ProbeStatus.FAIL, retired_qdrant),
        ("outbox-backlog", "semantic outbox backlog and simulated outage", "code-projection-outbox-backlog", ProbeStatus.FAIL, outbox_backlog),
        ("retired-leakage", "retired symbol leakage canary through current recall route", "code-projection-retired-recall-leakage", ProbeStatus.FAIL, retired_leakage),
        ("stale-source", "live source file hash differs from indexed code-symbol hash", "code-projection-source-freshness", ProbeStatus.WARN, stale_source),
        ("transform-drift", "active generation transform fingerprint drift", "code-projection-transform-drift", ProbeStatus.WARN, transform_drift),
        ("stale-doc-debug", "stale derived summary and unsafe debugger recipe state", "code-projection-doc-debugger-staleness", ProbeStatus.WARN, stale_doc_debug),
        ("inefficient-noop", "no-op ingest reparses too much of the repository", "code-projection-delta-efficiency", ProbeStatus.WARN, inefficient),
    ]

    receipts = [
        _run_case(
            db,
            case_id=case_id,
            description=description,
            probe_name=probe_name,
            expected_status=expected,
            setup=setup,
            out_dir=out_dir / "cases",
            fixture_root=fixture_root,
        )
        for case_id, description, probe_name, expected, setup in cases
    ]

    aggregate_results = registry.run_probes(tier=8, probe_name="", autofix=False)
    aggregate = [
        {
            "probe_id": result.probe_id,
            "name": result.name,
            "status": result.status.value,
            "message": result.message,
            "details": result.details,
        }
        for result in aggregate_results
    ]
    _write_json(out_dir / "aggregate-tier8.json", aggregate)
    summary = {
        "schema": "monitor_memory.code_projection_probe_proof.v1",
        "run_id": run_id,
        "database": db_name,
        "created_at": _now(),
        "mocked": False,
        "live": True,
        "case_count": len(receipts),
        "passed_cases": sum(1 for item in receipts if item["passed"]),
        "failed_cases": [item["case_id"] for item in receipts if not item["passed"]],
        "case_receipts": [str((out_dir / "cases" / f"{item['case_id']}.json").resolve()) for item in receipts],
        "aggregate_receipt": str((out_dir / "aggregate-tier8.json").resolve()),
        "stable_probe_ids": [result["probe_id"] for result in aggregate],
        "artifacts": {},
    }
    for path in sorted(out_dir.rglob("*.json")):
        if path.name == "proof-summary.json":
            continue
        summary["artifacts"][path.relative_to(out_dir).as_posix()] = _sha256(path)
    _write_json(out_dir / "proof-summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["passed_cases"] == summary["case_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
