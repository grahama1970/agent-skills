#!/usr/bin/env python3
"""Check PCTOM-R causal identifiability over sealed live-originated artifacts.

This is a derived checker: it consumes already-written commitments, outcomes,
scoring receipts, and Gate 6 action selections. It performs no new Tau, Memory,
provider, canonical-memory, identity, or source-memory writes.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import statistics
import time
from pathlib import Path
from typing import Any


CONDITIONS = ("M", "R", "D", "CD")
ACTION_VOCABULARY = (
    "ASK_CLARIFYING_QUESTION",
    "WAIT",
    "DISCLOSE_INFORMATION",
    "OFFER_COOPERATION",
    "SET_BOUNDARY",
    "ACT_INDEPENDENTLY",
    "ABSTAIN",
)
PASS_STATUS = "PASS_PCTOM_CAUSAL_IDENTIFIABILITY_GATE"
BLOCKED_STATUS = "BLOCKED_PCTOM_CAUSAL_IDENTIFIABILITY_GATE"
LINEAGE_PASS_STATUS = "PASS_PCTOM_END_TO_END_LINEAGE"
LINEAGE_BLOCKED_STATUS = "BLOCKED_PCTOM_END_TO_END_LINEAGE"
SENSITIVITY_PASS_STATUS = "PASS_PCTOM_ORACLE_POLICY_SENSITIVITY"
SENSITIVITY_BLOCKED_STATUS = "BLOCKED_PCTOM_ORACLE_POLICY_SENSITIVITY"
RAW_SOURCE_ID_KEYS = ("accepted_raw_source_id", "accepted_source_id", "raw_source_id")
RAW_SOURCE_HASH_KEYS = (
    "accepted_raw_source_sha256",
    "accepted_source_sha256",
    "raw_source_sha256",
    "source_sha256",
    "content_sha256",
)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str | None:
    if not path.exists() or path.is_symlink():
        return None
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


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


def _counterpart_to_agent_action(counterpart_action: str) -> str:
    action = counterpart_action.upper()
    if "ASKS_TO_WAIT" in action or "QUIET_REVIEW" in action:
        return "WAIT"
    if "OFFERS_COOPERATION" in action:
        return "OFFER_COOPERATION"
    if "HINTS_CONSTRAINT" in action:
        return "ASK_CLARIFYING_QUESTION"
    if "DISCLOSES_AUTHORITY_CONSTRAINT" in action:
        return "DISCLOSE_INFORMATION"
    if "SETS_BOUNDARY" in action:
        return "SET_BOUNDARY"
    if action == "UNKNOWN":
        return "ABSTAIN"
    return "ASK_CLARIFYING_QUESTION"


def _action_components(action: str, oracle_action: str) -> dict[str, float]:
    if action == oracle_action:
        return {
            "expected_task_reward": 0.8,
            "expected_social_cost": 0.1,
            "expected_information_gain": 0.3,
        }
    if action == "ASK_CLARIFYING_QUESTION":
        return {
            "expected_task_reward": 0.5,
            "expected_social_cost": 0.05,
            "expected_information_gain": 0.3,
        }
    if action == "ABSTAIN":
        return {
            "expected_task_reward": 0.2,
            "expected_social_cost": 0.0,
            "expected_information_gain": 0.1,
        }
    if action == "WAIT":
        return {
            "expected_task_reward": 0.45,
            "expected_social_cost": 0.1,
            "expected_information_gain": 0.1,
        }
    return {
        "expected_task_reward": 0.35,
        "expected_social_cost": 0.25,
        "expected_information_gain": 0.05,
    }


def _with_utility(action: str, oracle_action: str) -> dict[str, Any]:
    option: dict[str, Any] = {
        "action": action,
        "policy_compliant": True,
        "policy_basis": "deterministic_simulator_policy.v1",
    }
    option.update(_action_components(action, oracle_action))
    option["expected_utility"] = (
        option["expected_task_reward"] + option["expected_information_gain"] - option["expected_social_cost"]
    )
    return option


def _distribution(commitment_bundle: dict[str, Any], errors: list[str], label: str) -> list[tuple[str, float]]:
    commitments = commitment_bundle.get("commitments")
    if not isinstance(commitments, list) or len(commitments) != 1 or not isinstance(commitments[0], dict):
        errors.append(f"{label}_expected_one_commitment")
        return []
    payload = commitments[0].get("prediction_payload")
    if not isinstance(payload, dict):
        errors.append(f"{label}_prediction_payload_missing")
        return []
    distribution = payload.get("predicted_next_action_distribution")
    if not isinstance(distribution, list) or not distribution:
        errors.append(f"{label}_predicted_next_action_distribution_missing")
        return []
    rows: list[tuple[str, float]] = []
    for idx, item in enumerate(distribution):
        if not isinstance(item, dict):
            errors.append(f"{label}_distribution_{idx}_not_object")
            continue
        value = item.get("value")
        probability = item.get("probability")
        if not isinstance(value, str) or not isinstance(probability, (int, float)) or isinstance(probability, bool):
            errors.append(f"{label}_distribution_{idx}_invalid:{item}")
            continue
        rows.append((value, float(probability)))
    if not rows:
        errors.append(f"{label}_distribution_empty_after_validation")
    return rows


def _top_counterpart_action(distribution: list[tuple[str, float]]) -> tuple[str, float]:
    if not distribution:
        return "UNKNOWN", 1.0
    return max(distribution, key=lambda item: (item[1], item[0]))


def _anti_oracle_counterpart_action(
    distribution: list[tuple[str, float]],
    *,
    actual_next_action: str,
    oracle_agent_action: str,
) -> tuple[str, str]:
    for value, _probability in sorted(distribution, key=lambda item: (item[1], item[0])):
        if value == actual_next_action:
            continue
        candidate_agent_action = _counterpart_to_agent_action(value)
        if candidate_agent_action != oracle_agent_action:
            return value, "lowest_probability_non_actual_with_distinct_agent_action"
    for value, _probability in sorted(distribution, key=lambda item: (item[1], item[0])):
        if value != actual_next_action:
            return value, "lowest_probability_non_actual_fallback_same_agent_action"
    return "UNKNOWN", "unknown_fallback_no_non_actual_distribution_item"


def _projection(counterpart_action: str, *, actual_next_action: str) -> dict[str, Any]:
    oracle_agent_action = _counterpart_to_agent_action(actual_next_action)
    selected_agent_action = _counterpart_to_agent_action(counterpart_action)
    option_by_action = {action: _with_utility(action, oracle_agent_action) for action in ACTION_VOCABULARY}
    selected_utility = float(option_by_action[selected_agent_action]["expected_utility"])
    oracle_utility = float(option_by_action[oracle_agent_action]["expected_utility"])
    regret = max(0.0, oracle_utility - selected_utility)
    if abs(regret) < 1e-9:
        regret = 0.0
    return {
        "counterpart_action": counterpart_action,
        "selected_action": selected_agent_action,
        "expected_utility": selected_utility,
        "planning_regret": regret,
        "oracle_action": oracle_agent_action,
        "oracle_expected_utility": oracle_utility,
    }


def _commitment_payload(commitment_bundle: dict[str, Any]) -> dict[str, Any]:
    commitments = commitment_bundle.get("commitments")
    if not isinstance(commitments, list) or not commitments or not isinstance(commitments[0], dict):
        return {}
    payload = commitments[0].get("prediction_payload")
    return payload if isinstance(payload, dict) else {}


def _has_raw_source_id(ref: dict[str, Any]) -> bool:
    return any(isinstance(ref.get(key), str) and bool(ref.get(key)) for key in RAW_SOURCE_ID_KEYS)


def _has_raw_source_hash(ref: dict[str, Any]) -> bool:
    return any(isinstance(ref.get(key), str) and str(ref.get(key)).startswith("sha256:") for key in RAW_SOURCE_HASH_KEYS)


def _lineage_case(
    *,
    episode_id: str,
    condition: str,
    commitment_bundle_path: Path,
    commitment_bundle: dict[str, Any],
    outcome_path: Path,
    scoring_receipt_path: Path,
    action_selection_path: Path,
    gate4_receipt_path: Path,
    gate6_receipt_path: Path,
) -> dict[str, Any]:
    payload = _commitment_payload(commitment_bundle)
    evidence_refs = payload.get("evidence_refs")
    if not isinstance(evidence_refs, list):
        evidence_refs = []
    ref_results = []
    for idx, ref in enumerate(evidence_refs):
        ref_obj = ref if isinstance(ref, dict) else {}
        ref_results.append(
            {
                "index": idx,
                "scope": ref_obj.get("scope"),
                "source_id": ref_obj.get("source_id"),
                "has_accepted_raw_source_id": _has_raw_source_id(ref_obj),
                "has_raw_source_content_hash": _has_raw_source_hash(ref_obj),
            }
        )
    all_refs_have_raw = bool(ref_results) and all(
        row["has_accepted_raw_source_id"] and row["has_raw_source_content_hash"] for row in ref_results
    )
    required_paths = {
        "commitment_bundle": commitment_bundle_path,
        "outcome_reveal": outcome_path,
        "scoring_receipt": scoring_receipt_path,
        "action_selection": action_selection_path,
        "gate4_commitment_check_receipt": gate4_receipt_path,
        "gate6_action_selection_receipt": gate6_receipt_path,
    }
    path_hashes = {name: _file_sha256(path) for name, path in required_paths.items()}
    all_required_hashes = all(value is not None for value in path_hashes.values())
    return {
        "episode_id": episode_id,
        "condition": condition,
        "prediction_id": commitment_bundle.get("commitments", [{}])[0].get("prediction_id")
        if isinstance(commitment_bundle.get("commitments"), list)
        else None,
        "outcome_visible_at_commitment": payload.get("outcome_visible"),
        "required_artifact_hashes": path_hashes,
        "evidence_ref_count": len(ref_results),
        "evidence_refs": ref_results,
        "all_required_artifacts_hash_bound": all_required_hashes,
        "all_evidence_refs_have_raw_source_id_and_hash": all_refs_have_raw,
        "lineage_complete": all_required_hashes and all_refs_have_raw and payload.get("outcome_visible") is False,
    }


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _load_case_paths(
    *,
    condition_root: Path,
    action_root: Path,
    episode_id: str,
    condition: str,
) -> dict[str, Path]:
    return {
        "commitment_bundle": condition_root
        / "artifacts"
        / "cases"
        / episode_id
        / condition
        / "tom_prediction_commitment_bundle.json",
        "outcome_reveal": condition_root / "artifacts" / "cases" / episode_id / condition / "tom_outcome_reveal.json",
        "scoring_receipt": condition_root
        / "receipts"
        / "cases"
        / episode_id
        / condition
        / "gate5_scoring_receipt.json",
        "gate4_receipt": condition_root
        / "receipts"
        / "cases"
        / episode_id
        / condition
        / "gate4_commitment_check_receipt.json",
        "action_selection": action_root / "artifacts" / "cases" / episode_id / condition / "action_selection.json",
        "gate6_receipt": action_root
        / "receipts"
        / "cases"
        / episode_id
        / condition
        / "gate6_action_selection_receipt.json",
    }


def _build_rows(
    *,
    condition_root: Path,
    action_root: Path,
    action_index: list[dict[str, Any]],
    errors: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sensitivity_rows: list[dict[str, Any]] = []
    lineage_rows: list[dict[str, Any]] = []
    for idx, index_row in enumerate(action_index):
        if not isinstance(index_row, dict):
            errors.append(f"action_index_{idx}_not_object")
            continue
        episode_id = index_row.get("episode_id")
        condition = index_row.get("condition")
        if not isinstance(episode_id, str) or condition not in CONDITIONS:
            errors.append(f"action_index_{idx}_invalid_identity:{episode_id}:{condition}")
            continue
        paths = _load_case_paths(
            condition_root=condition_root,
            action_root=action_root,
            episode_id=episode_id,
            condition=condition,
        )
        commitment_bundle = _load_json(paths["commitment_bundle"], errors, f"commitment_bundle_{episode_id}_{condition}")
        outcome = _load_json(paths["outcome_reveal"], errors, f"outcome_{episode_id}_{condition}")
        action_selection = _load_json(paths["action_selection"], errors, f"action_selection_{episode_id}_{condition}")
        scoring_receipt = _load_json(paths["scoring_receipt"], errors, f"scoring_receipt_{episode_id}_{condition}")
        if not isinstance(commitment_bundle, dict):
            commitment_bundle = {}
        if not isinstance(outcome, dict):
            outcome = {}
        if not isinstance(action_selection, dict):
            action_selection = {}
        if not isinstance(scoring_receipt, dict):
            scoring_receipt = {}
        actual_next_action = outcome.get("actual_next_action")
        if not isinstance(actual_next_action, str) or not actual_next_action:
            errors.append(f"actual_next_action_missing:{episode_id}:{condition}")
            actual_next_action = "UNKNOWN"
        distribution = _distribution(commitment_bundle, errors, f"{episode_id}_{condition}")
        actual_counterpart_action, actual_probability = _top_counterpart_action(distribution)
        oracle_agent_action = _counterpart_to_agent_action(actual_next_action)
        anti_counterpart_action, anti_rule = _anti_oracle_counterpart_action(
            distribution,
            actual_next_action=actual_next_action,
            oracle_agent_action=oracle_agent_action,
        )
        actual_projection = _projection(actual_counterpart_action, actual_next_action=actual_next_action)
        oracle_projection = _projection(actual_next_action, actual_next_action=actual_next_action)
        anti_projection = _projection(anti_counterpart_action, actual_next_action=actual_next_action)
        selected_action = action_selection.get("selected_action")
        if selected_action != actual_projection["selected_action"]:
            errors.append(
                "actual_projection_selected_action_mismatch:"
                f"{episode_id}:{condition}:{selected_action}:{actual_projection['selected_action']}"
            )
        supplied_regret = action_selection.get("planning_regret")
        if isinstance(supplied_regret, (int, float)) and not isinstance(supplied_regret, bool):
            if abs(float(supplied_regret) - actual_projection["planning_regret"]) > 1e-6:
                errors.append(
                    "actual_projection_regret_mismatch:"
                    f"{episode_id}:{condition}:{supplied_regret}:{actual_projection['planning_regret']}"
                )
        sensitivity_rows.append(
            {
                "episode_id": episode_id,
                "condition": condition,
                "prediction_id": action_selection.get("prediction_id"),
                "status": "PASS_ORACLE_POLICY_SENSITIVITY_ROW",
                "actual_next_action": actual_next_action,
                "committed_top_counterpart_action": actual_counterpart_action,
                "committed_top_counterpart_probability": actual_probability,
                "anti_oracle_counterpart_action": anti_counterpart_action,
                "anti_oracle_selection_rule": anti_rule,
                "actual_committed_policy": actual_projection,
                "oracle_aligned_policy": oracle_projection,
                "anti_oracle_policy": anti_projection,
                "actual_to_oracle_regret_delta": oracle_projection["planning_regret"]
                - actual_projection["planning_regret"],
                "anti_oracle_minus_actual_regret_delta": anti_projection["planning_regret"]
                - actual_projection["planning_regret"],
                "actual_to_oracle_action_switched": actual_projection["selected_action"]
                != oracle_projection["selected_action"],
                "actual_to_anti_oracle_action_switched": actual_projection["selected_action"]
                != anti_projection["selected_action"],
                "commitment_bundle_sha256": _file_sha256(paths["commitment_bundle"]),
                "outcome_reveal_sha256": _file_sha256(paths["outcome_reveal"]),
                "scoring_receipt_sha256": _file_sha256(paths["scoring_receipt"]),
                "action_selection_sha256": _file_sha256(paths["action_selection"]),
                "scoring_receipt_status": scoring_receipt.get("status"),
                "outcome_visible_at_commitment": _commitment_payload(commitment_bundle).get("outcome_visible"),
            }
        )
        lineage_rows.append(
            _lineage_case(
                episode_id=episode_id,
                condition=condition,
                commitment_bundle_path=paths["commitment_bundle"],
                commitment_bundle=commitment_bundle,
                outcome_path=paths["outcome_reveal"],
                scoring_receipt_path=paths["scoring_receipt"],
                action_selection_path=paths["action_selection"],
                gate4_receipt_path=paths["gate4_receipt"],
                gate6_receipt_path=paths["gate6_receipt"],
            )
        )
    return sensitivity_rows, lineage_rows


def _summarize_sensitivity(rows: list[dict[str, Any]]) -> dict[str, Any]:
    oracle_deltas = [float(row["actual_to_oracle_regret_delta"]) for row in rows]
    anti_deltas = [float(row["anti_oracle_minus_actual_regret_delta"]) for row in rows]
    return {
        "rows": len(rows),
        "conditions": dict(collections.Counter(str(row["condition"]) for row in rows)),
        "actual_to_oracle_action_switch_count": sum(1 for row in rows if row["actual_to_oracle_action_switched"]),
        "actual_to_anti_oracle_action_switch_count": sum(
            1 for row in rows if row["actual_to_anti_oracle_action_switched"]
        ),
        "actual_to_oracle_regret_delta_mean": _mean(oracle_deltas),
        "anti_oracle_minus_actual_regret_delta_mean": _mean(anti_deltas),
        "oracle_improves_regret_count": sum(1 for value in oracle_deltas if value < 0),
        "anti_oracle_worsens_regret_count": sum(1 for value in anti_deltas if value > 0),
        "actual_selected_actions": dict(
            collections.Counter(str(row["actual_committed_policy"]["selected_action"]) for row in rows)
        ),
        "oracle_selected_actions": dict(
            collections.Counter(str(row["oracle_aligned_policy"]["selected_action"]) for row in rows)
        ),
        "anti_oracle_selected_actions": dict(
            collections.Counter(str(row["anti_oracle_policy"]["selected_action"]) for row in rows)
        ),
    }


def _summarize_lineage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [row for row in rows if row["lineage_complete"]]
    total_refs = sum(int(row["evidence_ref_count"]) for row in rows)
    refs_with_raw_id = sum(
        1
        for row in rows
        for ref in row["evidence_refs"]
        if ref["has_accepted_raw_source_id"]
    )
    refs_with_hash = sum(
        1
        for row in rows
        for ref in row["evidence_refs"]
        if ref["has_raw_source_content_hash"]
    )
    completeness = 1.0 if rows and len(complete) == len(rows) else (len(complete) / len(rows) if rows else 0.0)
    return {
        "rows": len(rows),
        "complete_rows": len(complete),
        "lineage_completeness": completeness,
        "total_evidence_refs": total_refs,
        "evidence_refs_with_accepted_raw_source_id": refs_with_raw_id,
        "evidence_refs_with_raw_source_content_hash": refs_with_hash,
        "incomplete_rows": [
            {
                "episode_id": row["episode_id"],
                "condition": row["condition"],
                "evidence_ref_count": row["evidence_ref_count"],
                "all_required_artifacts_hash_bound": row["all_required_artifacts_hash_bound"],
                "all_evidence_refs_have_raw_source_id_and_hash": row[
                    "all_evidence_refs_have_raw_source_id_and_hash"
                ],
                "outcome_visible_at_commitment": row["outcome_visible_at_commitment"],
            }
            for row in rows
            if not row["lineage_complete"]
        ],
    }


def run_causal_identifiability_gate(
    *,
    condition_root: Path,
    action_root: Path,
    output_root: Path,
    receipt_out: Path,
) -> dict[str, Any]:
    started = time.monotonic()
    condition_root = condition_root.resolve()
    action_root = action_root.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    errors: list[str] = []

    action_receipt_path = action_root / "live_tau_condition_action_selection_receipt.v1.json"
    condition_receipt_path = condition_root / "live_tau_condition_comparison_receipt.v1.json"
    action_receipt = _load_json(action_receipt_path, errors, "action_receipt")
    condition_receipt = _load_json(condition_receipt_path, errors, "condition_receipt")
    if not isinstance(action_receipt, dict):
        action_receipt = {}
    if not isinstance(condition_receipt, dict):
        condition_receipt = {}
    action_index_path = Path(str(action_receipt.get("decision_index", "")))
    if not action_index_path.is_absolute():
        action_index_path = action_root / "artifacts" / "live_condition_action_decisions.json"
    action_index = _load_json(action_index_path, errors, "action_index")
    if not isinstance(action_index, list):
        errors.append("action_index_not_list")
        action_index = []

    if action_receipt.get("status") != "PASS_LIVE_TAU_PCTOM_CONDITION_ACTION_SELECTION":
        errors.append(f"action_receipt_status_not_pass:{action_receipt.get('status')}")
    if condition_receipt.get("status") != "PASS_LIVE_TAU_PCTOM_CONDITION_COMPARISON":
        errors.append(f"condition_receipt_status_not_pass:{condition_receipt.get('status')}")
    if action_receipt.get("mocked") is not False or action_receipt.get("live") is not True:
        errors.append("action_receipt_mocked_live_flags_mismatch")
    if condition_receipt.get("mocked") is not False or condition_receipt.get("live") is not True:
        errors.append("condition_receipt_mocked_live_flags_mismatch")

    sensitivity_rows, lineage_rows = _build_rows(
        condition_root=condition_root,
        action_root=action_root,
        action_index=action_index,
        errors=errors,
    )
    sensitivity_summary = _summarize_sensitivity(sensitivity_rows)
    lineage_summary = _summarize_lineage(lineage_rows)
    sensitivity_errors = [error for error in errors if "lineage" not in error]
    sensitivity_status = SENSITIVITY_PASS_STATUS if not sensitivity_errors and sensitivity_rows else SENSITIVITY_BLOCKED_STATUS
    lineage_status = (
        LINEAGE_PASS_STATUS
        if lineage_rows and lineage_summary["lineage_completeness"] == 1.0
        else LINEAGE_BLOCKED_STATUS
    )
    status = PASS_STATUS if sensitivity_status == SENSITIVITY_PASS_STATUS and lineage_status == LINEAGE_PASS_STATUS else BLOCKED_STATUS

    manifest_path = output_root / "pctom_causal_identifiability_manifest.json"
    lineage_receipt_path = output_root / "pctom_end_to_end_lineage_receipt.json"
    sensitivity_jsonl_path = output_root / "pctom_oracle_policy_sensitivity.jsonl"
    sensitivity_receipt_path = output_root / "pctom_oracle_policy_sensitivity_receipt.json"

    _write_jsonl(sensitivity_jsonl_path, sensitivity_rows)
    sensitivity_receipt = {
        "schema": "persona_dream.research.prospective_tom.oracle_policy_sensitivity_receipt.v1",
        "created_at": _now_iso(),
        "status": sensitivity_status,
        "sensitivity_rows_path": str(sensitivity_jsonl_path),
        "sensitivity_rows_sha256": _file_sha256(sensitivity_jsonl_path),
        "summary": sensitivity_summary,
        "errors": sensitivity_errors,
    }
    sensitivity_receipt["receipt_sha256"] = _stable_json_sha256(sensitivity_receipt)
    _write_json(sensitivity_receipt_path, sensitivity_receipt)

    lineage_receipt = {
        "schema": "persona_dream.research.prospective_tom.end_to_end_lineage_receipt.v1",
        "created_at": _now_iso(),
        "status": lineage_status,
        "lineage_rows": lineage_rows,
        "summary": lineage_summary,
        "stop_condition": "every_case_has_commitment_outcome_score_action_hashes_and_every_evidence_ref_has_accepted_raw_source_id_and_content_hash",
    }
    lineage_receipt["receipt_sha256"] = _stable_json_sha256(lineage_receipt)
    _write_json(lineage_receipt_path, lineage_receipt)

    manifest = {
        "schema": "persona_dream.research.prospective_tom.causal_identifiability_manifest.v1",
        "created_at": _now_iso(),
        "condition_root": str(condition_root),
        "action_root": str(action_root),
        "action_receipt_path": str(action_receipt_path),
        "action_receipt_sha256": _file_sha256(action_receipt_path),
        "condition_receipt_path": str(condition_receipt_path),
        "condition_receipt_sha256": _file_sha256(condition_receipt_path),
        "action_index_path": str(action_index_path),
        "action_index_sha256": _file_sha256(action_index_path),
        "artifacts": {
            "pctom_end_to_end_lineage_receipt": str(lineage_receipt_path),
            "pctom_oracle_policy_sensitivity": str(sensitivity_jsonl_path),
            "pctom_oracle_policy_sensitivity_receipt": str(sensitivity_receipt_path),
        },
        "fixed_policy": {
            "action_vocabulary": list(ACTION_VOCABULARY),
            "action_mapping": "run_pctom_causal_identifiability_gate._counterpart_to_agent_action",
            "utility_function": "expected_task_reward + expected_information_gain - expected_social_cost",
            "anti_oracle_selection_rule": "lowest probability non-actual committed action that maps to a distinct agent action when possible",
        },
    }
    manifest["manifest_sha256"] = _stable_json_sha256(manifest)
    _write_json(manifest_path, manifest)

    receipt = {
        "schema": "persona_dream.research.prospective_tom.causal_identifiability_gate_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "mocked": False,
        "live": True,
        "live_tau_originated_artifacts_consumed": True,
        "live_tau_reexecuted": False,
        "fixture_backed": False,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "manifest_path": str(manifest_path),
        "manifest_sha256": _file_sha256(manifest_path),
        "lineage_receipt_path": str(lineage_receipt_path),
        "lineage_receipt_sha256": _file_sha256(lineage_receipt_path),
        "sensitivity_rows_path": str(sensitivity_jsonl_path),
        "sensitivity_rows_sha256": _file_sha256(sensitivity_jsonl_path),
        "sensitivity_receipt_path": str(sensitivity_receipt_path),
        "sensitivity_receipt_sha256": _file_sha256(sensitivity_receipt_path),
        "counts": {
            "action_index_rows": len(action_index),
            "sensitivity_rows": len(sensitivity_rows),
            "lineage_rows": len(lineage_rows),
            "lineage_complete_rows": lineage_summary["complete_rows"],
            "actual_to_oracle_action_switch_count": sensitivity_summary["actual_to_oracle_action_switch_count"],
            "actual_to_anti_oracle_action_switch_count": sensitivity_summary[
                "actual_to_anti_oracle_action_switch_count"
            ],
        },
        "checks": {
            "action_receipt_passed": action_receipt.get("status") == "PASS_LIVE_TAU_PCTOM_CONDITION_ACTION_SELECTION",
            "condition_receipt_passed": condition_receipt.get("status")
            == "PASS_LIVE_TAU_PCTOM_CONDITION_COMPARISON",
            "fixed_action_policy_recomputed": sensitivity_status == SENSITIVITY_PASS_STATUS,
            "lineage_100_percent_complete": lineage_status == LINEAGE_PASS_STATUS,
            "post_reveal_inputs_not_used_for_commitment": all(
                row.get("outcome_visible_at_commitment") is False for row in lineage_rows
            ),
            "llm_judge_absent": True,
            "human_content_judgment_absent": True,
            "unsupported_writes_absent": True,
        },
        "metrics": {
            "policy_sensitivity": sensitivity_summary,
            "lineage": lineage_summary,
        },
        "errors": errors,
        "claims": {
            "proves": [
                "the fixed action selector can be recomputed from sealed committed next-action distributions",
                "oracle-aligned and anti-oracle policy projections are compared under the same deterministic utility function",
                "lineage receipt fails closed unless evidence references include accepted raw source ids and content hashes",
                "no new Tau, Memory, provider, canonical-memory, identity, or source-memory write was attempted",
            ],
            "does_not_prove": [
                "that counterfactual dreaming improves prediction or planning",
                "that every historical PCTOM-R artifact already has complete raw Memory recall attribution",
                "semantic dream quality",
                "paid provider execution",
                "complete live Phase 01-16 runtime execution",
            ],
        },
    }
    receipt["receipt_sha256"] = _stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--condition-root", type=Path, required=True)
    parser.add_argument("--action-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt_out = args.receipt_out or (args.output_root / "pctom_causal_identifiability_receipt.json")
    receipt = run_causal_identifiability_gate(
        condition_root=args.condition_root,
        action_root=args.action_root,
        output_root=args.output_root,
        receipt_out=receipt_out,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
