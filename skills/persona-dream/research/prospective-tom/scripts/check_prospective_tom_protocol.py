#!/usr/bin/env python3
"""Check PCTOM-R Gate 0 lineage through a sealed ToM prediction.

This checker is intentionally deterministic and local. It does not call Tau,
Memory, an LLM, a VLM, or any media provider. Its claim surface is limited to
the fixture case files supplied on disk.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PCTOM_GATE0_LINEAGE"
BLOCKED_STATUS = "BLOCKED_PCTOM_GATE0_LINEAGE"
REQUIRED_CASE_FILES = {
    "recall_receipts": "recall_receipts.json",
    "normalized_residue": "normalized_residue.json",
    "dream_branches": "dream_branches.json",
    "tom_prediction_commitment": "tom_prediction_commitment.json",
}
EPSILON = 1e-6


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path, errors: list[str]) -> Any:
    if not path.exists():
        errors.append(f"missing_file:{path.name}")
        return None
    if path.is_symlink():
        errors.append(f"symlink_file:{path.name}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"malformed_json:{path.name}:{exc}")
        return None


def _as_pair(value: Any, prefix: str, errors: list[str]) -> tuple[str, str] | None:
    if not isinstance(value, dict):
        errors.append(f"{prefix}_not_object")
        return None
    scope = value.get("scope")
    source_id = value.get("source_id")
    if not isinstance(scope, str) or not scope:
        errors.append(f"{prefix}_missing_scope")
        return None
    if not isinstance(source_id, str) or not source_id:
        errors.append(f"{prefix}_missing_source_id")
        return None
    return scope, source_id


def _check_distribution(entries: Any, prefix: str, errors: list[str]) -> None:
    if not isinstance(entries, list) or not entries:
        errors.append(f"{prefix}_distribution_not_nonempty_list")
        return
    total = 0.0
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"{prefix}_distribution_{idx}_not_object")
            continue
        probability = entry.get("probability")
        if not isinstance(probability, (int, float)) or isinstance(probability, bool):
            errors.append(f"{prefix}_distribution_{idx}_invalid_probability:{probability}")
            continue
        if probability < 0 or probability > 1:
            errors.append(f"{prefix}_distribution_{idx}_probability_out_of_range:{probability}")
        total += float(probability)
    if abs(total - 1.0) > EPSILON:
        errors.append(f"{prefix}_distribution_sum:{total:.6f}")


def _check_case(case_root: Path) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    paths = {name: case_root / filename for name, filename in REQUIRED_CASE_FILES.items()}
    recall_receipts = _load_json(paths["recall_receipts"], errors)
    normalized_residue = _load_json(paths["normalized_residue"], errors)
    dream_branches = _load_json(paths["dream_branches"], errors)
    commitment = _load_json(paths["tom_prediction_commitment"], errors)

    recall_index: dict[int, dict[str, Any]] = {}
    accepted_pairs: dict[tuple[int, str, str], int] = {}
    if isinstance(recall_receipts, list):
        for idx, receipt in enumerate(recall_receipts):
            if not isinstance(receipt, dict):
                errors.append(f"recall_receipt_{idx}_not_object")
                continue
            recall_index[idx] = receipt
            for key in ("query", "scope", "accepted_source_ids", "accepted_source_ids_sha256"):
                if key not in receipt:
                    errors.append(f"recall_receipt_{idx}_missing:{key}")
            if receipt.get("status") not in {None, "ok"}:
                errors.append(f"recall_receipt_{idx}_status_not_ok:{receipt.get('status')}")
            scope = receipt.get("scope")
            source_ids = receipt.get("accepted_source_ids")
            if not isinstance(scope, str) or not scope:
                errors.append(f"recall_receipt_{idx}_invalid_scope")
                scope = ""
            if not isinstance(source_ids, list):
                errors.append(f"recall_receipt_{idx}_accepted_source_ids_not_list")
                source_ids = []
            else:
                bad_ids = [source_id for source_id in source_ids if not isinstance(source_id, str) or not source_id]
                if bad_ids:
                    errors.append(f"recall_receipt_{idx}_invalid_accepted_source_id_count:{len(bad_ids)}")
            expected_hash = _stable_json_sha256(source_ids)
            if receipt.get("accepted_source_ids_sha256") != expected_hash:
                errors.append(f"recall_receipt_{idx}_accepted_source_ids_sha256_mismatch")
            for order, source_id in enumerate(source_ids):
                if isinstance(source_id, str) and source_id:
                    accepted_pairs[(idx, scope, source_id)] = order
    else:
        errors.append("recall_receipts_not_list")

    residue_pairs: set[tuple[str, str]] = set()
    residue_lineage_links: list[dict[str, Any]] = []
    if isinstance(normalized_residue, list):
        for idx, item in enumerate(normalized_residue):
            if not isinstance(item, dict):
                errors.append(f"residue_{idx}_not_object")
                continue
            scope = item.get("scope")
            source_id = item.get("source_id")
            text = item.get("text")
            query_receipt_index = item.get("query_receipt_index")
            if not isinstance(scope, str) or not scope:
                errors.append(f"residue_{idx}_missing_scope")
                continue
            if not isinstance(source_id, str) or not source_id:
                errors.append(f"residue_{idx}_missing_source_id")
                continue
            if not isinstance(text, str) or not text.strip():
                errors.append(f"residue_{idx}_missing_text")
            if item.get("synthetic") is not False:
                errors.append(f"residue_{idx}_synthetic_not_false")
            if not isinstance(query_receipt_index, int):
                errors.append(f"residue_{idx}_missing_query_receipt_index")
                continue
            receipt = recall_index.get(query_receipt_index)
            if not receipt:
                errors.append(f"residue_{idx}_query_receipt_missing:{query_receipt_index}")
                continue
            if receipt.get("scope") != scope:
                errors.append(f"residue_{idx}_scope_not_receipt_scope:{scope}:{receipt.get('scope')}")
            accepted_order = accepted_pairs.get((query_receipt_index, scope, source_id))
            if accepted_order is None:
                errors.append(f"residue_{idx}_source_not_accepted:{scope}:{source_id}")
                continue
            pair = (scope, source_id)
            if pair in residue_pairs:
                errors.append(f"duplicate_residue_pair:{scope}:{source_id}")
            residue_pairs.add(pair)
            residue_lineage_links.append({
                "residue_index": idx,
                "query_receipt_index": query_receipt_index,
                "accepted_order": accepted_order,
                "scope": scope,
                "source_id": source_id,
                "accepted_source_ids_sha256": receipt.get("accepted_source_ids_sha256"),
            })
    else:
        errors.append("normalized_residue_not_list")

    branch_ids: set[str] = set()
    branch_lineage_links: list[dict[str, Any]] = []
    if isinstance(dream_branches, list):
        for idx, branch in enumerate(dream_branches):
            if not isinstance(branch, dict):
                errors.append(f"dream_branch_{idx}_not_object")
                continue
            branch_id = branch.get("branch_id")
            if not isinstance(branch_id, str) or not branch_id:
                errors.append(f"dream_branch_{idx}_missing_branch_id")
                continue
            if branch_id in branch_ids:
                errors.append(f"duplicate_dream_branch:{branch_id}")
            branch_ids.add(branch_id)
            branch_type = branch.get("branch_type")
            counterfactual = branch.get("counterfactual")
            if branch_type not in {"factual", "counterfactual"}:
                errors.append(f"dream_branch_{idx}_invalid_branch_type:{branch_type}")
            if not isinstance(counterfactual, bool):
                errors.append(f"dream_branch_{idx}_counterfactual_not_bool")
            if branch_type == "counterfactual" and counterfactual is not True:
                errors.append(f"dream_branch_{idx}_counterfactual_flag_false")
            if branch_type == "factual" and counterfactual is not False:
                errors.append(f"dream_branch_{idx}_factual_counterfactual_flag_true")
            if branch_type == "counterfactual" and not branch.get("intervention_id"):
                errors.append(f"dream_branch_{idx}_missing_intervention_id")
            refs = branch.get("source_residue_refs")
            if not isinstance(refs, list) or not refs:
                errors.append(f"dream_branch_{idx}_missing_source_residue_refs")
                continue
            for ref_idx, ref in enumerate(refs):
                pair = _as_pair(ref, f"dream_branch_{idx}_source_ref_{ref_idx}", errors)
                if pair and pair not in residue_pairs:
                    errors.append(f"dream_branch_{idx}_unresolved_residue_ref:{pair[0]}:{pair[1]}")
                if pair:
                    branch_lineage_links.append({
                        "branch_id": branch_id,
                        "scope": pair[0],
                        "source_id": pair[1],
                    })
    else:
        errors.append("dream_branches_not_list")

    prediction_evidence_links: list[dict[str, Any]] = []
    prediction_branch_links: list[str] = []
    prediction_payload_hash_valid = False
    if isinstance(commitment, dict):
        for key in (
            "prediction_id",
            "episode_id",
            "condition",
            "sealed_at",
            "outcome_visible",
            "prediction_payload_sha256",
            "prediction_payload",
        ):
            if key not in commitment:
                errors.append(f"commitment_missing:{key}")
        if commitment.get("outcome_visible") is not False:
            errors.append("commitment_outcome_visible_not_false")
        payload = commitment.get("prediction_payload")
        expected_payload_hash = _stable_json_sha256(payload)
        if commitment.get("prediction_payload_sha256") != expected_payload_hash:
            errors.append("commitment_prediction_payload_sha256_mismatch")
        else:
            prediction_payload_hash_valid = True
        if isinstance(payload, dict):
            refs = payload.get("evidence_residue_refs")
            if not isinstance(refs, list) or not refs:
                errors.append("prediction_payload_missing_evidence_residue_refs")
            else:
                for ref_idx, ref in enumerate(refs):
                    pair = _as_pair(ref, f"prediction_evidence_ref_{ref_idx}", errors)
                    if pair and pair not in residue_pairs:
                        errors.append(f"prediction_unresolved_evidence_ref:{pair[0]}:{pair[1]}")
                    if pair:
                        prediction_evidence_links.append({
                            "scope": pair[0],
                            "source_id": pair[1],
                        })
            branch_refs = payload.get("dream_branch_refs")
            if not isinstance(branch_refs, list) or not branch_refs:
                errors.append("prediction_payload_missing_dream_branch_refs")
            else:
                for branch_ref in branch_refs:
                    if not isinstance(branch_ref, str) or not branch_ref:
                        errors.append("prediction_invalid_dream_branch_ref")
                    elif branch_ref not in branch_ids:
                        errors.append(f"prediction_unresolved_dream_branch_ref:{branch_ref}")
                    else:
                        prediction_branch_links.append(branch_ref)
            belief_distributions = payload.get("belief_distributions")
            if not isinstance(belief_distributions, list) or not belief_distributions:
                errors.append("prediction_payload_missing_belief_distributions")
            else:
                for idx, belief in enumerate(belief_distributions):
                    if not isinstance(belief, dict):
                        errors.append(f"belief_{idx}_not_object")
                        continue
                    _check_distribution(belief.get("distribution"), f"belief_{idx}", errors)
                    for ref_idx, ref in enumerate(belief.get("evidence_refs") or []):
                        pair = _as_pair(ref, f"belief_{idx}_evidence_ref_{ref_idx}", errors)
                        if pair and pair not in residue_pairs:
                            errors.append(f"belief_{idx}_unresolved_evidence_ref:{pair[0]}:{pair[1]}")
            _check_distribution(payload.get("action_distribution"), "action", errors)
        else:
            errors.append("commitment_prediction_payload_not_object")
    else:
        errors.append("tom_prediction_commitment_not_object")

    derived = {
        "recall_receipt_count": len(recall_index),
        "accepted_source_id_count": len(accepted_pairs),
        "residue_count": len(residue_pairs),
        "dream_branch_count": len(branch_ids),
        "prediction_evidence_link_count": len(prediction_evidence_links),
        "prediction_branch_link_count": len(prediction_branch_links),
        "prediction_payload_hash_valid": prediction_payload_hash_valid,
        "residue_lineage_links": residue_lineage_links,
        "branch_lineage_links": branch_lineage_links,
        "prediction_evidence_links": prediction_evidence_links,
        "prediction_branch_links": prediction_branch_links,
    }
    return errors, derived


def build_receipt(case_root: Path, receipt_out: Path) -> dict[str, Any]:
    case_root = case_root.resolve()
    receipt_out = receipt_out.resolve()
    errors, derived = _check_case(case_root)
    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.gate0_lineage_check_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "case_root": str(case_root),
        "receipt_path": str(receipt_out),
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "provider_call_attempts": 0,
        "memory_write_attempts": 0,
        "tau_call_attempts": 0,
        "errors": errors,
        "counts": {
            "recall_receipts": derived["recall_receipt_count"],
            "accepted_source_ids": derived["accepted_source_id_count"],
            "normalized_residue": derived["residue_count"],
            "dream_branches": derived["dream_branch_count"],
            "prediction_evidence_links": derived["prediction_evidence_link_count"],
            "prediction_branch_links": derived["prediction_branch_link_count"],
        },
        "lineage_checks": {
            "accepted_source_id_hashes_recomputed": not any(
                error.endswith("_accepted_source_ids_sha256_mismatch") for error in errors
            ),
            "residue_links_to_recall_receipts": not any(
                "residue_" in error and ("source_not_accepted" in error or "query_receipt" in error)
                for error in errors
            ),
            "dream_branches_link_to_residue": not any("dream_branch_" in error and "residue_ref" in error for error in errors),
            "prediction_links_to_branches": not any("prediction_unresolved_dream_branch_ref" in error for error in errors),
            "prediction_links_to_residue": not any(
                "prediction_unresolved_evidence_ref" in error or "belief_" in error and "unresolved_evidence_ref" in error
                for error in errors
            ),
            "prediction_payload_hash_recomputed": derived["prediction_payload_hash_valid"],
            "prediction_sealed_before_reveal": "commitment_outcome_visible_not_false" not in errors,
        },
        "lineage": {
            "residue_lineage_links": derived["residue_lineage_links"],
            "branch_lineage_links": derived["branch_lineage_links"],
            "prediction_evidence_links": derived["prediction_evidence_links"],
            "prediction_branch_links": derived["prediction_branch_links"],
        },
        "claims": {
            "proves": [
                "fixture case files mechanically preserve recall receipt to accepted source id to normalized residue to dream branch to sealed prediction lineage",
                "accepted source-id lists and prediction payload are hash-bound in the fixture case",
                "the checker fails closed for unresolved or tampered local fixture links",
            ]
            if status == PASS_STATUS
            else [
                "the checker produced a fail-closed receipt for a malformed or incomplete local fixture case",
            ],
            "does_not_prove": [
                "live Tau execution",
                "live Memory recall",
                "semantic dream quality",
                "future prediction accuracy",
                "outcome reveal scoring",
                "belief revision",
                "pipeline reliability under repeated faults",
                "paid provider execution",
                "production Phase 01-16 runtime execution",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    receipt = build_receipt(args.case_root, args.receipt_out)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
