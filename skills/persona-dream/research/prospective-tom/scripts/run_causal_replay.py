#!/usr/bin/env python3
"""Validate deterministic PCTOM-R Gate 9 causal replay fixtures."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_TOM_CAUSAL_REPLAY"
BLOCKED_STATUS = "BLOCKED_TOM_CAUSAL_REPLAY"
REPLAY_SCHEMA = "persona_dream.research.prospective_tom.causal_replay.v1"
SURFACE_SCHEMA = "persona_dream.research.prospective_tom.reliability_surface.v1"
FORBIDDEN_TERMINAL_OUTCOMES = {"CONTINUED_WITH_UNKNOWN_STATE"}
ALLOWED_REPLAY_TERMINAL_OUTCOMES = {
    "CAUSAL_FAILURE_LOCALIZED",
    "BLOCKED_REPLAY_INSUFFICIENT_EVIDENCE",
    "NO_CAUSAL_EFFECT_FOUND",
}
ALLOWED_TOOL_RETURN_OPERATIONS = {"REMOVE_TOOL_RETURN", "REPLACE_TOOL_RETURN"}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


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


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 71 and value.startswith("sha256:") and all(
        c in "0123456789abcdef" for c in value[7:]
    )


def _check_bool_false(value: Any, name: str, errors: list[str]) -> bool:
    if value is not False:
        errors.append(f"{name}_not_false")
        return False
    return True


def _trial_by_id(surface: dict[str, Any], trial_id: str) -> dict[str, Any] | None:
    trials = surface.get("trials")
    if not isinstance(trials, list):
        return None
    for trial in trials:
        if isinstance(trial, dict) and trial.get("trial_id") == trial_id:
            return trial
    return None


def _baseline_hash_for_trial(surface: dict[str, Any], target_trial: dict[str, Any]) -> str | None:
    repeat_group_id = target_trial.get("repeat_group_id")
    trials = surface.get("trials")
    if not isinstance(repeat_group_id, str) or not isinstance(trials, list):
        return None
    for trial in trials:
        if not isinstance(trial, dict):
            continue
        if trial.get("repeat_group_id") != repeat_group_id:
            continue
        terminal = trial.get("terminal_outcome")
        if terminal == "RECOVERED_WITH_EQUIVALENT_END_STATE":
            end_hash = trial.get("end_state_equivalence_sha256")
            return end_hash if _is_sha256(end_hash) else None
    for trial in trials:
        if not isinstance(trial, dict):
            continue
        if trial.get("terminal_outcome") == "RECOVERED_WITH_EQUIVALENT_END_STATE":
            end_hash = trial.get("end_state_equivalence_sha256")
            return end_hash if _is_sha256(end_hash) else None
    return None


def _check_replay(replay_path: Path, surface_path: Path) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    replay = _load_json(replay_path, errors, "causal_replay")
    surface = _load_json(surface_path, errors, "reliability_surface")
    counts = {
        "target_trials": 0,
        "first_divergent_receipts": 0,
        "suspected_tool_returns": 0,
        "state_comparisons": 0,
        "localized_causes": 0,
        "forbidden_terminal_outcomes": 0,
        "forbidden_write_attempts": 0,
    }
    checks = {
        "replay_schema_valid": False,
        "surface_schema_valid": False,
        "surface_hash_bound": False,
        "target_trial_resolved": False,
        "target_trial_fault_or_divergent": False,
        "first_divergent_receipt_identified": False,
        "replay_starts_at_first_divergence": False,
        "exactly_one_tool_return_removed_or_replaced": False,
        "state_comparison_present": False,
        "counterfactual_matches_expected": False,
        "causal_failure_localization_written": False,
        "no_unknown_state_continuation": False,
        "no_canonical_identity_source_writes": False,
    }
    metrics = {
        "target_trial_id": None,
        "target_terminal_outcome": None,
        "first_divergent_receipt_id": None,
        "localized_cause_type": None,
        "causal_confidence": None,
    }

    if not isinstance(replay, dict):
        errors.append("causal_replay_not_object")
        return errors, {"counts": counts, "checks": checks, "metrics": metrics}
    if not isinstance(surface, dict):
        errors.append("reliability_surface_not_object")
        return errors, {"counts": counts, "checks": checks, "metrics": metrics}

    if replay.get("schema") != REPLAY_SCHEMA:
        errors.append(f"invalid_causal_replay_schema:{replay.get('schema')}")
    else:
        checks["replay_schema_valid"] = True
    if surface.get("schema") != SURFACE_SCHEMA:
        errors.append(f"invalid_reliability_surface_schema:{surface.get('schema')}")
    else:
        checks["surface_schema_valid"] = True

    surface_hash = _stable_json_sha256(surface)
    if replay.get("reliability_surface_sha256") != surface_hash:
        errors.append(f"reliability_surface_sha256_mismatch:{replay.get('reliability_surface_sha256')}:{surface_hash}")
    else:
        checks["surface_hash_bound"] = True
    if replay.get("surface_id") != surface.get("surface_id"):
        errors.append(f"surface_id_mismatch:{replay.get('surface_id')}:{surface.get('surface_id')}")

    trial_id = replay.get("trial_id")
    metrics["target_trial_id"] = trial_id
    if not isinstance(trial_id, str) or not trial_id:
        errors.append("missing_trial_id")
        target_trial = None
    else:
        target_trial = _trial_by_id(surface, trial_id)
        if target_trial is None:
            errors.append(f"unresolved_reliability_trial:{trial_id}")
        else:
            counts["target_trials"] = 1
            checks["target_trial_resolved"] = True
            terminal = target_trial.get("terminal_outcome")
            metrics["target_terminal_outcome"] = terminal
            faulted = bool(target_trial.get("faults"))
            divergent = target_trial.get("end_state_equivalence_sha256") != _baseline_hash_for_trial(surface, target_trial)
            if faulted or divergent or terminal != "RECOVERED_WITH_EQUIVALENT_END_STATE":
                checks["target_trial_fault_or_divergent"] = True
            else:
                errors.append(f"target_trial_not_fault_or_divergent:{trial_id}")

    first = replay.get("first_divergent_receipt")
    if not isinstance(first, dict):
        errors.append("missing_first_divergent_receipt")
        first_receipt_id = None
    else:
        counts["first_divergent_receipts"] = 1
        first_receipt_id = first.get("receipt_id")
        metrics["first_divergent_receipt_id"] = first_receipt_id
        if not isinstance(first_receipt_id, str) or not first_receipt_id:
            errors.append("first_divergent_receipt_missing_receipt_id")
        receipt_index = first.get("receipt_index")
        if not isinstance(receipt_index, int) or isinstance(receipt_index, bool) or receipt_index < 0:
            errors.append(f"first_divergent_receipt_bad_index:{receipt_index}")
        if not isinstance(first.get("boundary"), str) or not first.get("boundary"):
            errors.append("first_divergent_receipt_missing_boundary")
        expected_hash = first.get("expected_state_sha256")
        observed_hash = first.get("observed_state_sha256")
        if not _is_sha256(expected_hash):
            errors.append(f"first_divergent_receipt_bad_expected_hash:{expected_hash}")
        if not _is_sha256(observed_hash):
            errors.append(f"first_divergent_receipt_bad_observed_hash:{observed_hash}")
        if expected_hash == observed_hash:
            errors.append("first_divergent_receipt_not_divergent")
        if isinstance(first_receipt_id, str) and first_receipt_id:
            checks["first_divergent_receipt_identified"] = True

    if replay.get("replay_start_receipt_id") != first_receipt_id:
        errors.append(f"replay_start_not_first_divergence:{replay.get('replay_start_receipt_id')}:{first_receipt_id}")
    elif first_receipt_id:
        checks["replay_starts_at_first_divergence"] = True

    suspected = replay.get("suspected_tool_return")
    if not isinstance(suspected, dict):
        errors.append("missing_suspected_tool_return")
    else:
        counts["suspected_tool_returns"] = 1
        if suspected.get("receipt_id") != first_receipt_id:
            errors.append(f"suspected_tool_return_receipt_mismatch:{suspected.get('receipt_id')}:{first_receipt_id}")
        if not isinstance(suspected.get("tool_return_id"), str) or not suspected.get("tool_return_id"):
            errors.append("suspected_tool_return_missing_id")
        if not isinstance(suspected.get("tool_name"), str) or not suspected.get("tool_name"):
            errors.append("suspected_tool_return_missing_tool_name")
        operation = suspected.get("operation")
        if operation not in ALLOWED_TOOL_RETURN_OPERATIONS:
            errors.append(f"suspected_tool_return_operation_not_remove_or_replace:{operation}")
        else:
            checks["exactly_one_tool_return_removed_or_replaced"] = True
        if not _is_sha256(suspected.get("original_return_sha256")):
            errors.append(f"suspected_tool_return_bad_original_hash:{suspected.get('original_return_sha256')}")
        if operation == "REPLACE_TOOL_RETURN" and not _is_sha256(suspected.get("replacement_return_sha256")):
            errors.append(f"suspected_tool_return_bad_replacement_hash:{suspected.get('replacement_return_sha256')}")

    comparison = replay.get("comparison")
    if not isinstance(comparison, dict):
        errors.append("missing_state_comparison")
    else:
        counts["state_comparisons"] = 1
        checks["state_comparison_present"] = True
        for key in ("factual_end_state_sha256", "counterfactual_end_state_sha256", "expected_end_state_sha256"):
            if not _is_sha256(comparison.get(key)):
                errors.append(f"comparison_bad_{key}:{comparison.get(key)}")
        if target_trial is not None and comparison.get("factual_end_state_sha256") != target_trial.get("end_state_equivalence_sha256"):
            errors.append(
                "comparison_factual_hash_not_target_observed:"
                f"{comparison.get('factual_end_state_sha256')}:{target_trial.get('end_state_equivalence_sha256')}"
            )
        expected_hash = first.get("expected_state_sha256") if isinstance(first, dict) else None
        if comparison.get("expected_end_state_sha256") != expected_hash:
            errors.append(f"comparison_expected_hash_not_first_divergence:{comparison.get('expected_end_state_sha256')}:{expected_hash}")
        if comparison.get("counterfactual_end_state_sha256") != comparison.get("expected_end_state_sha256"):
            errors.append(
                "comparison_counterfactual_not_expected:"
                f"{comparison.get('counterfactual_end_state_sha256')}:{comparison.get('expected_end_state_sha256')}"
            )
        if comparison.get("counterfactual_matches_expected") is not True:
            errors.append("comparison_counterfactual_matches_expected_not_true")
        else:
            checks["counterfactual_matches_expected"] = True

    localized = replay.get("localized_cause")
    if not isinstance(localized, dict):
        errors.append("missing_localized_cause")
    else:
        counts["localized_causes"] = 1
        cause_type = localized.get("cause_type")
        confidence = localized.get("causal_confidence")
        metrics["localized_cause_type"] = cause_type
        metrics["causal_confidence"] = confidence
        if not isinstance(cause_type, str) or not cause_type:
            errors.append("localized_cause_missing_type")
        if localized.get("receipt_id") != first_receipt_id:
            errors.append(f"localized_cause_receipt_mismatch:{localized.get('receipt_id')}:{first_receipt_id}")
        suspected_tool_return_id = suspected.get("tool_return_id") if isinstance(suspected, dict) else None
        if localized.get("tool_return_id") != suspected_tool_return_id:
            errors.append(f"localized_cause_tool_return_mismatch:{localized.get('tool_return_id')}:{suspected_tool_return_id}")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= float(confidence) <= 1:
            errors.append(f"localized_cause_bad_confidence:{confidence}")
        if not isinstance(localized.get("evidence_refs"), list) or not localized.get("evidence_refs"):
            errors.append("localized_cause_missing_evidence_refs")

    terminal_outcome = replay.get("terminal_outcome")
    if terminal_outcome in FORBIDDEN_TERMINAL_OUTCOMES:
        counts["forbidden_terminal_outcomes"] = 1
        errors.append(f"forbidden_terminal_outcome:{terminal_outcome}")
    elif terminal_outcome not in ALLOWED_REPLAY_TERMINAL_OUTCOMES:
        errors.append(f"terminal_outcome_not_allowed:{terminal_outcome}")
    elif terminal_outcome != "CAUSAL_FAILURE_LOCALIZED":
        errors.append(f"terminal_outcome_not_localized:{terminal_outcome}")
    else:
        checks["causal_failure_localization_written"] = True

    checks["no_unknown_state_continuation"] = _check_bool_false(
        replay.get("unknown_state_continued"), "unknown_state_continued", errors
    )
    no_writes = True
    for field in ("canonical_memory_write", "identity_write", "source_memory_write"):
        if not _check_bool_false(replay.get(field), field, errors):
            counts["forbidden_write_attempts"] += 1
            no_writes = False
    checks["no_canonical_identity_source_writes"] = no_writes

    return errors, {"counts": counts, "checks": checks, "metrics": metrics}


def build_receipt(replay_path: Path, surface_path: Path, receipt_out: Path) -> dict[str, Any]:
    errors, derived = _check_replay(replay_path, surface_path)
    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.causal_replay_check_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "causal_replay_path": str(replay_path.resolve()),
        "causal_replay_sha256": _stable_json_sha256(_load_json(replay_path, [], "causal_replay")),
        "reliability_surface_path": str(surface_path.resolve()),
        "reliability_surface_sha256": _stable_json_sha256(_load_json(surface_path, [], "reliability_surface")),
        "receipt_path": str(receipt_out.resolve()),
        "errors": errors,
        "counts": derived["counts"],
        "checks": derived["checks"],
        "metrics": derived["metrics"],
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "claims": {
            "proves": [
                "the supplied replay targets a resolved faulted or divergent Gate 8 trial",
                "the first divergent receipt is identified and replay starts at that boundary",
                "exactly one suspected tool return is removed or replaced for counterfactual replay",
                "the factual, counterfactual, and expected end-state hashes are compared",
                "the counterfactual replay localizes a cause without continuing unknown state",
                "canonical memory, identity, and source-memory writes are absent",
            ]
            if status == PASS_STATUS
            else [
                "the checker produced a fail-closed receipt for an invalid causal-replay boundary",
            ],
            "does_not_prove": [
                "live Tau execution",
                "live Memory recall",
                "real service fault injection",
                "production causal replay",
                "statistical prediction benefit",
                "complete live Phase 01-16 runtime execution",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--surface", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt = build_receipt(args.replay, args.surface, args.receipt_out)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
