#!/usr/bin/env python3
"""Validate deterministic PCTOM-R Gate 8 reliability surface fixtures."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_TOM_RELIABILITY_SURFACE"
BLOCKED_STATUS = "BLOCKED_TOM_RELIABILITY_SURFACE"
ALLOWED_TERMINAL_OUTCOMES = {
    "RECOVERED_WITH_EQUIVALENT_END_STATE",
    "BLOCKED_BEFORE_SIDE_EFFECT",
    "QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE",
}
FORBIDDEN_TERMINAL_OUTCOMES = {"CONTINUED_WITH_UNKNOWN_STATE"}


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


def _number(value: Any, prefix: str, errors: list[str]) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"{prefix}_not_number:{value}")
        return None
    return float(value)


def _int(value: Any, prefix: str, errors: list[str]) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool):
        errors.append(f"{prefix}_not_integer:{value}")
        return None
    return int(value)


def _check_surface(surface_path: Path) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    surface = _load_json(surface_path, errors, "reliability_surface")
    counts = {
        "trials": 0,
        "recovered": 0,
        "blocked": 0,
        "quarantined": 0,
        "fault_injected_trials": 0,
        "perturbed_trials": 0,
        "repeat_groups": 0,
        "equivalent_end_state_trials": 0,
        "forbidden_terminal_outcomes": 0,
        "side_effect_violations": 0,
    }
    checks = {
        "surface_schema_valid": False,
        "has_repeated_execution": False,
        "has_semantic_perturbation": False,
        "has_fault_injection": False,
        "terminal_outcomes_allowed": True,
        "recovered_trials_equivalent": True,
        "blocked_trials_before_side_effect": True,
        "quarantined_trials_no_active_partial": True,
        "no_unknown_state_continuation": True,
        "no_canonical_identity_source_writes": True,
        "retries_do_not_duplicate_active_state": True,
    }
    metrics = {
        "k_total": None,
        "epsilon_values": [],
        "lambda_values": [],
        "pass_k": None,
        "fault_containment_rate": None,
    }

    if not isinstance(surface, dict):
        errors.append("reliability_surface_not_object")
        return errors, {"counts": counts, "checks": checks, "metrics": metrics}
    if surface.get("schema") != "persona_dream.research.prospective_tom.reliability_surface.v1":
        errors.append(f"invalid_reliability_surface_schema:{surface.get('schema')}")
    else:
        checks["surface_schema_valid"] = True
    if surface.get("canonical_memory_write") is not False:
        errors.append("surface_canonical_memory_write_not_false")
        checks["no_canonical_identity_source_writes"] = False
    if surface.get("identity_write") is not False:
        errors.append("surface_identity_write_not_false")
        checks["no_canonical_identity_source_writes"] = False
    if surface.get("source_memory_write") is not False:
        errors.append("surface_source_memory_write_not_false")
        checks["no_canonical_identity_source_writes"] = False

    expected_k = _int(surface.get("k"), "surface_k", errors)
    metrics["k_total"] = expected_k
    expected_epsilon_values = surface.get("epsilon_values")
    expected_lambda_values = surface.get("lambda_values")
    if not isinstance(expected_epsilon_values, list) or not expected_epsilon_values:
        errors.append("surface_epsilon_values_not_nonempty_list")
        expected_epsilon_values = []
    if not isinstance(expected_lambda_values, list) or not expected_lambda_values:
        errors.append("surface_lambda_values_not_nonempty_list")
        expected_lambda_values = []
    metrics["epsilon_values"] = expected_epsilon_values
    metrics["lambda_values"] = expected_lambda_values

    trials = surface.get("trials")
    if not isinstance(trials, list) or not trials:
        errors.append("surface_trials_not_nonempty_list")
        trials = []
    seen_trial_ids: set[str] = set()
    repeat_groups: dict[str, list[dict[str, Any]]] = {}
    baseline_by_group: dict[str, str] = {}
    contained_faults = 0
    total_faults = 0
    terminal_successes = 0

    for idx, trial in enumerate(trials):
        prefix = f"trial_{idx}"
        counts["trials"] += 1
        if not isinstance(trial, dict):
            errors.append(f"{prefix}_not_object")
            continue
        trial_id = trial.get("trial_id")
        if not isinstance(trial_id, str) or not trial_id:
            errors.append(f"{prefix}_missing_trial_id")
        elif trial_id in seen_trial_ids:
            errors.append(f"duplicate_trial_id:{trial_id}")
        else:
            seen_trial_ids.add(trial_id)
        repeat_group_id = trial.get("repeat_group_id")
        if not isinstance(repeat_group_id, str) or not repeat_group_id:
            errors.append(f"{prefix}_missing_repeat_group_id")
            repeat_group_id = f"__missing_{idx}"
        repeat_groups.setdefault(repeat_group_id, []).append(trial)

        k = _int(trial.get("k"), f"{prefix}_k", errors)
        epsilon = _number(trial.get("epsilon"), f"{prefix}_epsilon", errors)
        lambdav = _number(trial.get("lambda"), f"{prefix}_lambda", errors)
        if expected_k is not None and k is not None and k != expected_k:
            errors.append(f"{prefix}_k_mismatch:{k}:{expected_k}")
        if epsilon is not None and epsilon > 0:
            counts["perturbed_trials"] += 1
        if lambdav is not None and lambdav > 0:
            counts["fault_injected_trials"] += 1
            total_faults += 1
        if epsilon is not None and expected_epsilon_values and epsilon not in expected_epsilon_values:
            errors.append(f"{prefix}_epsilon_not_in_surface_values:{epsilon}")
        if lambdav is not None and expected_lambda_values and lambdav not in expected_lambda_values:
            errors.append(f"{prefix}_lambda_not_in_surface_values:{lambdav}")

        terminal = trial.get("terminal_outcome")
        if terminal in FORBIDDEN_TERMINAL_OUTCOMES:
            counts["forbidden_terminal_outcomes"] += 1
            checks["terminal_outcomes_allowed"] = False
            checks["no_unknown_state_continuation"] = False
            errors.append(f"{prefix}_forbidden_terminal_outcome:{terminal}")
        elif terminal not in ALLOWED_TERMINAL_OUTCOMES:
            checks["terminal_outcomes_allowed"] = False
            errors.append(f"{prefix}_terminal_outcome_not_allowed:{terminal}")
        else:
            terminal_successes += 1
            if terminal == "RECOVERED_WITH_EQUIVALENT_END_STATE":
                counts["recovered"] += 1
            elif terminal == "BLOCKED_BEFORE_SIDE_EFFECT":
                counts["blocked"] += 1
            elif terminal == "QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE":
                counts["quarantined"] += 1

        end_hash = trial.get("end_state_equivalence_sha256")
        if not isinstance(end_hash, str) or not end_hash.startswith("sha256:"):
            errors.append(f"{prefix}_missing_end_state_equivalence_sha256")
        baseline_hash = baseline_by_group.setdefault(repeat_group_id, end_hash if isinstance(end_hash, str) else "")
        side_effect_count = _int(trial.get("side_effect_count"), f"{prefix}_side_effect_count", errors)
        active_partial_state = trial.get("active_partial_state")
        unknown_state_continued = trial.get("unknown_state_continued")
        if unknown_state_continued is not False:
            checks["no_unknown_state_continuation"] = False
            errors.append(f"{prefix}_unknown_state_continued_not_false")

        if terminal == "RECOVERED_WITH_EQUIVALENT_END_STATE":
            if end_hash != baseline_hash:
                checks["recovered_trials_equivalent"] = False
                errors.append(f"{prefix}_recovered_end_state_not_equivalent:{end_hash}:{baseline_hash}")
            else:
                counts["equivalent_end_state_trials"] += 1
                if lambdav is not None and lambdav > 0:
                    contained_faults += 1
        elif terminal == "BLOCKED_BEFORE_SIDE_EFFECT":
            if side_effect_count != 0:
                counts["side_effect_violations"] += 1
                checks["blocked_trials_before_side_effect"] = False
                errors.append(f"{prefix}_blocked_with_side_effects:{side_effect_count}")
            else:
                if lambdav is not None and lambdav > 0:
                    contained_faults += 1
        elif terminal == "QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE":
            if side_effect_count != 0 or active_partial_state is not False:
                counts["side_effect_violations"] += 1
                checks["quarantined_trials_no_active_partial"] = False
                errors.append(f"{prefix}_quarantined_with_active_or_side_effect_state:{side_effect_count}:{active_partial_state}")
            else:
                if lambdav is not None and lambdav > 0:
                    contained_faults += 1

        if trial.get("canonical_memory_write") is not False:
            checks["no_canonical_identity_source_writes"] = False
            errors.append(f"{prefix}_canonical_memory_write_not_false")
        if trial.get("identity_write") is not False:
            checks["no_canonical_identity_source_writes"] = False
            errors.append(f"{prefix}_identity_write_not_false")
        if trial.get("source_memory_write") is not False:
            checks["no_canonical_identity_source_writes"] = False
            errors.append(f"{prefix}_source_memory_write_not_false")

        duplicate_active_predictions = _int(trial.get("duplicate_active_predictions"), f"{prefix}_duplicate_active_predictions", errors)
        duplicate_active_revisions = _int(trial.get("duplicate_active_revisions"), f"{prefix}_duplicate_active_revisions", errors)
        if duplicate_active_predictions not in (0, None) or duplicate_active_revisions not in (0, None):
            checks["retries_do_not_duplicate_active_state"] = False
            errors.append(f"{prefix}_duplicate_active_state:{duplicate_active_predictions}:{duplicate_active_revisions}")

    counts["repeat_groups"] = len(repeat_groups)
    if expected_k is not None:
        repeated_groups = [group for group in repeat_groups.values() if len(group) >= expected_k]
        checks["has_repeated_execution"] = bool(repeated_groups)
    checks["has_semantic_perturbation"] = counts["perturbed_trials"] > 0
    checks["has_fault_injection"] = counts["fault_injected_trials"] > 0
    if not checks["has_semantic_perturbation"]:
        errors.append("surface_missing_semantic_perturbation_trial")
    if not checks["has_fault_injection"]:
        errors.append("surface_missing_fault_injection_trial")
    if not checks["has_repeated_execution"]:
        errors.append("surface_missing_repeated_execution_group")
    metrics["pass_k"] = terminal_successes / counts["trials"] if counts["trials"] else None
    metrics["fault_containment_rate"] = contained_faults / total_faults if total_faults else None

    return errors, {"counts": counts, "checks": checks, "metrics": metrics}


def build_receipt(surface_path: Path, receipt_out: Path) -> dict[str, Any]:
    errors, derived = _check_surface(surface_path)
    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.reliability_surface_check_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
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
                "the supplied reliability surface includes repeated executions, semantic perturbations, and fault-injected trials",
                "terminal outcomes are restricted to recovered, blocked-before-side-effect, or quarantined-with-no-active-partial-state",
                "recovered trials preserve end-state equivalence within their repeat group",
                "blocked and quarantined fault trials do not leave accepted side effects or active partial state",
                "retries do not create duplicate active predictions or revisions in the supplied fixtures",
                "canonical memory, identity, and source-memory writes are absent",
            ]
            if status == PASS_STATUS
            else [
                "the checker produced a fail-closed receipt for an invalid reliability-surface boundary",
            ],
            "does_not_prove": [
                "live Tau execution",
                "live Memory recall",
                "real service fault injection",
                "production retry behavior",
                "statistical prediction benefit",
                "Gate 9 causal replay",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--surface", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt = build_receipt(args.surface, args.receipt_out)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
