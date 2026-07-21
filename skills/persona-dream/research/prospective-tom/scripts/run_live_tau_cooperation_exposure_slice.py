#!/usr/bin/env python3
"""Run a held-out live Tau slice to test cooperation-threshold exposure."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
RESEARCH_ROOT = ROOT / "research" / "prospective-tom"
BALANCED_SCRIPT = RESEARCH_ROOT / "scripts" / "run_live_tau_balanced_planning_replication.py"
COOPERATION_RULE_SCRIPT = RESEARCH_ROOT / "scripts" / "run_live_tau_cooperation_threshold_rule.py"
PASS_STATUS = "PASS_LIVE_TAU_PCTOM_COOPERATION_EXPOSURE_SLICE"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_COOPERATION_EXPOSURE_SLICE"
POLICY_ID = "pre_outcome_cooperation_threshold_rule.v1"
CONDITIONS = ("M", "R", "D", "CD")
ZERO_WRITE_KEYS = (
    "memory_write_attempts",
    "provider_call_attempts",
    "canonical_memory_write_attempts",
    "identity_write_attempts",
    "source_memory_write_attempts",
)


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


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_load_module:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _episode_variant(episode_id: str) -> int | None:
    suffix = episode_id.rsplit("-", 1)[-1]
    try:
        return int(suffix)
    except ValueError:
        return None


def _coordination_cooperation_outcome_variant(episode_id: str) -> bool:
    variant = _episode_variant(episode_id)
    return "coord" in episode_id and variant is not None and (variant - 1) % 3 == 1


def _validate_zero_writes(receipt: dict[str, Any], errors: list[str], label: str) -> None:
    for key in ZERO_WRITE_KEYS:
        if receipt.get(key) != 0:
            errors.append(f"{label}_{key}_not_zero:{receipt.get(key)}")


def _planning_receipt_path(planning_root: Path) -> Path:
    return planning_root / "live_tau_balanced_planning_replication_receipt.v1.json"


def _run_or_load_planning(
    *,
    balanced: Any,
    output_root: Path,
    planning_root: Path,
    reuse_planning_root: Path | None,
    family_episode_limit: int,
    episodes_per_family: int,
    variant_min: int,
    variant_max: int,
    model: str | None,
    timeout_s: float,
    outer_timeout_s: float | None,
    bootstrap_samples: int,
    bootstrap_seed: int,
    alpha: float,
    errors: list[str],
) -> tuple[dict[str, Any], Path]:
    if reuse_planning_root is not None:
        planning_root = reuse_planning_root.resolve()
        receipt = _load_json(_planning_receipt_path(planning_root), errors, "reuse_planning_receipt")
        return (receipt if isinstance(receipt, dict) else {}), planning_root

    receipt_path = _planning_receipt_path(planning_root)
    try:
        receipt = balanced.run_balanced_replication(
            output_root=planning_root,
            receipt_out=receipt_path,
            family_episode_limit=family_episode_limit,
            episodes_per_family=episodes_per_family,
            variant_min=variant_min,
            variant_max=variant_max,
            model=model,
            timeout_s=timeout_s,
            outer_timeout_s=outer_timeout_s,
            bootstrap_samples=bootstrap_samples,
            bootstrap_seed=bootstrap_seed,
            alpha=alpha,
        )
    except Exception as exc:
        errors.append(f"planning_exception:{type(exc).__name__}:{exc}")
        receipt = _load_json(receipt_path, errors, "planning_receipt_after_exception")
        if not isinstance(receipt, dict):
            receipt = {}
    return receipt, planning_root


def run_slice(
    *,
    derivation_receipt_path: Path,
    output_root: Path,
    receipt_out: Path,
    variant_min: int,
    variant_max: int,
    family_episode_limit: int,
    episodes_per_family: int,
    cooperation_threshold: float,
    model: str | None,
    timeout_s: float,
    outer_timeout_s: float | None,
    bootstrap_samples: int,
    bootstrap_seed: int,
    alpha: float,
    reuse_planning_root: Path | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    derivation_receipt_path = derivation_receipt_path.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    planning_root = output_root / "live_tau_cooperation_exposure_planning"
    artifacts_root = output_root / "artifacts"
    rows_path = artifacts_root / "cooperation_exposure_slice_rows.json"
    summary_path = artifacts_root / "cooperation_exposure_slice_summary.json"
    errors: list[str] = []

    balanced = _load_module(BALANCED_SCRIPT, "pctom_live_tau_balanced_planning_replication")
    rule_module = _load_module(COOPERATION_RULE_SCRIPT, "pctom_live_tau_cooperation_threshold_rule")

    derivation_receipt = _load_json(derivation_receipt_path, errors, "derivation_receipt")
    derivation_receipt = derivation_receipt if isinstance(derivation_receipt, dict) else {}
    rule_module._validate_derivation(derivation_receipt, errors)

    planning_receipt, planning_root = _run_or_load_planning(
        balanced=balanced,
        output_root=output_root,
        planning_root=planning_root,
        reuse_planning_root=reuse_planning_root,
        family_episode_limit=family_episode_limit,
        episodes_per_family=episodes_per_family,
        variant_min=variant_min,
        variant_max=variant_max,
        model=model,
        timeout_s=timeout_s,
        outer_timeout_s=outer_timeout_s,
        bootstrap_samples=bootstrap_samples,
        bootstrap_seed=bootstrap_seed,
        alpha=alpha,
        errors=errors,
    )

    if planning_receipt.get("status") != balanced.PASS_STATUS:
        errors.append(f"planning_status_not_pass:{planning_receipt.get('status')}")
        errors.extend(f"planning_error:{error}" for error in planning_receipt.get("errors", []))
    _validate_zero_writes(derivation_receipt, errors, "derivation")
    _validate_zero_writes(planning_receipt, errors, "planning")

    condition_receipt_path = Path(str(planning_receipt.get("live_tau_condition_comparison_receipt", "")))
    action_receipt_path = Path(str(planning_receipt.get("live_tau_action_selection_receipt", "")))
    condition_receipt = _load_json(condition_receipt_path, errors, "condition_receipt") if str(condition_receipt_path) else {}
    action_receipt = _load_json(action_receipt_path, errors, "action_receipt") if str(action_receipt_path) else {}
    condition_receipt = condition_receipt if isinstance(condition_receipt, dict) else {}
    action_receipt = action_receipt if isinstance(action_receipt, dict) else {}

    case_index_path_value = condition_receipt.get("case_index_path")
    action_index_path_value = action_receipt.get("decision_index")
    case_index = _load_json(Path(str(case_index_path_value)), errors, "condition_case_index") if isinstance(case_index_path_value, str) else None
    action_index = _load_json(Path(str(action_index_path_value)), errors, "action_decision_index") if isinstance(action_index_path_value, str) else None
    if not isinstance(case_index, list):
        errors.append("condition_case_index_not_list")
        case_index = []
    if not isinstance(action_index, list):
        errors.append("action_decision_index_not_list")
        action_index = []

    rows = rule_module._build_rows(
        base_root=planning_root,
        case_index=case_index,
        action_index=action_index,
        threshold=cooperation_threshold,
        errors=errors,
    )
    summary = rule_module._summarize(
        rows,
        bootstrap_samples=bootstrap_samples,
        bootstrap_seed=bootstrap_seed,
        alpha=alpha,
    )

    variants = [_episode_variant(str(row.get("episode_id"))) for row in rows]
    valid_variants = [variant for variant in variants if variant is not None]
    expected_episodes = family_episode_limit * len(balanced.FAMILIES)
    expected_cases = expected_episodes * len(CONDITIONS)
    exposure_rows = [
        row
        for row in rows
        if row.get("cd_original_action") == "OFFER_COOPERATION"
        and row.get("cd_pre_outcome_rule_inputs", {}).get("selected_from_predicted_counterpart_action") == "KAI_OFFERS_COOPERATION"
    ]
    cooperation_outcome_rows = [row for row in rows if _coordination_cooperation_outcome_variant(str(row.get("episode_id")))]
    disjoint_from_derivation_and_full64 = bool(valid_variants) and min(valid_variants) >= 23 and variant_min >= 23
    no_oracle_rule_inputs = all(
        row.get("cd_pre_outcome_rule_inputs", {}).get("uses_outcome_or_oracle") is False for row in rows
    )
    live_tau_cases = planning_receipt.get("tau_live_call_performed")
    live_tau_reexecuted = reuse_planning_root is None

    checks = {
        "derivation_receipt_passed": derivation_receipt.get("status") == rule_module.DERIVATION_PASS_STATUS,
        "planning_receipt_passed": planning_receipt.get("status") == balanced.PASS_STATUS,
        "heldout_variants_disjoint_from_full64_and_derivation": disjoint_from_derivation_and_full64,
        "expected_episode_count": len(rows) == expected_episodes,
        "expected_case_count": len(case_index) == expected_cases,
        "live_tau_cases_complete": live_tau_cases == expected_cases,
        "tau_receipts_hash_bound": condition_receipt.get("tau_receipts_hash_bound") is True,
        "no_oracle_or_outcome_inputs_in_rule": no_oracle_rule_inputs,
        "zero_unsupported_writes": all(derivation_receipt.get(key) == 0 for key in ZERO_WRITE_KEYS)
        and all(planning_receipt.get(key) == 0 for key in ZERO_WRITE_KEYS),
        "cooperation_outcome_candidate_present": len(cooperation_outcome_rows) > 0,
        "cd_offer_cooperation_exposure_present": len(exposure_rows) > 0,
    }
    for key, value in checks.items():
        if value is not True:
            errors.append(f"check_failed:{key}:{value}")

    conclusion = (
        "HELDOUT_COOPERATION_EXPOSURE_SCORED"
        if checks["cd_offer_cooperation_exposure_present"] and not errors
        else "HELDOUT_COOPERATION_OUTCOME_PRESENT_BUT_CD_NO_OFFER_EXPOSURE"
        if checks["cooperation_outcome_candidate_present"] and not checks["cd_offer_cooperation_exposure_present"]
        else "HELDOUT_COOPERATION_EXPOSURE_SLICE_FAILED_CLOSED"
    )

    artifact_rows = {
        "schema": "persona_dream.research.prospective_tom.cooperation_exposure_slice_rows.v1",
        "policy_id": POLICY_ID,
        "variant_min": variant_min,
        "variant_max": variant_max,
        "rows": rows,
        "exposure_rows": exposure_rows,
        "cooperation_outcome_rows": cooperation_outcome_rows,
    }
    artifact_summary = {
        "schema": "persona_dream.research.prospective_tom.cooperation_exposure_slice_summary.v1",
        "policy_id": POLICY_ID,
        "variant_min": variant_min,
        "variant_max": variant_max,
        "family_episode_limit": family_episode_limit,
        "episodes_per_family": episodes_per_family,
        **summary,
        "cooperation_outcome_rows": len(cooperation_outcome_rows),
        "exposure_rows": len(exposure_rows),
        "conclusion": conclusion,
    }
    _write_json(rows_path, artifact_rows)
    _write_json(summary_path, artifact_summary)

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_tau_cooperation_exposure_slice_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "policy_id": POLICY_ID,
        "cooperation_probability_threshold": cooperation_threshold,
        "variant_min": variant_min,
        "variant_max": variant_max,
        "family_episode_limit": family_episode_limit,
        "episodes_per_family": episodes_per_family,
        "derivation_receipt": str(derivation_receipt_path),
        "derivation_receipt_sha256": _file_sha256(derivation_receipt_path) if derivation_receipt_path.exists() else None,
        "planning_root": str(planning_root),
        "planning_receipt": str(_planning_receipt_path(planning_root)),
        "planning_receipt_sha256": _file_sha256(_planning_receipt_path(planning_root))
        if _planning_receipt_path(planning_root).exists()
        else None,
        "rows_path": str(rows_path),
        "rows_sha256": _file_sha256(rows_path) if rows_path.exists() else None,
        "summary_path": str(summary_path),
        "summary_sha256": _file_sha256(summary_path) if summary_path.exists() else None,
        "mocked": False,
        "live": planning_receipt.get("live") is True,
        "fixture_backed": False,
        "deterministic_simulator_corpus_fixture_backed": True,
        "live_tau_reexecuted_by_this_command": live_tau_reexecuted,
        "live_tau_originated_artifacts_consumed": planning_receipt.get("live_tau_originated_artifacts_consumed") is True,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "tau_call_attempts": planning_receipt.get("tau_call_attempts"),
        "tau_live_call_performed": planning_receipt.get("tau_live_call_performed"),
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "checks": checks,
        "counts": {
            "rows": len(rows),
            "cases": len(case_index),
            "cooperation_outcome_rows": len(cooperation_outcome_rows),
            "cd_offer_cooperation_candidates": summary["cd_offer_cooperation_candidates"],
            "cd_low_confidence_cooperation_interventions": summary["cd_low_confidence_cooperation_interventions"],
            "cd_action_change_count": summary["cd_action_change_count"],
        },
        "metrics": {
            "original_mean_cd_minus_baseline_planning_regret": summary["original_mean_cd_minus_baseline_planning_regret"],
            "intervened_mean_cd_minus_baseline_planning_regret": summary["intervened_mean_cd_minus_baseline_planning_regret"],
            "mean_improvement_vs_original": summary["mean_improvement_vs_original"],
            "intervened_planning_regret_ci": summary["intervened_planning_regret_ci"],
            "improvement_ci": summary["improvement_ci"],
            "original_direction_counts": summary["original_direction_counts"],
            "intervened_direction_counts": summary["intervened_direction_counts"],
        },
        "planning_benefit_with_confidence": rule_module._planning_benefit_with_confidence(summary["intervened_planning_regret_ci"]),
        "slice_conclusion": conclusion,
        "errors": errors,
        "claims": {
            "proves": [
                "a held-out variant slice disjoint from full64 and derivation variants was run through live Tau M/R/D/CD planning",
                "the pre-outcome cooperation threshold rule was applied only to sealed prediction and action-selection fields",
                "cooperation-exposure rows were scored with deterministic Gate 6 planning-regret utilities",
                "no human content judgment, LLM judge, Memory write, provider call, canonical write, identity write, or source-memory write was attempted",
            ]
            if status == PASS_STATUS
            else [
                "the cooperation-exposure slice failed closed before accepting a planning-benefit claim",
            ],
            "does_not_prove": [
                "broad held-out planning benefit",
                "confidence-bounded CD planning benefit",
                "semantic dream quality",
                "paid provider execution",
                "complete live Phase 01-16 runtime execution",
                "that the cooperation threshold is optimal",
            ],
        },
    }
    receipt["receipt_sha256"] = _stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--derivation-receipt", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--variant-min", type=int, default=23)
    parser.add_argument("--variant-max", type=int, default=24)
    parser.add_argument("--family-episode-limit", type=int, default=2)
    parser.add_argument("--episodes-per-family", type=int, default=24)
    parser.add_argument("--cooperation-threshold", type=float, default=0.5)
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout-s", type=float, default=240.0)
    parser.add_argument("--outer-timeout-s", type=float, default=None)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--bootstrap-seed", type=int, default=20721023)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--reuse-planning-root", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "live_tau_cooperation_exposure_slice_receipt.v1.json")
    receipt = run_slice(
        derivation_receipt_path=args.derivation_receipt,
        output_root=args.output_root,
        receipt_out=receipt_out,
        variant_min=args.variant_min,
        variant_max=args.variant_max,
        family_episode_limit=args.family_episode_limit,
        episodes_per_family=args.episodes_per_family,
        cooperation_threshold=args.cooperation_threshold,
        model=args.model,
        timeout_s=args.timeout_s,
        outer_timeout_s=args.outer_timeout_s,
        bootstrap_samples=args.bootstrap_samples,
        bootstrap_seed=args.bootstrap_seed,
        alpha=args.alpha,
        reuse_planning_root=args.reuse_planning_root,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
