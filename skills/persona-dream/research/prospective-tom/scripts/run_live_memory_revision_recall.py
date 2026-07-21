#!/usr/bin/env python3
"""Persist and recall PCTOM-R action-linked revisions through live Memory."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

import httpx


CONDITIONS = ("M", "R", "D", "CD")
COLLECTION = "persona_dream_pctom_revision_recall"
RECALL_COLLECTION = "lessons"
PASS_STATUS = "PASS_PCTOM_LIVE_MEMORY_REVISION_RECALL"
BLOCKED_STATUS = "BLOCKED_PCTOM_LIVE_MEMORY_REVISION_RECALL"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path, errors: list[str], label: str) -> Any:
    if not path.exists():
        errors.append(f"missing_{label}:{path}")
        return None
    if path.is_symlink():
        errors.append(f"symlink_{label}:{path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"malformed_{label}:{path}:{exc}")
        return None


def _safe_key_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_:-]+", "_", value)[:180]


def _validate_base(base_root: Path, errors: list[str]) -> dict[str, Any]:
    receipt_path = base_root / "live_tau_revision_recall_receipt.v1.json"
    receipt = _load_json(receipt_path, errors, "base_revision_recall_receipt")
    if not isinstance(receipt, dict):
        return {}
    expected = {
        "status": "PASS_LIVE_TAU_PCTOM_REVISION_RECALL",
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "deterministic_artifact_recall": True,
        "live_memory_recall_performed": False,
        "human_content_judgment_required": False,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            errors.append(f"base_{key}_mismatch:{receipt.get(key)}:{value}")
    counts = receipt.get("counts") if isinstance(receipt.get("counts"), dict) else {}
    if counts.get("revision_documents") != 16:
        errors.append(f"base_revision_documents_not_16:{counts.get('revision_documents')}")
    for condition, count in (counts.get("revision_documents_per_condition") or {}).items():
        if condition not in CONDITIONS or not isinstance(count, int) or count < 1:
            errors.append(f"base_revision_documents_per_condition_invalid:{condition}:{count}")
    checks = receipt.get("checks") if isinstance(receipt.get("checks"), dict) else {}
    for key in ("prior_and_posterior_distinguished", "synthetic_literal_boundary_preserved", "unsupported_writes_absent"):
        if checks.get(key) is not True:
            errors.append(f"base_check_not_true:{key}:{checks.get(key)}")
    return receipt


def _memory_document(source: dict[str, Any], base_receipt_sha256: str, run_id: str) -> dict[str, Any]:
    condition = str(source.get("condition"))
    episode_id = str(source.get("episode_id"))
    revision_id = str(source.get("revision_id"))
    key = _safe_key_part(f"pctom_revision_recall_{run_id}_{condition}_{episode_id}_{revision_id}")
    retrieval_text = (
        f"Persona Dream PCTOM-R live Memory recall after action-linked revision. "
        f"condition {condition}. episode {episode_id}. revision {revision_id}. "
        f"selected action {source.get('selected_action')}. oracle action {source.get('oracle_action')}. "
        f"prior hypothesis {source.get('prior_hypothesis_id')}. "
        f"actual label {source.get('actual_label')}. "
        f"prior actual probability {source.get('prior_actual_probability')}. "
        f"posterior actual probability {source.get('posterior_actual_probability')}. "
        f"prior posterior distinguished {source.get('prior_and_posterior_distinguished')}. "
        f"synthetic literal boundary preserved {source.get('synthetic_literal_boundary_preserved')}. "
        f"canonical identity source writes absent."
    )
    return {
        "_key": key,
        "schema": "persona_dream.research.prospective_tom.live_memory_revision_recall_document.v1",
        "kind": "pctom_action_linked_revision_recall",
        "run_id": run_id,
        "base_receipt_sha256": base_receipt_sha256,
        "source_document_sha256": _stable_json_sha256(source),
        "retrieval_text": retrieval_text,
        "text": retrieval_text,
        "problem": f"Recall PCTOM-R action-linked revision for condition {condition}",
        "solution": retrieval_text,
        "tags": [
            "persona-dream",
            "pctom-r",
            "revision-recall",
            "action-linked-revision",
            f"condition:{condition}",
            f"condition:{condition.lower()}",
            "synthetic-literal-boundary-preserved",
            "prior-posterior-distinguished",
        ],
        "episode_id": episode_id,
        "condition": condition,
        "revision_id": revision_id,
        "selected_action": source.get("selected_action"),
        "oracle_action": source.get("oracle_action"),
        "planning_regret": source.get("planning_regret"),
        "prior_hypothesis_id": source.get("prior_hypothesis_id"),
        "prior_distribution_sha256": source.get("prior_distribution_sha256"),
        "posterior_distribution_sha256": source.get("posterior_distribution_sha256"),
        "actual_label": source.get("actual_label"),
        "prior_actual_probability": source.get("prior_actual_probability"),
        "posterior_actual_probability": source.get("posterior_actual_probability"),
        "prior_and_posterior_distinguished": source.get("prior_and_posterior_distinguished"),
        "prior_remains_auditable": source.get("prior_remains_auditable"),
        "synthetic_literal_boundary_preserved": source.get("synthetic_literal_boundary_preserved"),
        "synthetic_branch_ids": source.get("synthetic_branch_ids"),
        "literal_history_branch_ids": source.get("literal_history_branch_ids"),
        "canonical_memory_write": False,
        "identity_write": False,
        "source_memory_write": False,
        "canonical_memory_write_attempt": False,
        "identity_write_attempt": False,
        "source_memory_write_attempt": False,
        "observed_at": _now_iso(),
    }


def _semantic_memory_document(source_doc: dict[str, Any], recall_collection: str) -> dict[str, Any]:
    condition = str(source_doc.get("condition"))
    key = _safe_key_part(f"lesson_{source_doc['_key']}")
    retrieval_text = str(source_doc.get("retrieval_text", ""))
    solution = (
        f"{retrieval_text} "
        f"research_collection {source_doc.get('research_collection', COLLECTION)}. "
        f"research_document_key {source_doc.get('_key')}. "
        f"condition {condition}. "
        f"prior_and_posterior_distinguished {source_doc.get('prior_and_posterior_distinguished')}. "
        f"synthetic_literal_boundary_preserved {source_doc.get('synthetic_literal_boundary_preserved')}. "
        "canonical_memory_write false. identity_write false. source_memory_write false."
    )
    return {
        "_key": key,
        "schema": "persona_dream.research.prospective_tom.live_memory_revision_recall_semantic_document.v1",
        "scope": "persona-dream-pctom-revision-recall",
        "problem": (
            f"Persona Dream PCTOM-R action-linked revision recall condition {condition} "
            f"run {source_doc.get('run_id')}"
        ),
        "solution": solution,
        "text": solution,
        "tags": source_doc.get("tags", []),
        "kind": source_doc.get("kind"),
        "run_id": source_doc.get("run_id"),
        "condition": condition,
        "episode_id": source_doc.get("episode_id"),
        "revision_id": source_doc.get("revision_id"),
        "research_collection": source_doc.get("research_collection", COLLECTION),
        "research_document_key": source_doc.get("_key"),
        "recall_collection": recall_collection,
        "prior_and_posterior_distinguished": source_doc.get("prior_and_posterior_distinguished"),
        "synthetic_literal_boundary_preserved": source_doc.get("synthetic_literal_boundary_preserved"),
        "canonical_memory_write": False,
        "identity_write": False,
        "source_memory_write": False,
        "canonical_memory_write_attempt": False,
        "identity_write_attempt": False,
        "source_memory_write_attempt": False,
        "observed_at": _now_iso(),
    }


def _documents_from_list(response_json: Any) -> list[dict[str, Any]]:
    if not isinstance(response_json, dict):
        return []
    for key in ("documents", "items", "results"):
        value = response_json.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _recall_hits_for_condition(
    items: list[dict[str, Any]],
    expected_keys: set[str],
    condition: str,
    docs_by_key: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for item in items:
        key = item.get("_key")
        if key not in expected_keys:
            continue
        expected_doc = docs_by_key.get(str(key), {})
        expected_condition = expected_doc.get("condition")
        if expected_condition != condition:
            continue
        recall_text = f"{item.get('problem') or ''} {item.get('solution') or ''} {item.get('text') or ''}"
        prior_posterior = (
            item.get("prior_and_posterior_distinguished") is True
            or "prior_and_posterior_distinguished True" in recall_text
            or "prior posterior distinguished True" in recall_text
        )
        synthetic_literal = (
            item.get("synthetic_literal_boundary_preserved") is True
            or "synthetic_literal_boundary_preserved True" in recall_text
            or "synthetic literal boundary preserved True" in recall_text
        )
        hits.append(
            {
                "_key": key,
                "condition": expected_condition,
                "episode_id": item.get("episode_id") or expected_doc.get("episode_id"),
                "revision_id": item.get("revision_id") or expected_doc.get("revision_id"),
                "research_document_key": item.get("research_document_key") or expected_doc.get("research_document_key"),
                "scores": item.get("scores"),
                "prior_and_posterior_distinguished": prior_posterior,
                "synthetic_literal_boundary_preserved": synthetic_literal,
            }
        )
    return hits


def _post_json(client: httpx.Client, path: str, payload: dict[str, Any]) -> tuple[int | None, dict[str, Any] | None, str | None]:
    try:
        response = client.post(path, json=payload)
        status = response.status_code
        try:
            data = response.json()
        except Exception as exc:
            return status, None, f"invalid_json_response:{exc}"
        return status, data if isinstance(data, dict) else {"value": data}, None
    except Exception as exc:
        return None, None, f"{type(exc).__name__}:{exc}"


def run_bridge(
    *,
    base_root: Path,
    output_root: Path,
    receipt_out: Path,
    memory_base_url: str,
    collection: str,
    recall_collection: str,
    recall_attempts: int,
    recall_sleep_s: float,
) -> dict[str, Any]:
    errors: list[str] = []
    started = time.monotonic()
    base_root = base_root.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    base_receipt_path = base_root / "live_tau_revision_recall_receipt.v1.json"
    base_receipt = _validate_base(base_root, errors)
    base_receipt_sha256 = _file_sha256(base_receipt_path) if base_receipt_path.exists() else None
    source_index_path = Path(str(base_receipt.get("recall_index", "")))
    source_documents = _load_json(source_index_path, errors, "base_revision_recall_index")
    if not isinstance(source_documents, list):
        errors.append("base_revision_recall_index_not_list")
        source_documents = []

    run_id = hashlib.sha256(f"{base_receipt_sha256}:{_now_iso()}".encode("utf-8")).hexdigest()[:12]
    documents = [
        _memory_document(source, str(base_receipt_sha256), run_id)
        for source in source_documents
        if isinstance(source, dict)
    ]
    for doc in documents:
        doc["research_collection"] = collection
    expected_keys = {doc["_key"] for doc in documents}
    semantic_documents = [_semantic_memory_document(doc, recall_collection) for doc in documents]
    semantic_expected_keys = {doc["_key"] for doc in semantic_documents}
    semantic_docs_by_key = {doc["_key"]: doc for doc in semantic_documents}
    documents_per_condition = {condition: 0 for condition in CONDITIONS}
    for doc in documents:
        if doc.get("condition") in CONDITIONS:
            documents_per_condition[doc["condition"]] += 1
        if doc.get("canonical_memory_write") is not False:
            errors.append(f"document_canonical_memory_write_not_false:{doc['_key']}")
        if doc.get("identity_write") is not False:
            errors.append(f"document_identity_write_not_false:{doc['_key']}")
        if doc.get("source_memory_write") is not False:
            errors.append(f"document_source_memory_write_not_false:{doc['_key']}")
        if doc.get("prior_and_posterior_distinguished") is not True:
            errors.append(f"document_prior_posterior_not_distinguished:{doc['_key']}")
        if doc.get("synthetic_literal_boundary_preserved") is not True:
            errors.append(f"document_synthetic_literal_boundary_not_preserved:{doc['_key']}")

    document_index_path = output_root / "artifacts" / "live_memory_revision_documents.json"
    semantic_document_index_path = output_root / "artifacts" / "live_memory_semantic_documents.json"
    _write_json(document_index_path, documents)
    _write_json(semantic_document_index_path, semantic_documents)

    upsert_status: int | None = None
    upsert_response: dict[str, Any] | None = None
    semantic_upsert_status: int | None = None
    semantic_upsert_response: dict[str, Any] | None = None
    exact_reread_rows: list[dict[str, Any]] = []
    semantic_exact_reread_rows: list[dict[str, Any]] = []
    exact_reread_errors: list[str] = []
    semantic_exact_reread_errors: list[str] = []
    recall_results: list[dict[str, Any]] = []
    memory_write_attempts = 0
    memory_upserted_documents = 0
    memory_semantic_upserted_documents = 0
    live_memory_recall_performed = False

    headers = {"X-Caller-Skill": "persona-dream"}
    timeout = httpx.Timeout(20.0, connect=3.0)
    with httpx.Client(base_url=memory_base_url.rstrip("/"), timeout=timeout, headers=headers) as client:
        if documents:
            memory_write_attempts += 1
            upsert_status, upsert_response, upsert_error = _post_json(
                client,
                "/upsert",
                {"collection": collection, "documents": documents},
            )
            if upsert_error:
                errors.append(f"memory_upsert_error:{upsert_error}")
            if upsert_status is None or upsert_status >= 400:
                errors.append(f"memory_upsert_http_status:{upsert_status}")
            else:
                memory_upserted_documents = len(documents)

        if semantic_documents:
            memory_write_attempts += 1
            semantic_upsert_status, semantic_upsert_response, semantic_upsert_error = _post_json(
                client,
                "/upsert",
                {"collection": recall_collection, "documents": semantic_documents},
            )
            if semantic_upsert_error:
                errors.append(f"memory_semantic_upsert_error:{semantic_upsert_error}")
            if semantic_upsert_status is None or semantic_upsert_status >= 400:
                errors.append(f"memory_semantic_upsert_http_status:{semantic_upsert_status}")
            else:
                memory_semantic_upserted_documents = len(semantic_documents)

        for doc in documents:
            status, listed, list_error = _post_json(
                client,
                "/list",
                {"collection": collection, "limit": 2, "filters": {"_key": doc["_key"]}},
            )
            rows = _documents_from_list(listed)
            row = rows[0] if rows else None
            exact_reread_rows.append(
                {
                    "_key": doc["_key"],
                    "http_status": status,
                    "found": isinstance(row, dict),
                    "condition": row.get("condition") if isinstance(row, dict) else None,
                    "prior_and_posterior_distinguished": row.get("prior_and_posterior_distinguished")
                    if isinstance(row, dict)
                    else None,
                    "synthetic_literal_boundary_preserved": row.get("synthetic_literal_boundary_preserved")
                    if isinstance(row, dict)
                    else None,
                    "canonical_memory_write": row.get("canonical_memory_write") if isinstance(row, dict) else None,
                    "identity_write": row.get("identity_write") if isinstance(row, dict) else None,
                    "source_memory_write": row.get("source_memory_write") if isinstance(row, dict) else None,
                    "error": list_error,
                }
            )
            if list_error:
                exact_reread_errors.append(f"{doc['_key']}:{list_error}")
            if status is None or status >= 400 or not isinstance(row, dict):
                exact_reread_errors.append(f"{doc['_key']}:exact_reread_failed:{status}")

        for doc in semantic_documents:
            status, listed, list_error = _post_json(
                client,
                "/list",
                {"collection": recall_collection, "limit": 2, "filters": {"_key": doc["_key"]}},
            )
            rows = _documents_from_list(listed)
            row = rows[0] if rows else None
            semantic_exact_reread_rows.append(
                {
                    "_key": doc["_key"],
                    "research_document_key": doc.get("research_document_key"),
                    "http_status": status,
                    "found": isinstance(row, dict),
                    "condition": row.get("condition") if isinstance(row, dict) else None,
                    "prior_and_posterior_distinguished": row.get("prior_and_posterior_distinguished")
                    if isinstance(row, dict)
                    else None,
                    "synthetic_literal_boundary_preserved": row.get("synthetic_literal_boundary_preserved")
                    if isinstance(row, dict)
                    else None,
                    "canonical_memory_write": row.get("canonical_memory_write") if isinstance(row, dict) else None,
                    "identity_write": row.get("identity_write") if isinstance(row, dict) else None,
                    "source_memory_write": row.get("source_memory_write") if isinstance(row, dict) else None,
                    "error": list_error,
                }
            )
            if list_error:
                semantic_exact_reread_errors.append(f"{doc['_key']}:{list_error}")
            if status is None or status >= 400 or not isinstance(row, dict):
                semantic_exact_reread_errors.append(f"{doc['_key']}:semantic_exact_reread_failed:{status}")

        for condition in CONDITIONS:
            query = (
                f"Persona Dream PCTOM-R action-linked revision recall condition {condition} "
                f"prior posterior distinguished synthetic literal boundary preserved run {run_id}"
            )
            condition_results: list[dict[str, Any]] = []
            condition_hits: list[dict[str, Any]] = []
            for attempt in range(1, max(1, recall_attempts) + 1):
                payload = {
                    "q": query,
                    "k": 10,
                    "collections": [recall_collection],
                    "tags": ["persona-dream", "pctom-r", "revision-recall", f"condition:{condition}"],
                }
                status, recalled, recall_error = _post_json(client, "/recall", payload)
                live_memory_recall_performed = True
                items = recalled.get("items", []) if isinstance(recalled, dict) and isinstance(recalled.get("items"), list) else []
                hits = _recall_hits_for_condition(items, semantic_expected_keys, condition, semantic_docs_by_key)
                condition_results.append(
                    {
                        "attempt": attempt,
                        "http_status": status,
                        "found": recalled.get("found") if isinstance(recalled, dict) else None,
                        "should_scan": recalled.get("should_scan") if isinstance(recalled, dict) else None,
                        "confidence": recalled.get("confidence") if isinstance(recalled, dict) else None,
                        "item_count": len(items),
                        "hit_count": len(hits),
                        "hits": hits,
                        "error": recall_error,
                    }
                )
                if hits:
                    condition_hits = hits
                    break
                if attempt < recall_attempts:
                    time.sleep(recall_sleep_s)
            recall_results.append(
                {
                    "query_id": f"live-memory-revision-recall-{condition.lower()}",
                    "query": query,
                    "condition": condition,
                    "attempts": condition_results,
                    "hit_count": len(condition_hits),
                    "hits": condition_hits,
                }
            )

    exact_reread_path = output_root / "artifacts" / "live_memory_exact_rereads.json"
    semantic_exact_reread_path = output_root / "artifacts" / "live_memory_semantic_exact_rereads.json"
    recall_results_path = output_root / "artifacts" / "live_memory_recall_results.json"
    upsert_response_path = output_root / "artifacts" / "live_memory_upsert_response.json"
    semantic_upsert_response_path = output_root / "artifacts" / "live_memory_semantic_upsert_response.json"
    _write_json(exact_reread_path, exact_reread_rows)
    _write_json(semantic_exact_reread_path, semantic_exact_reread_rows)
    _write_json(recall_results_path, recall_results)
    _write_json(upsert_response_path, upsert_response or {})
    _write_json(semantic_upsert_response_path, semantic_upsert_response or {})

    recall_hits = sum(result["hit_count"] for result in recall_results)
    recall_hits_per_condition = {result["condition"]: result["hit_count"] for result in recall_results}
    exact_reread_count = sum(1 for row in exact_reread_rows if row.get("found") is True)
    semantic_exact_reread_count = sum(1 for row in semantic_exact_reread_rows if row.get("found") is True)
    prior_and_posterior_distinguished = all(
        row.get("prior_and_posterior_distinguished") is True for row in exact_reread_rows if row.get("found") is True
    ) and all(
        row.get("prior_and_posterior_distinguished") is True
        for row in semantic_exact_reread_rows
        if row.get("found") is True
    ) and all(
        hit.get("prior_and_posterior_distinguished") is True
        for result in recall_results
        for hit in result.get("hits", [])
    )
    synthetic_literal_boundary_preserved = all(
        row.get("synthetic_literal_boundary_preserved") is True for row in exact_reread_rows if row.get("found") is True
    ) and all(
        row.get("synthetic_literal_boundary_preserved") is True
        for row in semantic_exact_reread_rows
        if row.get("found") is True
    ) and all(
        hit.get("synthetic_literal_boundary_preserved") is True
        for result in recall_results
        for hit in result.get("hits", [])
    )
    write_violations = 0
    for row in exact_reread_rows:
        if row.get("found") is not True:
            continue
        for key in ("canonical_memory_write", "identity_write", "source_memory_write"):
            if row.get(key) is not False:
                write_violations += 1
                errors.append(f"exact_reread_{key}_not_false:{row.get('_key')}:{row.get(key)}")
    for row in semantic_exact_reread_rows:
        if row.get("found") is not True:
            continue
        for key in ("canonical_memory_write", "identity_write", "source_memory_write"):
            if row.get(key) is not False:
                write_violations += 1
                errors.append(f"semantic_exact_reread_{key}_not_false:{row.get('_key')}:{row.get(key)}")

    errors.extend(f"exact_reread_error:{error}" for error in exact_reread_errors)
    errors.extend(f"semantic_exact_reread_error:{error}" for error in semantic_exact_reread_errors)
    for condition in CONDITIONS:
        if documents_per_condition[condition] < 1:
            errors.append(f"revision_documents_per_condition_insufficient:{condition}:{documents_per_condition[condition]}")
        if recall_hits_per_condition.get(condition, 0) < 1:
            errors.append(f"live_memory_recall_hits_per_condition_insufficient:{condition}:{recall_hits_per_condition.get(condition, 0)}")
    if not live_memory_recall_performed:
        errors.append("live_memory_recall_not_performed")
    if recall_hits < 1:
        errors.append("revision_recall_hits_insufficient:0")
    if exact_reread_count != len(documents):
        errors.append(f"exact_reread_count_mismatch:{exact_reread_count}:{len(documents)}")
    if semantic_exact_reread_count != len(semantic_documents):
        errors.append(f"semantic_exact_reread_count_mismatch:{semantic_exact_reread_count}:{len(semantic_documents)}")
    if not prior_and_posterior_distinguished:
        errors.append("prior_and_posterior_distinguished_false")
    if not synthetic_literal_boundary_preserved:
        errors.append("synthetic_literal_boundary_preserved_false")

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_memory_revision_recall_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "base_root": str(base_root),
        "base_receipt": str(base_receipt_path),
        "base_receipt_sha256": base_receipt_sha256,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "collection": collection,
        "exact_audit_collection": collection,
        "semantic_recall_collection": recall_collection,
        "memory_base_url": memory_base_url.rstrip("/"),
        "document_index": str(document_index_path),
        "semantic_document_index": str(semantic_document_index_path),
        "exact_rereads": str(exact_reread_path),
        "semantic_exact_rereads": str(semantic_exact_reread_path),
        "recall_results": str(recall_results_path),
        "upsert_response": str(upsert_response_path),
        "semantic_upsert_response": str(semantic_upsert_response_path),
        "conditions": list(CONDITIONS),
        "errors": errors,
        "counts": {
            "base_revision_documents": base_receipt.get("counts", {}).get("revision_documents")
            if isinstance(base_receipt.get("counts"), dict)
            else None,
            "memory_documents_prepared": len(documents),
            "memory_documents_upserted": memory_upserted_documents,
            "memory_semantic_documents_prepared": len(semantic_documents),
            "memory_semantic_documents_upserted": memory_semantic_upserted_documents,
            "memory_exact_rereads": exact_reread_count,
            "memory_semantic_exact_rereads": semantic_exact_reread_count,
            "revision_documents_per_condition": documents_per_condition,
            "revision_recall_queries": len(recall_results),
            "revision_recall_hits": recall_hits,
            "revision_recall_hits_per_condition": recall_hits_per_condition,
            "write_violations": write_violations,
        },
        "checks": {
            "base_revision_recall_passed": base_receipt.get("status") == "PASS_LIVE_TAU_PCTOM_REVISION_RECALL",
            "base_receipt_hash_recomputed": isinstance(base_receipt_sha256, str) and base_receipt_sha256.startswith("sha256:"),
            "memory_upsert_http_ok": upsert_status is not None and upsert_status < 400,
            "memory_semantic_upsert_http_ok": semantic_upsert_status is not None and semantic_upsert_status < 400,
            "memory_exact_reread_complete": exact_reread_count == len(documents),
            "memory_semantic_exact_reread_complete": semantic_exact_reread_count == len(semantic_documents),
            "conditions_represented": all(documents_per_condition[condition] >= 1 for condition in CONDITIONS),
            "live_memory_recall_performed": live_memory_recall_performed,
            "live_memory_recall_hits_present": recall_hits >= 1,
            "live_memory_recall_hits_per_condition": all(recall_hits_per_condition.get(condition, 0) >= 1 for condition in CONDITIONS),
            "prior_and_posterior_distinguished": prior_and_posterior_distinguished,
            "synthetic_literal_boundary_preserved": synthetic_literal_boundary_preserved,
            "human_content_judgment_absent": True,
            "unsupported_writes_absent": write_violations == 0,
        },
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "live_memory_recall_performed": live_memory_recall_performed,
        "deterministic_artifact_recall": False,
        "live_tau_originated_revision_artifacts_consumed": True,
        "deterministic_simulator_corpus_fixture_backed": True,
        "human_content_judgment_required": False,
        "tau_call_attempts": 0,
        "memory_write_attempts": memory_write_attempts,
        "memory_upsert_http_status": upsert_status,
        "memory_semantic_upsert_http_status": semantic_upsert_status,
        "memory_recall_attempts": sum(len(result.get("attempts", [])) for result in recall_results),
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "claims": {
            "proves": [
                "action-linked revisions were written to a noncanonical PCTOM-R research Memory collection",
                "searchable noncanonical lesson mirrors were written for live semantic recall",
                "Memory exact reread returned the written revision documents",
                "live /recall returned revision documents for M, R, D, and CD conditions",
                "prior and posterior distributions remain distinguishable in live-recalled revision context",
                "synthetic counterfactual branches remain excluded from literal history in live-recalled revision context",
                "canonical, identity, source-memory, provider, Tau, and human-content-judgment paths were not used",
            ]
            if status == PASS_STATUS
            else [
                "the live Memory revision-recall bridge failed closed before claiming live recall-after-revision evidence",
            ],
            "does_not_prove": [
                "held-out live Tau execution",
                "64-episode statistical confidence intervals",
                "planning benefit over the strongest baseline",
                "real external service fault injection",
                "production retry machinery",
                "complete live Phase 01-16 runtime execution",
                "paid provider execution",
                "video or semantic dream quality",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--memory-base-url", default="http://127.0.0.1:8601")
    parser.add_argument("--collection", default=COLLECTION)
    parser.add_argument("--recall-collection", default=RECALL_COLLECTION)
    parser.add_argument("--recall-attempts", type=int, default=3)
    parser.add_argument("--recall-sleep-s", type=float, default=1.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "live_memory_revision_recall_receipt.v1.json")
    receipt = run_bridge(
        base_root=args.base_root,
        output_root=args.output_root,
        receipt_out=receipt_out,
        memory_base_url=args.memory_base_url,
        collection=args.collection,
        recall_collection=args.recall_collection,
        recall_attempts=args.recall_attempts,
        recall_sleep_s=args.recall_sleep_s,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
