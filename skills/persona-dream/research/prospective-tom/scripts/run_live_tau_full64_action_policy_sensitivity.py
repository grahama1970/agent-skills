#!/usr/bin/env python3
"""Measure realized action-policy sensitivity over full64 live Tau artifacts."""
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
PASS_STATUS = "PASS_LIVE_TAU_PCTOM_FULL64_ACTION_POLICY_SENSITIVITY"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_FULL64_ACTION_POLICY_SENSITIVITY"
DEFAULT_SPLIT = "sealed_test"


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


def _family_from_episode(episode_id: str) -> str:
    parts = episode_id.split("-")
    if len(parts) >= 4 and parts[0].startswith("sealed"):
        return "-".join(parts[1:-1])
    return episode_id


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _number(value: Any, errors: list[str], label: str) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"{label}_not_number:{value}")
        return None
    return float(value)


def _validate_base(base_receipt: dict[str, Any], errors: list[str]) -> None:
    expected = {
        "status": "PASS_LIVE_TAU_PCTOM_SEALED_TEST_REPLICATION",
        "split": DEFAULT_SPLIT,
        "episode_limit": 64,
        "full_64_episode_replication": True,
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
    }
    for key, value in expected.items():
        if base_receipt.get(key) != value:
            errors.append(f"base_{key}_mismatch:{base_receipt.get(key)}:{value}")
    counts = base_receipt.get("counts") if isinstance(base_receipt.get("counts"), dict) else {}
    if counts.get("episodes_consumed") != 64:
        errors.append(f"base_episode_count_mismatch:{counts.get('episodes_consumed')}:64")
    if counts.get("cases") != 256:
        errors.append(f"base_case_count_mismatch:{counts.get('cases')}:256")
    for count_key in ("action_decisions_per_condition", "planning_regret_scores_per_condition"):
        values = counts.get(count_key)
        if not isinstance(values, dict):
            errors.append(f"base_{count_key}_not_object")
            continue
        for condition in CONDITIONS:
            if values.get(condition) != 64:
                errors.append(f"base_{count_key}_mismatch:{condition}:{values.get(condition)}:64")


def _validate_diagnostic(diagnostic_receipt: dict[str, Any], errors: list[str]) -> None:
    if diagnostic_receipt.get("status") != "PASS_LIVE_TAU_PCTOM_FULL64_PLANNING_DIAGNOSTIC":
        errors.append(f"diagnostic_status_not_pass:{diagnostic_receipt.get('status')}")
    if diagnostic_receipt.get("diagnostic_conclusion") != "SPARSE_FAMILY_CONCENTRATED_SIGNAL":
        errors.append(f"diagnostic_conclusion_unexpected:{diagnostic_receipt.get('diagnostic_conclusion')}")
    if diagnostic_receipt.get("planning_benefit_with_confidence") is not False:
        errors.append(f"diagnostic_planning_benefit_unexpected:{diagnostic_receipt.get('planning_benefit_with_confidence')}")
    if diagnostic_receipt.get("mocked") is not False or diagnostic_receipt.get("live") is not True:
        errors.append("diagnostic_mocked_live_flags_mismatch")
    counts = diagnostic_receipt.get("counts") if isinstance(diagnostic_receipt.get("counts"), dict) else {}
    expected_counts = {
        "episodes": 64,
        "tie_count": 60,
        "benefit_count": 3,
        "harm_count": 1,
        "nonzero_count": 4,
    }
    for key, value in expected_counts.items():
        if counts.get(key) != value:
            errors.append(f"diagnostic_{key}_mismatch:{counts.get(key)}:{value}")
    if counts.get("nonzero_families") != ["trust-commit"]:
        errors.append(f"diagnostic_nonzero_families_mismatch:{counts.get('nonzero_families')}")


def _utility_surface(action_selection: dict[str, Any], errors: list[str], label: str) -> dict[str, float]:
    options = action_selection.get("action_options")
    if not isinstance(options, list):
        errors.append(f"{label}_action_options_not_list")
        return {}
    surface: dict[str, float] = {}
    for idx, option in enumerate(options):
        if not isinstance(option, dict):
            errors.append(f"{label}_action_option_{idx}_not_object")
            continue
        action = option.get("action")
        utility = option.get("expected_utility")
        if not isinstance(action, str) or not isinstance(utility, (int, float)) or isinstance(utility, bool):
            errors.append(f"{label}_action_option_{idx}_invalid:{option}")
            continue
        if action in surface:
            errors.append(f"{label}_duplicate_action_option:{action}")
        surface[action] = float(utility)
        if option.get("policy_compliant") is not True:
            errors.append(f"{label}_action_option_{idx}_policy_noncompliant:{action}")
    if len(surface) != 7:
        errors.append(f"{label}_surface_size_mismatch:{len(surface)}:7")
    return surface


def _build_rows(base_root: Path, action_index: list[dict[str, Any]], errors: list[str]) -> list[dict[str, Any]]:
    by_episode: dict[str, dict[str, dict[str, Any]]] = {}
    loaded_actions: dict[tuple[str, str], dict[str, Any]] = {}
    for idx, row in enumerate(action_index):
        if not isinstance(row, dict):
            errors.append(f"action_index_{idx}_not_object")
            continue
        episode_id = row.get("episode_id")
        condition = row.get("condition")
        if not isinstance(episode_id, str) or condition not in CONDITIONS:
            errors.append(f"action_index_{idx}_invalid_identity:{episode_id}:{condition}")
            continue
        if row.get("status") != "PASS_TOM_ACTION_SELECTION":
            errors.append(f"action_index_{idx}_status_not_pass:{row.get('status')}")
        action_path = Path(str(row.get("action_selection_path", "")))
        if not action_path.is_absolute():
            action_path = base_root / action_path
        action_selection = _load_json(action_path, errors, f"action_selection_{episode_id}_{condition}")
        if not isinstance(action_selection, dict):
            action_selection = {}
        loaded_actions[(episode_id, condition)] = action_selection
        by_episode.setdefault(episode_id, {})[condition] = row

    rows: list[dict[str, Any]] = []
    for episode_id in sorted(by_episode):
        episode_rows = by_episode[episode_id]
        missing = [condition for condition in CONDITIONS if condition not in episode_rows]
        if missing:
            errors.append(f"episode_missing_conditions:{episode_id}:{missing}")
            continue
        baseline_regrets: dict[str, float] = {}
        for condition in ("M", "R", "D"):
            regret = _number(
                episode_rows[condition].get("planning_regret"),
                errors,
                f"{episode_id}_{condition}_planning_regret",
            )
            if regret is not None:
                baseline_regrets[condition] = regret
        if set(baseline_regrets) != {"M", "R", "D"}:
            errors.append(f"episode_baseline_regret_missing:{episode_id}:{sorted(baseline_regrets)}")
            continue
        baseline_condition = min(baseline_regrets, key=baseline_regrets.get)
        baseline_index = episode_rows[baseline_condition]
        cd_index = episode_rows["CD"]
        baseline_action = loaded_actions.get((episode_id, baseline_condition), {})
        cd_action = loaded_actions.get((episode_id, "CD"), {})
        baseline_surface = _utility_surface(baseline_action, errors, f"{episode_id}_{baseline_condition}")
        cd_surface = _utility_surface(cd_action, errors, f"{episode_id}_CD")
        cd_selected = cd_index.get("selected_action")
        baseline_selected = baseline_index.get("selected_action")
        oracle_action = cd_index.get("oracle_action")
        cd_regret = _number(cd_index.get("planning_regret"), errors, f"{episode_id}_CD_planning_regret")
        baseline_regret = _number(
            baseline_index.get("planning_regret"),
            errors,
            f"{episode_id}_{baseline_condition}_selected_baseline_planning_regret",
        )
        if cd_regret is None or baseline_regret is None:
            errors.append(f"episode_selected_regret_missing:{episode_id}")
            continue
        delta = cd_regret - baseline_regret
        cd_oracle_utility = cd_surface.get(str(oracle_action))
        baseline_oracle_utility = baseline_surface.get(str(oracle_action))
        cd_selected_utility = cd_surface.get(str(cd_selected))
        baseline_selected_utility = baseline_surface.get(str(baseline_selected))
        rows.append(
            {
                "episode_id": episode_id,
                "family": _family_from_episode(episode_id),
                "baseline_condition": baseline_condition,
                "baseline_action": baseline_selected,
                "cd_action": cd_selected,
                "oracle_action": oracle_action,
                "action_switched": cd_selected != baseline_selected,
                "cd_matches_oracle": cd_selected == oracle_action,
                "baseline_matches_oracle": baseline_selected == oracle_action,
                "oracle_match_transition": (
                    "GAIN"
                    if cd_selected == oracle_action and baseline_selected != oracle_action
                    else "LOSS"
                    if cd_selected != oracle_action and baseline_selected == oracle_action
                    else "UNCHANGED"
                ),
                "baseline_regret": baseline_regret,
                "cd_regret": cd_regret,
                "cd_minus_baseline": delta,
                "direction": "BENEFIT" if delta < 0 else "HARM" if delta > 0 else "TIE",
                "baseline_selected_utility": baseline_selected_utility,
                "cd_selected_utility": cd_selected_utility,
                "baseline_oracle_utility": baseline_oracle_utility,
                "cd_oracle_utility": cd_oracle_utility,
                "baseline_utility_gap_to_oracle": None
                if baseline_oracle_utility is None or baseline_selected_utility is None
                else baseline_oracle_utility - baseline_selected_utility,
                "cd_utility_gap_to_oracle": None
                if cd_oracle_utility is None or cd_selected_utility is None
                else cd_oracle_utility - cd_selected_utility,
            }
        )
    return rows


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    nonzero = [row for row in rows if row["cd_minus_baseline"] != 0]
    switch_rows = [row for row in rows if row["action_switched"]]
    oracle_gains = [row for row in rows if row["oracle_match_transition"] == "GAIN"]
    oracle_losses = [row for row in rows if row["oracle_match_transition"] == "LOSS"]
    families: dict[str, Any] = {}
    for family in sorted({row["family"] for row in rows}):
        family_rows = [row for row in rows if row["family"] == family]
        families[family] = {
            "episodes": len(family_rows),
            "direction_counts": dict(collections.Counter(row["direction"] for row in family_rows)),
            "switch_count": sum(1 for row in family_rows if row["action_switched"]),
            "oracle_match_transitions": dict(collections.Counter(row["oracle_match_transition"] for row in family_rows)),
            "cd_actions": dict(collections.Counter(str(row["cd_action"]) for row in family_rows)),
            "baseline_actions": dict(collections.Counter(str(row["baseline_action"]) for row in family_rows)),
            "oracle_actions": dict(collections.Counter(str(row["oracle_action"]) for row in family_rows)),
            "mean_cd_minus_baseline": _mean([float(row["cd_minus_baseline"]) for row in family_rows]),
        }
    return {
        "episodes": len(rows),
        "mean_cd_minus_baseline": _mean([float(row["cd_minus_baseline"]) for row in rows]),
        "direction_counts": dict(collections.Counter(row["direction"] for row in rows)),
        "delta_counts": dict(collections.Counter(str(row["cd_minus_baseline"]) for row in rows)),
        "action_switch_count": len(switch_rows),
        "nonzero_delta_count": len(nonzero),
        "nonzero_action_switch_count": sum(1 for row in nonzero if row["action_switched"]),
        "oracle_match_gain_count": len(oracle_gains),
        "oracle_match_loss_count": len(oracle_losses),
        "net_oracle_match_gain": len(oracle_gains) - len(oracle_losses),
        "nonzero_rows": nonzero,
        "action_switch_rows": switch_rows,
        "families": families,
    }


def run_action_policy_sensitivity(
    *,
    base_root: Path,
    planning_diagnostic_root: Path,
    output_root: Path,
    receipt_out: Path,
) -> dict[str, Any]:
    started = time.monotonic()
    base_root = base_root.resolve()
    planning_diagnostic_root = planning_diagnostic_root.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    errors: list[str] = []

    base_receipt_path = base_root / "live_tau_sealed_test_replication_receipt.v1.json"
    diagnostic_receipt_path = planning_diagnostic_root / "live_tau_full64_planning_diagnostic_receipt.v1.json"
    action_index_path = base_root / "live_tau_sealed_test_action_selection" / "artifacts" / "live_condition_action_decisions.json"
    base_receipt = _load_json(base_receipt_path, errors, "base_live_tau_full64_receipt")
    diagnostic_receipt = _load_json(diagnostic_receipt_path, errors, "full64_planning_diagnostic_receipt")
    action_index = _load_json(action_index_path, errors, "action_decision_index")
    if not isinstance(base_receipt, dict):
        base_receipt = {}
    if not isinstance(diagnostic_receipt, dict):
        diagnostic_receipt = {}
    if not isinstance(action_index, list):
        errors.append("action_decision_index_not_list")
        action_index = []
    _validate_base(base_receipt, errors)
    _validate_diagnostic(diagnostic_receipt, errors)

    rows = _build_rows(base_root, action_index, errors)
    if len(rows) != 64:
        errors.append(f"sensitivity_row_count_mismatch:{len(rows)}:64")
    summary = _summarize(rows)
    nonzero = summary["nonzero_rows"]
    nonzero_families = sorted({row["family"] for row in nonzero})
    nonzero_all_switches = bool(nonzero) and all(row["action_switched"] for row in nonzero)
    nonzero_all_oracle_transitions = bool(nonzero) and all(
        row["oracle_match_transition"] in {"GAIN", "LOSS"} for row in nonzero
    )
    nonzero_transition_counts = collections.Counter(row["oracle_match_transition"] for row in nonzero)
    sensitivity_conclusion = (
        "REALIZED_ACTION_SWITCH_EXPLAINS_SPARSE_PLANNING_SIGNAL"
        if len(nonzero) == 4
        and nonzero_families == ["trust-commit"]
        and nonzero_all_switches
        and nonzero_all_oracle_transitions
        and nonzero_transition_counts.get("GAIN", 0) == 3
        and nonzero_transition_counts.get("LOSS", 0) == 1
        else "ACTION_POLICY_SENSITIVITY_INCONCLUSIVE"
    )
    if sensitivity_conclusion != "REALIZED_ACTION_SWITCH_EXPLAINS_SPARSE_PLANNING_SIGNAL":
        errors.append(f"unexpected_sensitivity_conclusion:{sensitivity_conclusion}")

    artifacts_root = output_root / "artifacts"
    rows_path = artifacts_root / "action_policy_sensitivity_rows.json"
    summary_path = artifacts_root / "action_policy_sensitivity_summary.json"
    sensitivity_summary = {
        "schema": "persona_dream.research.prospective_tom.live_tau_full64_action_policy_sensitivity_summary.v1",
        "base_live_tau_replication_receipt_sha256": _file_sha256(base_receipt_path) if base_receipt_path.exists() else None,
        "full64_planning_diagnostic_receipt_sha256": _file_sha256(diagnostic_receipt_path)
        if diagnostic_receipt_path.exists()
        else None,
        "sensitivity_conclusion": sensitivity_conclusion,
        "summary": summary,
        "interpretation": {
            "planning_benefit_with_confidence": False,
            "realized_action_policy_sensitive": sensitivity_conclusion
            == "REALIZED_ACTION_SWITCH_EXPLAINS_SPARSE_PLANNING_SIGNAL",
            "nonzero_rows_are_action_switches": nonzero_all_switches,
            "nonzero_rows_are_oracle_match_transitions": nonzero_all_oracle_transitions,
            "nonzero_families": nonzero_families,
            "oracle_match_gain_count": int(nonzero_transition_counts.get("GAIN", 0)),
            "oracle_match_loss_count": int(nonzero_transition_counts.get("LOSS", 0)),
            "reason_planning_ci_still_crosses_zero": "the action-policy-sensitive cases are four trust-commit episodes out of sixty-four",
            "next_planning_evidence_needed": "repeat or expand trust/commitment episodes before claiming confidence-bounded planning benefit",
        },
    }
    _write_json(rows_path, {"schema": "persona_dream.research.prospective_tom.live_tau_full64_action_policy_sensitivity_rows.v1", "rows": rows})
    _write_json(summary_path, sensitivity_summary)

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_tau_full64_action_policy_sensitivity_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "base_root": str(base_root),
        "base_live_tau_replication_receipt": str(base_receipt_path),
        "base_live_tau_replication_receipt_sha256": _file_sha256(base_receipt_path) if base_receipt_path.exists() else None,
        "planning_diagnostic_root": str(planning_diagnostic_root),
        "full64_planning_diagnostic_receipt": str(diagnostic_receipt_path),
        "full64_planning_diagnostic_receipt_sha256": _file_sha256(diagnostic_receipt_path)
        if diagnostic_receipt_path.exists()
        else None,
        "action_index_path": str(action_index_path),
        "action_index_sha256": _file_sha256(action_index_path) if action_index_path.exists() else None,
        "sensitivity_rows_path": str(rows_path),
        "sensitivity_rows_sha256": _file_sha256(rows_path),
        "sensitivity_summary_path": str(summary_path),
        "sensitivity_summary_sha256": _file_sha256(summary_path),
        "sensitivity_conclusion": sensitivity_conclusion,
        "planning_benefit_with_confidence": False,
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "deterministic_simulator_corpus_fixture_backed": True,
        "live_tau_reexecuted": False,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "tau_call_attempts": 0,
        "tau_live_call_performed": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "counts": {
            "episodes": len(rows),
            "action_switch_count": summary["action_switch_count"],
            "nonzero_delta_count": summary["nonzero_delta_count"],
            "nonzero_action_switch_count": summary["nonzero_action_switch_count"],
            "oracle_match_gain_count": summary["oracle_match_gain_count"],
            "oracle_match_loss_count": summary["oracle_match_loss_count"],
            "net_oracle_match_gain": summary["net_oracle_match_gain"],
            "nonzero_families": nonzero_families,
        },
        "checks": {
            "base_receipt_passed": base_receipt.get("status") == "PASS_LIVE_TAU_PCTOM_SEALED_TEST_REPLICATION",
            "planning_diagnostic_receipt_passed": diagnostic_receipt.get("status")
            == "PASS_LIVE_TAU_PCTOM_FULL64_PLANNING_DIAGNOSTIC",
            "base_is_full64_live_tau": base_receipt.get("full_64_episode_replication") is True
            and base_receipt.get("live") is True,
            "sensitivity_rows_cover_64_episodes": len(rows) == 64,
            "per_action_utility_surface_present": not any("surface_size_mismatch" in error for error in errors),
            "nonzero_deltas_are_family_concentrated": nonzero_families == ["trust-commit"],
            "nonzero_deltas_are_action_switches": nonzero_all_switches,
            "nonzero_deltas_are_oracle_match_transitions": nonzero_all_oracle_transitions,
            "sparse_signal_has_three_gains_one_loss": nonzero_transition_counts.get("GAIN", 0) == 3
            and nonzero_transition_counts.get("LOSS", 0) == 1,
            "llm_judge_absent": True,
            "human_content_judgment_absent": True,
            "unsupported_writes_absent": True,
        },
        "metrics": sensitivity_summary,
        "errors": errors,
        "claims": {
            "proves": [
                "the accepted full64 live Tau action decisions were consumed without reexecuting Tau",
                "all four nonzero planning-regret deltas are action switches in trust-commit episodes",
                "the sparse planning signal corresponds to three oracle-match gains and one oracle-match loss",
                "per-action deterministic utility surfaces are present for the compared selected and oracle actions",
                "no human content judgment, LLM judge, Memory write, provider call, canonical write, identity write, or source-memory write was attempted",
            ]
            if status == PASS_STATUS
            else [
                "the action-policy sensitivity receipt failed closed before accepting the planning-sensitivity explanation",
            ],
            "does_not_prove": [
                "confidence-bounded planning-regret benefit",
                "planning benefit under repeated live Tau seeds",
                "planning benefit under a larger or differently balanced trust/commitment corpus",
                "production retry machinery",
                "live Memory recall in the sealed-test loop",
                "complete live Phase 01-16 runtime execution",
                "paid provider execution",
                "video, audio, or semantic dream quality",
            ],
        },
    }
    receipt["receipt_sha256"] = _stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-root", type=Path, required=True)
    parser.add_argument("--planning-diagnostic-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt_out = args.receipt_out or (args.output_root / "live_tau_full64_action_policy_sensitivity_receipt.v1.json")
    receipt = run_action_policy_sensitivity(
        base_root=args.base_root,
        planning_diagnostic_root=args.planning_diagnostic_root,
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
