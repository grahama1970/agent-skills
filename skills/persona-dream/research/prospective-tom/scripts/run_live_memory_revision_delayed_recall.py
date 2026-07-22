#!/usr/bin/env python3
"""Re-read PCTOM-R revision Memory records from a fresh no-write process."""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

from run_live_memory_revision_recall import (
    COLLECTION,
    CONDITIONS,
    RECALL_COLLECTION,
    _documents_from_list,
    _file_sha256,
    _load_json,
    _post_json,
    _recall_hits_for_condition,
    _write_json,
)


PASS_STATUS = "PASS_PCTOM_LIVE_MEMORY_REVISION_DELAYED_RECALL"
BLOCKED_STATUS = "BLOCKED_PCTOM_LIVE_MEMORY_REVISION_DELAYED_RECALL"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _validate_source(source_root: Path, errors: list[str]) -> dict[str, Any]:
    receipt_path = source_root / "live_memory_revision_recall_receipt.v1.json"
    receipt = _load_json(receipt_path, errors, "source_live_memory_revision_recall_receipt")
    if not isinstance(receipt, dict):
        return {}
    expected = {
        "status": "PASS_PCTOM_LIVE_MEMORY_REVISION_RECALL",
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "live_memory_recall_performed": True,
        "human_content_judgment_required": False,
        "tau_call_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            errors.append(f"source_{key}_mismatch:{receipt.get(key)}:{value}")
    counts = receipt.get("counts") if isinstance(receipt.get("counts"), dict) else {}
    if counts.get("memory_documents_upserted", 0) < 16:
        errors.append(f"source_memory_documents_upserted_lt_16:{counts.get('memory_documents_upserted')}")
    if counts.get("memory_semantic_documents_upserted", 0) < 16:
        errors.append(f"source_memory_semantic_documents_upserted_lt_16:{counts.get('memory_semantic_documents_upserted')}")
    if counts.get("memory_exact_rereads") != counts.get("memory_documents_upserted"):
        errors.append(f"source_exact_reread_count_mismatch:{counts.get('memory_exact_rereads')}:{counts.get('memory_documents_upserted')}")
    if counts.get("memory_semantic_exact_rereads") != counts.get("memory_semantic_documents_upserted"):
        errors.append(
            "source_semantic_exact_reread_count_mismatch:"
            f"{counts.get('memory_semantic_exact_rereads')}:{counts.get('memory_semantic_documents_upserted')}"
        )
    checks = receipt.get("checks") if isinstance(receipt.get("checks"), dict) else {}
    for key in (
        "memory_exact_reread_complete",
        "memory_semantic_exact_reread_complete",
        "live_memory_recall_hits_per_condition",
        "prior_and_posterior_distinguished",
        "synthetic_literal_boundary_preserved",
        "unsupported_writes_absent",
    ):
        if checks.get(key) is not True:
            errors.append(f"source_check_not_true:{key}:{checks.get(key)}")
    return receipt


def _load_document_list(path_text: Any, errors: list[str], label: str) -> list[dict[str, Any]]:
    if not isinstance(path_text, str) or not path_text:
        errors.append(f"{label}_path_missing:{path_text}")
        return []
    value = _load_json(Path(path_text), errors, label)
    if not isinstance(value, list):
        errors.append(f"{label}_not_list:{path_text}")
        return []
    return [item for item in value if isinstance(item, dict)]


def _compare_exact_row(row: dict[str, Any], expected: dict[str, Any], errors: list[str], label: str) -> dict[str, Any]:
    key = expected.get("_key")
    found = isinstance(row, dict)
    result = {
        "_key": key,
        "found": found,
        "condition": row.get("condition") if found else None,
        "episode_id": row.get("episode_id") if found else None,
        "revision_id": row.get("revision_id") if found else None,
        "prior_and_posterior_distinguished": row.get("prior_and_posterior_distinguished") if found else None,
        "synthetic_literal_boundary_preserved": row.get("synthetic_literal_boundary_preserved") if found else None,
        "canonical_memory_write": row.get("canonical_memory_write") if found else None,
        "identity_write": row.get("identity_write") if found else None,
        "source_memory_write": row.get("source_memory_write") if found else None,
        "source_document_sha256": expected.get("source_document_sha256"),
    }
    if not found:
        errors.append(f"{label}_not_found:{key}")
        return result
    for field in ("condition", "episode_id", "revision_id"):
        if row.get(field) != expected.get(field):
            errors.append(f"{label}_{field}_mismatch:{key}:{row.get(field)}:{expected.get(field)}")
    for field in ("prior_and_posterior_distinguished", "synthetic_literal_boundary_preserved"):
        if row.get(field) is not True:
            errors.append(f"{label}_{field}_not_true:{key}:{row.get(field)}")
    for field in ("canonical_memory_write", "identity_write", "source_memory_write"):
        if row.get(field) is not False:
            errors.append(f"{label}_{field}_not_false:{key}:{row.get(field)}")
    return result


def run(
    *,
    source_root: Path,
    output_root: Path,
    receipt_out: Path,
    memory_base_url: str,
    recall_attempts: int,
    recall_sleep_s: float,
) -> dict[str, Any]:
    started = time.monotonic()
    errors: list[str] = []
    source_root = source_root.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    source_receipt_path = source_root / "live_memory_revision_recall_receipt.v1.json"
    source_receipt = _validate_source(source_root, errors)
    source_receipt_sha256 = _file_sha256(source_receipt_path) if source_receipt_path.exists() else None
    collection = str(source_receipt.get("collection") or COLLECTION)
    recall_collection = str(source_receipt.get("semantic_recall_collection") or RECALL_COLLECTION)
    documents = _load_document_list(source_receipt.get("document_index"), errors, "source_document_index")
    semantic_documents = _load_document_list(source_receipt.get("semantic_document_index"), errors, "source_semantic_document_index")

    docs_by_key = {str(doc.get("_key")): doc for doc in documents if isinstance(doc.get("_key"), str)}
    semantic_docs_by_key = {str(doc.get("_key")): doc for doc in semantic_documents if isinstance(doc.get("_key"), str)}
    semantic_expected_keys = set(semantic_docs_by_key)
    run_ids = sorted({str(doc.get("run_id")) for doc in semantic_documents if doc.get("run_id")})
    run_id = run_ids[0] if len(run_ids) == 1 else ""
    if len(run_ids) != 1:
        errors.append(f"source_run_id_count_mismatch:{run_ids}")

    exact_rereads: list[dict[str, Any]] = []
    semantic_exact_rereads: list[dict[str, Any]] = []
    recall_results: list[dict[str, Any]] = []
    headers = {"X-Caller-Skill": "persona-dream"}
    timeout = httpx.Timeout(20.0, connect=3.0)
    with httpx.Client(base_url=memory_base_url.rstrip("/"), timeout=timeout, headers=headers) as client:
        for key, expected in docs_by_key.items():
            status, listed, list_error = _post_json(
                client,
                "/list",
                {"collection": collection, "limit": 2, "filters": {"_key": key}},
            )
            rows = _documents_from_list(listed)
            row = rows[0] if rows else {}
            result = _compare_exact_row(row, expected, errors, "delayed_exact_reread")
            result["http_status"] = status
            result["error"] = list_error
            exact_rereads.append(result)
            if list_error:
                errors.append(f"delayed_exact_reread_error:{key}:{list_error}")
            if status is None or status >= 400:
                errors.append(f"delayed_exact_reread_http_status:{key}:{status}")

        for key, expected in semantic_docs_by_key.items():
            status, listed, list_error = _post_json(
                client,
                "/list",
                {"collection": recall_collection, "limit": 2, "filters": {"_key": key}},
            )
            rows = _documents_from_list(listed)
            row = rows[0] if rows else {}
            result = _compare_exact_row(row, expected, errors, "delayed_semantic_exact_reread")
            result["research_document_key"] = expected.get("research_document_key")
            result["http_status"] = status
            result["error"] = list_error
            semantic_exact_rereads.append(result)
            if list_error:
                errors.append(f"delayed_semantic_exact_reread_error:{key}:{list_error}")
            if status is None or status >= 400:
                errors.append(f"delayed_semantic_exact_reread_http_status:{key}:{status}")

        for condition in CONDITIONS:
            query = (
                f"Persona Dream PCTOM-R delayed multi-session action-linked revision recall "
                f"condition {condition} prior posterior distinguished synthetic literal boundary preserved run {run_id}"
            )
            attempts: list[dict[str, Any]] = []
            chosen_hits: list[dict[str, Any]] = []
            for attempt in range(1, max(1, recall_attempts) + 1):
                payload = {
                    "q": query,
                    "k": 10,
                    "collections": [recall_collection],
                    "tags": ["persona-dream", "pctom-r", "revision-recall", f"condition:{condition}"],
                }
                status, recalled, recall_error = _post_json(client, "/recall", payload)
                items = recalled.get("items", []) if isinstance(recalled, dict) and isinstance(recalled.get("items"), list) else []
                hits = _recall_hits_for_condition(items, semantic_expected_keys, condition, semantic_docs_by_key)
                attempts.append(
                    {
                        "attempt": attempt,
                        "http_status": status,
                        "found": recalled.get("found") if isinstance(recalled, dict) else None,
                        "item_count": len(items),
                        "hit_count": len(hits),
                        "hits": hits,
                        "error": recall_error,
                    }
                )
                if recall_error:
                    errors.append(f"delayed_recall_error:{condition}:{attempt}:{recall_error}")
                if status is None or status >= 400:
                    errors.append(f"delayed_recall_http_status:{condition}:{attempt}:{status}")
                if hits:
                    chosen_hits = hits
                    break
                if attempt < recall_attempts:
                    time.sleep(recall_sleep_s)
            recall_results.append(
                {
                    "query_id": f"delayed-live-memory-revision-recall-{condition.lower()}",
                    "query": query,
                    "condition": condition,
                    "attempts": attempts,
                    "hit_count": len(chosen_hits),
                    "hits": chosen_hits,
                }
            )

    exact_reread_path = output_root / "artifacts" / "delayed_exact_rereads.json"
    semantic_exact_reread_path = output_root / "artifacts" / "delayed_semantic_exact_rereads.json"
    recall_results_path = output_root / "artifacts" / "delayed_recall_results.json"
    _write_json(exact_reread_path, exact_rereads)
    _write_json(semantic_exact_reread_path, semantic_exact_rereads)
    _write_json(recall_results_path, recall_results)

    exact_reread_count = sum(1 for row in exact_rereads if row.get("found") is True)
    semantic_exact_reread_count = sum(1 for row in semantic_exact_rereads if row.get("found") is True)
    recall_hits = sum(int(result.get("hit_count", 0)) for result in recall_results)
    recall_hits_per_condition = {str(result.get("condition")): int(result.get("hit_count", 0)) for result in recall_results}
    prior_and_posterior_distinguished = all(
        row.get("prior_and_posterior_distinguished") is True for row in exact_rereads + semantic_exact_rereads
    ) and all(
        hit.get("prior_and_posterior_distinguished") is True
        for result in recall_results
        for hit in result.get("hits", [])
    )
    synthetic_literal_boundary_preserved = all(
        row.get("synthetic_literal_boundary_preserved") is True for row in exact_rereads + semantic_exact_rereads
    ) and all(
        hit.get("synthetic_literal_boundary_preserved") is True
        for result in recall_results
        for hit in result.get("hits", [])
    )
    write_violations = sum(
        1
        for row in exact_rereads + semantic_exact_rereads
        for field in ("canonical_memory_write", "identity_write", "source_memory_write")
        if row.get(field) is not False
    )
    if exact_reread_count != len(documents):
        errors.append(f"delayed_exact_reread_count_mismatch:{exact_reread_count}:{len(documents)}")
    if semantic_exact_reread_count != len(semantic_documents):
        errors.append(f"delayed_semantic_exact_reread_count_mismatch:{semantic_exact_reread_count}:{len(semantic_documents)}")
    for condition in CONDITIONS:
        if recall_hits_per_condition.get(condition, 0) < 1:
            errors.append(f"delayed_recall_hits_per_condition_insufficient:{condition}:{recall_hits_per_condition.get(condition, 0)}")
    if not prior_and_posterior_distinguished:
        errors.append("delayed_prior_and_posterior_distinguished_false")
    if not synthetic_literal_boundary_preserved:
        errors.append("delayed_synthetic_literal_boundary_preserved_false")
    if write_violations != 0:
        errors.append(f"delayed_write_violations_nonzero:{write_violations}")

    source_created_at = source_receipt.get("created_at")
    created_at = _now_iso()
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_memory_revision_delayed_recall_receipt.v1",
        "created_at": created_at,
        "status": PASS_STATUS if not errors else BLOCKED_STATUS,
        "source_root": str(source_root),
        "source_receipt": str(source_receipt_path),
        "source_receipt_sha256": source_receipt_sha256,
        "source_created_at": source_created_at,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "fresh_process_pid": os.getpid(),
        "fresh_process_started_after_source_receipt": isinstance(source_created_at, str) and source_created_at < created_at,
        "collection": collection,
        "semantic_recall_collection": recall_collection,
        "memory_base_url": memory_base_url.rstrip("/"),
        "source_document_index": source_receipt.get("document_index"),
        "source_semantic_document_index": source_receipt.get("semantic_document_index"),
        "delayed_exact_rereads": str(exact_reread_path),
        "delayed_semantic_exact_rereads": str(semantic_exact_reread_path),
        "delayed_recall_results": str(recall_results_path),
        "conditions": list(CONDITIONS),
        "errors": errors,
        "counts": {
            "source_memory_documents": len(documents),
            "source_semantic_documents": len(semantic_documents),
            "delayed_exact_rereads": exact_reread_count,
            "delayed_semantic_exact_rereads": semantic_exact_reread_count,
            "delayed_recall_queries": len(recall_results),
            "delayed_recall_hits": recall_hits,
            "delayed_recall_hits_per_condition": recall_hits_per_condition,
            "write_violations": write_violations,
        },
        "checks": {
            "source_live_memory_revision_recall_passed": source_receipt.get("status") == "PASS_PCTOM_LIVE_MEMORY_REVISION_RECALL",
            "source_receipt_hash_recomputed": isinstance(source_receipt_sha256, str) and source_receipt_sha256.startswith("sha256:"),
            "fresh_process_no_write_path": True,
            "delayed_exact_reread_complete": exact_reread_count == len(documents),
            "delayed_semantic_exact_reread_complete": semantic_exact_reread_count == len(semantic_documents),
            "delayed_live_memory_recall_performed": len(recall_results) == len(CONDITIONS),
            "delayed_live_memory_recall_hits_per_condition": all(
                recall_hits_per_condition.get(condition, 0) >= 1 for condition in CONDITIONS
            ),
            "prior_and_posterior_distinguished": prior_and_posterior_distinguished,
            "synthetic_literal_boundary_preserved": synthetic_literal_boundary_preserved,
            "unsupported_writes_absent": write_violations == 0,
            "human_content_judgment_absent": True,
        },
        "artifact_sha256": {
            "delayed_exact_rereads": _file_sha256(exact_reread_path),
            "delayed_semantic_exact_rereads": _file_sha256(semantic_exact_reread_path),
            "delayed_recall_results": _file_sha256(recall_results_path),
        },
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "fresh_process_delayed_recall": True,
        "memory_write_attempts": 0,
        "tau_call_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "processing_time_s": round(time.monotonic() - started, 6),
        "claims": {
            "proves": [
                "a fresh no-write process can exact-reread previously persisted noncanonical PCTOM-R revision documents",
                "a fresh no-write process can exact-reread the searchable semantic mirrors",
                "a fresh no-write process can retrieve delayed condition-scoped revision context through live Memory /recall",
                "prior/posterior distinction and synthetic/literal separation survive delayed recall",
                "no Memory write, provider call, Tau call, canonical write, identity write, source-memory write, LLM judge, or human content judgment was used",
            ]
            if not errors
            else [
                "the delayed live Memory revision-recall checker failed closed before accepting delayed recall evidence",
            ],
            "does_not_prove": [
                "Memory service restart",
                "long-duration wall-clock retention beyond the source artifact interval",
                "new live Tau execution",
                "paid provider execution",
                "video, audio, or semantic dream quality",
                "complete live Phase 01-16 runtime execution",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    receipt["receipt_sha256"] = _file_sha256(receipt_out)
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--memory-base-url", default="http://127.0.0.1:8601")
    parser.add_argument("--recall-attempts", type=int, default=3)
    parser.add_argument("--recall-sleep-s", type=float, default=1.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt_out = args.receipt_out or (args.output_root / "live_memory_revision_delayed_recall_receipt.v1.json")
    receipt = run(
        source_root=args.source_root,
        output_root=args.output_root,
        receipt_out=receipt_out,
        memory_base_url=args.memory_base_url,
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
