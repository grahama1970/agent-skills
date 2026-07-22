#!/usr/bin/env python3
"""Check deterministic recall/use over live-originated action-linked revisions."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


CONDITIONS = ("M", "R", "D", "CD")
PASS_STATUS = "PASS_LIVE_TAU_PCTOM_REVISION_RECALL"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_REVISION_RECALL"


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


def _validate_base(revision_root: Path, errors: list[str]) -> dict[str, Any]:
    receipt_path = revision_root / "live_tau_action_linked_revision_receipt.v1.json"
    receipt = _load_json(receipt_path, errors, "base_revision_receipt")
    if not isinstance(receipt, dict):
        return {}
    expected = {
        "status": "PASS_LIVE_TAU_PCTOM_ACTION_LINKED_REVISION",
        "mocked": False,
        "live": True,
        "fixture_backed": False,
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
    revision_cases_written = counts.get("revision_cases_written")
    if not isinstance(revision_cases_written, int) or revision_cases_written < 16:
        errors.append(f"base_revision_cases_written_lt_16:{revision_cases_written}")
    individual_status_counts = counts.get("individual_status_counts")
    pass_count = (
        individual_status_counts.get("PASS_TOM_BELIEF_REVISION")
        if isinstance(individual_status_counts, dict)
        else None
    )
    if pass_count != revision_cases_written:
        errors.append(f"base_individual_status_counts_mismatch:{individual_status_counts}:{revision_cases_written}")
    for key in ("prior_action_hypotheses_per_condition", "posterior_action_revisions_per_condition"):
        values = counts.get(key)
        if not isinstance(values, dict) or set(values) != set(CONDITIONS):
            errors.append(f"base_{key}_missing_conditions:{values}")
            continue
        for condition in CONDITIONS:
            if not isinstance(values.get(condition), int) or values[condition] < 4:
                errors.append(f"base_{key}_{condition}_lt_4:{values.get(condition)}")
    return receipt


def _load_base_action_rows(base_receipt: dict[str, Any], errors: list[str]) -> dict[tuple[str, str], dict[str, Any]]:
    base_action_receipt_path = Path(str(base_receipt.get("base_receipt", "")))
    action_root = base_action_receipt_path.parent
    action_index_path = action_root / "artifacts" / "live_condition_action_decisions.json"
    rows = _load_json(action_index_path, errors, "base_action_decision_index")
    index: dict[tuple[str, str], dict[str, Any]] = {}
    if not isinstance(rows, list):
        errors.append("base_action_decision_index_not_list")
        return index
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"base_action_decision_row_{idx}_not_object")
            continue
        key = (str(row.get("episode_id")), str(row.get("condition")))
        index[key] = row
    return index


def _distribution_values(entries: Any) -> dict[str, float]:
    if not isinstance(entries, list):
        return {}
    values: dict[str, float] = {}
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("value"), str) and isinstance(entry.get("probability"), (int, float)):
            values[entry["value"]] = float(entry["probability"])
    return values


def _synthetic_boundary(source_case_root: Path, errors: list[str]) -> dict[str, Any]:
    branch_path = source_case_root / "counterfactual_branch_bundle.json"
    outcome_path = source_case_root / "tom_outcome_reveal.json"
    branch_bundle = _load_json(branch_path, errors, "counterfactual_branch_bundle")
    outcome = _load_json(outcome_path, errors, "outcome_reveal")
    if not isinstance(branch_bundle, dict) or not isinstance(outcome, dict):
        return {
            "synthetic_branch_ids": [],
            "literal_history_branch_ids": [],
            "synthetic_literal_overlap": [],
            "preserved": False,
        }
    synthetic_branch_ids = [
        branch.get("branch_id")
        for branch in branch_bundle.get("branches", [])
        if isinstance(branch, dict) and branch.get("synthetic") is True and isinstance(branch.get("branch_id"), str)
    ]
    literal_history_branch_ids = [
        branch_id for branch_id in outcome.get("literal_history_branch_ids", []) if isinstance(branch_id, str)
    ]
    overlap = sorted(set(synthetic_branch_ids) & set(literal_history_branch_ids))
    return {
        "branch_bundle_sha256": _stable_json_sha256(branch_bundle),
        "outcome_reveal_sha256": _stable_json_sha256(outcome),
        "synthetic_branch_ids": synthetic_branch_ids,
        "literal_history_branch_ids": literal_history_branch_ids,
        "synthetic_literal_overlap": overlap,
        "preserved": not overlap and bool(synthetic_branch_ids) and bool(literal_history_branch_ids),
    }


def _recall_document(
    row: dict[str, Any],
    revision: dict[str, Any],
    gate7_receipt: dict[str, Any],
    boundary: dict[str, Any],
) -> dict[str, Any]:
    prior_distribution = revision.get("prior_distribution") if isinstance(revision.get("prior_distribution"), dict) else {}
    prior_values = _distribution_values(prior_distribution.get("distribution"))
    posterior_values = _distribution_values(revision.get("posterior_distribution"))
    actual_label = revision.get("prediction_error", {}).get("actual_label")
    prior_actual = prior_values.get(str(actual_label))
    posterior_actual = posterior_values.get(str(actual_label))
    return {
        "document_id": f"revision-recall:{row.get('episode_id')}:{row.get('condition')}",
        "episode_id": row.get("episode_id"),
        "condition": row.get("condition"),
        "selected_action": row.get("selected_action"),
        "oracle_action": row.get("oracle_action"),
        "planning_regret": row.get("planning_regret"),
        "revision_id": revision.get("revision_id"),
        "prior_hypothesis_id": revision.get("prior_hypothesis_id"),
        "prior_distribution_sha256": revision.get("prior_distribution_sha256"),
        "posterior_distribution_sha256": revision.get("posterior_distribution_sha256"),
        "actual_label": actual_label,
        "prior_actual_probability": prior_actual,
        "posterior_actual_probability": posterior_actual,
        "prior_and_posterior_distinguished": prior_distribution.get("distribution") != revision.get("posterior_distribution"),
        "prior_remains_auditable": revision.get("prior_remains_auditable") is True
        and gate7_receipt.get("checks", {}).get("prior_remains_auditable") is True,
        "synthetic_literal_boundary_preserved": boundary.get("preserved") is True,
        "synthetic_branch_ids": boundary.get("synthetic_branch_ids"),
        "literal_history_branch_ids": boundary.get("literal_history_branch_ids"),
        "canonical_memory_write": revision.get("canonical_memory_write"),
        "identity_write": revision.get("identity_write"),
        "source_memory_write": revision.get("source_memory_write"),
    }


def _run_query(query: dict[str, Any], documents: list[dict[str, Any]]) -> dict[str, Any]:
    terms = {str(term).lower() for term in query.get("must_match_terms", [])}
    hits: list[dict[str, Any]] = []
    for document in documents:
        haystack = json.dumps(document, sort_keys=True).lower()
        if all(term in haystack for term in terms):
            hits.append(
                {
                    "document_id": document["document_id"],
                    "episode_id": document["episode_id"],
                    "condition": document["condition"],
                    "revision_id": document["revision_id"],
                    "prior_hypothesis_id": document["prior_hypothesis_id"],
                }
            )
    return {
        "query_id": query["query_id"],
        "query": query["query"],
        "must_match_terms": sorted(terms),
        "hit_count": len(hits),
        "hits": hits,
    }


def run_bridge(revision_root: Path, output_root: Path, receipt_out: Path) -> dict[str, Any]:
    errors: list[str] = []
    revision_root = revision_root.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    base_receipt_path = revision_root / "live_tau_action_linked_revision_receipt.v1.json"
    base_receipt = _validate_base(revision_root, errors)
    base_receipt_sha256 = _file_sha256(base_receipt_path) if base_receipt_path.exists() else None
    revision_index_path = revision_root / "artifacts" / "live_action_linked_belief_revisions.json"
    revision_rows = _load_json(revision_index_path, errors, "revision_index")
    if not isinstance(revision_rows, list):
        errors.append("revision_index_not_list")
        revision_rows = []
    action_rows = _load_base_action_rows(base_receipt, errors)

    documents: list[dict[str, Any]] = []
    recall_queries: list[dict[str, Any]] = []
    prior_posterior_distinguished = True
    synthetic_boundary_preserved = True
    write_violations = 0
    documents_per_condition = {condition: 0 for condition in CONDITIONS}

    for idx, row in enumerate(revision_rows):
        if not isinstance(row, dict):
            errors.append(f"revision_row_{idx}_not_object")
            continue
        condition = row.get("condition")
        episode_id = row.get("episode_id")
        if condition not in CONDITIONS:
            errors.append(f"revision_row_{idx}_invalid_condition:{condition}")
            continue
        if row.get("status") != "PASS_TOM_BELIEF_REVISION":
            errors.append(f"revision_row_{idx}_not_pass:{row.get('status')}")
            continue
        revision_path = Path(str(row.get("revision_path", "")))
        gate7_receipt_path = Path(str(row.get("gate7_receipt_path", "")))
        revision = _load_json(revision_path, errors, f"revision_{episode_id}_{condition}")
        gate7_receipt = _load_json(gate7_receipt_path, errors, f"gate7_receipt_{episode_id}_{condition}")
        action_row = action_rows.get((str(episode_id), str(condition)))
        if action_row is None:
            errors.append(f"missing_action_row_for_revision:{episode_id}:{condition}")
            continue
        source_case_root = Path(str(action_row.get("source_case_root", "")))
        if not isinstance(revision, dict) or not isinstance(gate7_receipt, dict):
            continue
        boundary = _synthetic_boundary(source_case_root, errors)
        document = _recall_document(row, revision, gate7_receipt, boundary)
        documents.append(document)
        documents_per_condition[condition] += 1
        if not document["prior_and_posterior_distinguished"]:
            prior_posterior_distinguished = False
            errors.append(f"prior_posterior_not_distinguished:{episode_id}:{condition}")
        if not document["synthetic_literal_boundary_preserved"]:
            synthetic_boundary_preserved = False
            errors.append(f"synthetic_literal_boundary_not_preserved:{episode_id}:{condition}")
        for key in ("canonical_memory_write", "identity_write", "source_memory_write"):
            if document.get(key) is not False:
                write_violations += 1
                errors.append(f"{key}_not_false:{episode_id}:{condition}:{document.get(key)}")

    for condition in CONDITIONS:
        if documents_per_condition[condition] < 1:
            errors.append(f"revision_documents_per_condition_insufficient:{condition}:{documents_per_condition[condition]}")
        recall_queries.append(
            {
                "query_id": f"revision-recall-{condition.lower()}",
                "query": f"Recall action-linked current posterior for condition {condition}",
                "must_match_terms": ["revision-recall", f'"condition": "{condition.lower()}"'],
            }
        )
    recall_results = [_run_query(query, documents) for query in recall_queries]
    recall_hits = sum(result["hit_count"] for result in recall_results)
    if len(recall_queries) < 1:
        errors.append("revision_recall_queries_insufficient:0")
    if recall_hits < 1:
        errors.append("revision_recall_hits_insufficient:0")

    recall_index_path = output_root / "artifacts" / "revision_recall_index.json"
    recall_results_path = output_root / "artifacts" / "revision_recall_results.json"
    _write_json(recall_index_path, documents)
    _write_json(recall_results_path, recall_results)

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_tau_revision_recall_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "base_root": str(revision_root),
        "base_receipt": str(base_receipt_path),
        "base_receipt_sha256": base_receipt_sha256,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "recall_index": str(recall_index_path),
        "recall_results": str(recall_results_path),
        "conditions": list(CONDITIONS),
        "errors": errors,
        "counts": {
            "base_revision_cases": base_receipt.get("counts", {}).get("revision_cases_written")
            if isinstance(base_receipt.get("counts"), dict)
            else None,
            "revision_documents": len(documents),
            "revision_documents_per_condition": documents_per_condition,
            "revision_recall_queries": len(recall_queries),
            "revision_recall_hits": recall_hits,
            "write_violations": write_violations,
        },
        "checks": {
            "base_action_linked_revision_passed": base_receipt.get("status") == "PASS_LIVE_TAU_PCTOM_ACTION_LINKED_REVISION",
            "base_receipt_hash_recomputed": isinstance(base_receipt_sha256, str) and base_receipt_sha256.startswith("sha256:"),
            "conditions_represented": all(documents_per_condition[condition] >= 1 for condition in CONDITIONS),
            "prior_and_posterior_distinguished": prior_posterior_distinguished,
            "synthetic_literal_boundary_preserved": synthetic_boundary_preserved,
            "human_content_judgment_absent": True,
            "unsupported_writes_absent": write_violations == 0,
        },
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "live_tau_originated_revision_artifacts_consumed": True,
        "deterministic_artifact_recall": True,
        "live_memory_recall_performed": False,
        "deterministic_simulator_corpus_fixture_backed": True,
        "human_content_judgment_required": False,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "claims": {
            "proves": [
                "action-linked revisions can be found by deterministic local recall queries over live-originated revision artifacts",
                "prior and posterior distributions are distinguishable in recalled revision documents",
                "synthetic counterfactual branches remain excluded from literal history in recalled revision context",
                "canonical, identity, and source-memory writes remain absent",
            ]
            if status == PASS_STATUS
            else [
                "the revision recall bridge failed closed before claiming longitudinal recall-after-revision evidence",
            ],
            "does_not_prove": [
                "live Memory recall after revision",
                "held-out statistical prediction benefit",
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
    parser.add_argument("--revision-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt = run_bridge(args.revision_root, args.output_root, args.receipt_out)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
