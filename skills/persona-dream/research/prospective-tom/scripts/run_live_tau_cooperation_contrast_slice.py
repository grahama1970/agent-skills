#!/usr/bin/env python3
"""Run the deterministic cooperation-contrast instrument through live Tau."""
from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
RESEARCH_ROOT = ROOT / "research" / "prospective-tom"
CONTRAST_SCRIPT = RESEARCH_ROOT / "scripts" / "check_cooperation_contrast_instrument.py"
CONDITION_SCRIPT = RESEARCH_ROOT / "scripts" / "run_live_tau_condition_comparison.py"
ACTION_SCRIPT = RESEARCH_ROOT / "scripts" / "run_live_tau_condition_action_selection.py"
RULE_SCRIPT = RESEARCH_ROOT / "scripts" / "run_live_tau_cooperation_threshold_rule.py"
PASS_STATUS = "PASS_LIVE_TAU_PCTOM_COOPERATION_CONTRAST_SLICE"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_COOPERATION_CONTRAST_SLICE"
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


def _validate_zero_writes(receipt: dict[str, Any], errors: list[str], label: str) -> None:
    for key in ZERO_WRITE_KEYS:
        if receipt.get(key) != 0:
            errors.append(f"{label}_{key}_not_zero:{receipt.get(key)}")


def _run_or_load_contrast(
    *,
    contrast: Any,
    output_root: Path,
    receipt_path: Path,
    reuse_contrast_receipt: Path | None,
    prefix: str,
    variant_start: int,
    pair_count: int,
    errors: list[str],
) -> dict[str, Any]:
    if reuse_contrast_receipt is not None:
        receipt = _load_json(reuse_contrast_receipt.resolve(), errors, "reuse_contrast_receipt")
        return receipt if isinstance(receipt, dict) else {}
    try:
        return contrast.run_check(
            output_root=output_root,
            receipt_out=receipt_path,
            prefix=prefix,
            variant_start=variant_start,
            pair_count=pair_count,
        )
    except Exception as exc:
        errors.append(f"contrast_instrument_exception:{type(exc).__name__}:{exc}")
        receipt = _load_json(receipt_path, errors, "contrast_receipt_after_exception")
        return receipt if isinstance(receipt, dict) else {}


def _contrast_rows(corpus_path: Path, errors: list[str]) -> dict[str, str]:
    corpus = _load_json(corpus_path, errors, "contrast_corpus")
    if not isinstance(corpus, dict) or not isinstance(corpus.get("episodes"), list):
        errors.append("contrast_corpus_episodes_not_list")
        return {}
    rows: dict[str, str] = {}
    for idx, episode in enumerate(corpus["episodes"]):
        if not isinstance(episode, dict):
            errors.append(f"contrast_episode_{idx}_not_object")
            continue
        episode_id = episode.get("episode_id")
        hidden = episode.get("hidden_world_state") if isinstance(episode.get("hidden_world_state"), dict) else {}
        contrast_class = hidden.get("contrast_class")
        if not isinstance(episode_id, str) or not isinstance(contrast_class, str):
            errors.append(f"contrast_episode_{idx}_missing_id_or_class")
            continue
        rows[episode_id] = contrast_class
    return rows


def _contrast_metadata(corpus_path: Path, errors: list[str]) -> dict[str, dict[str, Any]]:
    corpus = _load_json(corpus_path, errors, "contrast_corpus_for_metadata")
    if not isinstance(corpus, dict) or not isinstance(corpus.get("episodes"), list):
        errors.append("contrast_metadata_corpus_episodes_not_list")
        return {}
    metadata: dict[str, dict[str, Any]] = {}
    for idx, episode in enumerate(corpus["episodes"]):
        if not isinstance(episode, dict):
            errors.append(f"contrast_metadata_episode_{idx}_not_object")
            continue
        episode_id = episode.get("episode_id")
        hidden = episode.get("hidden_world_state") if isinstance(episode.get("hidden_world_state"), dict) else {}
        if not isinstance(episode_id, str):
            errors.append(f"contrast_metadata_episode_{idx}_missing_episode_id")
            continue
        metadata[episode_id] = {
            "variant": episode.get("variant"),
            "contrast_class": hidden.get("contrast_class"),
        }
    return metadata


def _attach_contrast_metadata(rows: list[dict[str, Any]], metadata: dict[str, dict[str, Any]]) -> None:
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_metadata = metadata.get(str(row.get("episode_id")), {})
        row["variant"] = row_metadata.get("variant")
        row["contrast_class"] = row_metadata.get("contrast_class")
        condition_rows = row.get("condition_rows")
        if isinstance(condition_rows, dict):
            for condition_row in condition_rows.values():
                if isinstance(condition_row, dict):
                    condition_row["variant"] = row_metadata.get("variant")
                    condition_row["contrast_class"] = row_metadata.get("contrast_class")


def _summarize_rule_rows(
    rows: list[dict[str, Any]],
    *,
    rule: Any,
    bootstrap_samples: int,
    bootstrap_seed: int,
    alpha: float,
) -> dict[str, Any]:
    original_deltas = [float(row["original_cd_minus_baseline_planning_regret"]) for row in rows]
    intervened_deltas = [float(row["intervened_cd_minus_baseline_planning_regret"]) for row in rows]
    improvement_deltas = [original - intervened for original, intervened in zip(original_deltas, intervened_deltas)]
    cd_offer_candidates = [
        row
        for row in rows
        if row["cd_original_action"] == "OFFER_COOPERATION"
        and row["cd_pre_outcome_rule_inputs"].get("selected_from_predicted_counterpart_action") == "KAI_OFFERS_COOPERATION"
    ]
    changed_rows = [row for row in rows if row["cd_action_changed_by_rule"]]
    variants = [row.get("variant") for row in rows if isinstance(row.get("variant"), int)]
    return {
        "rows": len(rows),
        "variant_min": min(variants) if variants else None,
        "variant_max": max(variants) if variants else None,
        "cd_offer_cooperation_candidates": len(cd_offer_candidates),
        "cd_low_confidence_cooperation_interventions": len(changed_rows),
        "cd_action_change_count": len(changed_rows),
        "original_direction_counts": dict(collections.Counter(row["original_direction"] for row in rows)),
        "intervened_direction_counts": dict(collections.Counter(row["intervened_direction"] for row in rows)),
        "original_mean_cd_minus_baseline_planning_regret": rule._mean(original_deltas),
        "intervened_mean_cd_minus_baseline_planning_regret": rule._mean(intervened_deltas),
        "mean_improvement_vs_original": rule._mean(improvement_deltas),
        "intervened_planning_regret_ci": rule._bootstrap_ci(
            intervened_deltas,
            samples=bootstrap_samples,
            seed=bootstrap_seed,
            alpha=alpha,
        ),
        "improvement_ci": rule._bootstrap_ci(
            improvement_deltas,
            samples=bootstrap_samples,
            seed=bootstrap_seed + 1,
            alpha=alpha,
        ),
        "changed_rows": changed_rows,
    }


def _summarize_contrast_exposure(rows: list[dict[str, Any]], contrast_by_episode: dict[str, str]) -> dict[str, Any]:
    summary = {
        "rows_by_contrast_class": {},
        "cd_offer_candidates_by_contrast_class": {},
        "cd_action_changes_by_contrast_class": {},
        "cd_original_actions_by_contrast_class": {},
        "cd_intervened_actions_by_contrast_class": {},
    }
    for row in rows:
        if not isinstance(row, dict):
            continue
        contrast_class = contrast_by_episode.get(str(row.get("episode_id")), "UNKNOWN")
        summary["rows_by_contrast_class"][contrast_class] = summary["rows_by_contrast_class"].get(contrast_class, 0) + 1
        if row.get("cd_original_action") == "OFFER_COOPERATION":
            summary["cd_offer_candidates_by_contrast_class"][contrast_class] = (
                summary["cd_offer_candidates_by_contrast_class"].get(contrast_class, 0) + 1
            )
        if row.get("cd_action_changed_by_rule") is True:
            summary["cd_action_changes_by_contrast_class"][contrast_class] = (
                summary["cd_action_changes_by_contrast_class"].get(contrast_class, 0) + 1
            )
        original = row.get("cd_original_action")
        intervened = row.get("cd_intervened_action")
        if isinstance(original, str):
            bucket = summary["cd_original_actions_by_contrast_class"].setdefault(contrast_class, {})
            bucket[original] = bucket.get(original, 0) + 1
        if isinstance(intervened, str):
            bucket = summary["cd_intervened_actions_by_contrast_class"].setdefault(contrast_class, {})
            bucket[intervened] = bucket.get(intervened, 0) + 1
    return summary


def run_slice(
    *,
    derivation_receipt_path: Path,
    output_root: Path,
    receipt_out: Path,
    prefix: str,
    variant_start: int,
    pair_count: int,
    cooperation_threshold: float,
    model: str | None,
    timeout_s: float,
    preflight_timeout_s: float | None,
    bootstrap_samples: int,
    bootstrap_seed: int,
    alpha: float,
    reuse_contrast_receipt: Path | None = None,
    reuse_condition_root: Path | None = None,
    reuse_action_root: Path | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    derivation_receipt_path = derivation_receipt_path.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    contrast_root = output_root / "cooperation_contrast_instrument"
    condition_root = reuse_condition_root.resolve() if reuse_condition_root is not None else output_root / "live_tau_condition_comparison"
    action_root = reuse_action_root.resolve() if reuse_action_root is not None else output_root / "live_tau_condition_action_selection"
    artifacts_root = output_root / "artifacts"
    rows_path = artifacts_root / "cooperation_contrast_slice_rows.json"
    summary_path = artifacts_root / "cooperation_contrast_slice_summary.json"
    errors: list[str] = []

    contrast = _load_module(CONTRAST_SCRIPT, "pctom_cooperation_contrast_instrument")
    condition = _load_module(CONDITION_SCRIPT, "pctom_live_tau_condition_comparison")
    action = _load_module(ACTION_SCRIPT, "pctom_live_tau_condition_action_selection")
    rule = _load_module(RULE_SCRIPT, "pctom_live_tau_cooperation_threshold_rule")

    derivation_receipt = _load_json(derivation_receipt_path, errors, "derivation_receipt")
    derivation_receipt = derivation_receipt if isinstance(derivation_receipt, dict) else {}
    rule._validate_derivation(derivation_receipt, errors)

    contrast_receipt_path = contrast_root / "cooperation_contrast_instrument_receipt.v1.json"
    contrast_receipt = _run_or_load_contrast(
        contrast=contrast,
        output_root=contrast_root,
        receipt_path=contrast_receipt_path,
        reuse_contrast_receipt=reuse_contrast_receipt,
        prefix=prefix,
        variant_start=variant_start,
        pair_count=pair_count,
        errors=errors,
    )
    if contrast_receipt.get("status") != contrast.PASS_STATUS:
        errors.append(f"contrast_status_not_pass:{contrast_receipt.get('status')}")
        errors.extend(f"contrast_error:{error}" for error in contrast_receipt.get("errors", []))
    corpus_path_value = contrast_receipt.get("corpus_path")
    corpus_path = (
        Path(str(corpus_path_value))
        if isinstance(corpus_path_value, str)
        else contrast_root / "artifacts" / "cooperation_contrast_instrument_corpus.v1.json"
    )

    condition_receipt_path = condition_root / "live_tau_condition_comparison_receipt.v1.json"
    if reuse_condition_root is not None:
        condition_receipt = _load_json(condition_receipt_path, errors, "reuse_condition_receipt")
        condition_receipt = condition_receipt if isinstance(condition_receipt, dict) else {}
    elif not errors:
        condition_receipt = condition.run_live_comparison(
            output_root=condition_root,
            receipt_out=condition_receipt_path,
            split="contrast",
            episodes_per_family=pair_count * 2,
            episode_limit=pair_count * 2,
            model=model,
            timeout_s=timeout_s,
            preflight_timeout_s=preflight_timeout_s,
            gate0_case_root=None,
            corpus_path_override=corpus_path,
        )
    else:
        condition_receipt = {}

    if condition_receipt.get("status") != condition.PASS_STATUS:
        errors.append(f"condition_status_not_pass:{condition_receipt.get('status')}")
        errors.extend(f"condition_error:{error}" for error in condition_receipt.get("errors", []))

    action_receipt_path = action_root / "live_tau_condition_action_selection_receipt.v1.json"
    if reuse_action_root is not None:
        action_receipt = _load_json(action_receipt_path, errors, "reuse_action_receipt")
        action_receipt = action_receipt if isinstance(action_receipt, dict) else {}
    elif condition_receipt.get("status") == condition.PASS_STATUS:
        action_receipt = action.run_bridge(
            base_root=condition_root,
            output_root=action_root,
            receipt_out=action_receipt_path,
        )
    else:
        action_receipt = {}

    if action_receipt.get("status") != action.PASS_STATUS:
        errors.append(f"action_status_not_pass:{action_receipt.get('status')}")
        errors.extend(f"action_error:{error}" for error in action_receipt.get("errors", []))

    case_index_path_value = condition_receipt.get("case_index_path")
    action_index_path_value = action_receipt.get("decision_index")
    case_index = (
        _load_json(Path(str(case_index_path_value)), errors, "condition_case_index")
        if isinstance(case_index_path_value, str)
        else None
    )
    action_index = (
        _load_json(Path(str(action_index_path_value)), errors, "action_decision_index")
        if isinstance(action_index_path_value, str)
        else None
    )
    if not isinstance(case_index, list):
        errors.append("condition_case_index_not_list")
        case_index = []
    if not isinstance(action_index, list):
        errors.append("action_decision_index_not_list")
        action_index = []

    rows = rule._build_rows(
        base_root=condition_root,
        case_index=case_index,
        action_index=action_index,
        threshold=cooperation_threshold,
        errors=errors,
    )
    contrast_metadata = _contrast_metadata(corpus_path, errors)
    _attach_contrast_metadata(rows, contrast_metadata)
    summary = _summarize_rule_rows(
        rows,
        rule=rule,
        bootstrap_samples=bootstrap_samples,
        bootstrap_seed=bootstrap_seed,
        alpha=alpha,
    )
    expected_episode_count = pair_count * 2
    expected_cases = expected_episode_count * len(CONDITIONS)
    expected_variants = list(range(variant_start, variant_start + expected_episode_count))
    variants = sorted(row.get("variant") for row in rows if isinstance(row.get("variant"), int))
    contrast_counts = contrast_receipt.get("counts") if isinstance(contrast_receipt.get("counts"), dict) else {}
    keep_rows = contrast_counts.get("keep_cooperation_positive_rows")
    avoid_rows = contrast_counts.get("avoid_or_unsafe_cooperation_contrast_rows")
    contrast_by_episode = {
        episode_id: str(metadata.get("contrast_class"))
        for episode_id, metadata in contrast_metadata.items()
        if isinstance(metadata.get("contrast_class"), str)
    }
    contrast_summary = _summarize_contrast_exposure(rows, contrast_by_episode)
    cd_offer_candidates = int(summary.get("cd_offer_cooperation_candidates") or 0)
    avoid_offer_candidates = int(
        contrast_summary.get("cd_offer_candidates_by_contrast_class", {}).get(
            "AVOID_OR_UNSAFE_COOPERATION_CONTRAST", 0
        )
        or 0
    )
    keep_offer_candidates = int(
        contrast_summary.get("cd_offer_candidates_by_contrast_class", {}).get("KEEP_COOPERATION_POSITIVE", 0)
        or 0
    )
    if avoid_offer_candidates > 0 and keep_offer_candidates > 0:
        conclusion = "CONTRAST_SLICE_HAS_KEEP_AND_AVOID_CD_OFFER_EXPOSURE"
    elif cd_offer_candidates > 0:
        conclusion = "CONTRAST_SLICE_PARTIAL_CD_OFFER_EXPOSURE"
    else:
        conclusion = "CONTRAST_SLICE_LIVE_TAU_NO_CD_OFFER_EXPOSURE"

    _write_json(
        rows_path,
        {
            "schema": "persona_dream.research.prospective_tom.cooperation_contrast_slice_rows.v1",
            "policy_id": POLICY_ID,
            "corpus_path": str(corpus_path),
            "contrast_by_episode": contrast_by_episode,
            "rows": rows,
        },
    )
    _write_json(
        summary_path,
        {
            "schema": "persona_dream.research.prospective_tom.cooperation_contrast_slice_summary.v1",
            "policy_id": POLICY_ID,
            "corpus_path": str(corpus_path),
            "variant_start": variant_start,
            "pair_count": pair_count,
            "episode_count": expected_episode_count,
            **summary,
            "contrast_summary": contrast_summary,
            "keep_cooperation_positive_rows": keep_rows,
            "avoid_or_unsafe_cooperation_contrast_rows": avoid_rows,
            "conclusion": conclusion,
        },
    )

    _validate_zero_writes(derivation_receipt, errors, "derivation")
    _validate_zero_writes(contrast_receipt, errors, "contrast")
    _validate_zero_writes(condition_receipt, errors, "condition")
    _validate_zero_writes(action_receipt, errors, "action")
    no_oracle_rule_inputs = all(
        row.get("cd_pre_outcome_rule_inputs", {}).get("uses_outcome_or_oracle") is False for row in rows
    )
    checks = {
        "derivation_receipt_passed": derivation_receipt.get("status") == rule.DERIVATION_PASS_STATUS,
        "contrast_receipt_passed": contrast_receipt.get("status") == contrast.PASS_STATUS,
        "contrast_keep_rows_present": keep_rows == pair_count,
        "contrast_avoid_rows_present": avoid_rows == pair_count,
        "condition_receipt_passed": condition_receipt.get("status") == condition.PASS_STATUS,
        "condition_used_external_contrast_corpus": condition_receipt.get("external_corpus_used") is True
        and condition_receipt.get("external_corpus_path") == str(corpus_path.resolve()),
        "action_receipt_passed": action_receipt.get("status") == action.PASS_STATUS,
        "expected_case_count": len(case_index) == expected_cases,
        "expected_action_count": len(action_index) == expected_cases,
        "expected_row_count": len(rows) == expected_episode_count,
        "expected_variants": variants == expected_variants,
        "tau_receipts_hash_bound": condition_receipt.get("tau_receipts_hash_bound") is True,
        "live_tau_cases_complete": condition_receipt.get("tau_live_call_performed") == expected_cases,
        "no_oracle_or_outcome_inputs_in_rule": no_oracle_rule_inputs,
        "zero_unsupported_writes": all(
            receipt.get(key) == 0
            for receipt in (derivation_receipt, contrast_receipt, condition_receipt, action_receipt)
            for key in ZERO_WRITE_KEYS
        ),
    }
    for key, value in checks.items():
        if value is not True:
            errors.append(f"check_failed:{key}:{value}")

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    contrast_receipt_path_for_hash = (
        contrast_receipt_path if reuse_contrast_receipt is None else reuse_contrast_receipt.resolve()
    )
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_tau_cooperation_contrast_slice_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "policy_id": POLICY_ID,
        "cooperation_probability_threshold": cooperation_threshold,
        "derivation_receipt": str(derivation_receipt_path),
        "derivation_receipt_sha256": _file_sha256(derivation_receipt_path) if derivation_receipt_path.exists() else None,
        "contrast_receipt": str(contrast_receipt_path_for_hash),
        "contrast_receipt_sha256": _file_sha256(contrast_receipt_path_for_hash)
        if contrast_receipt_path_for_hash.exists()
        else None,
        "condition_receipt": str(condition_receipt_path),
        "condition_receipt_sha256": _file_sha256(condition_receipt_path) if condition_receipt_path.exists() else None,
        "action_receipt": str(action_receipt_path),
        "action_receipt_sha256": _file_sha256(action_receipt_path) if action_receipt_path.exists() else None,
        "rows_path": str(rows_path),
        "rows_sha256": _file_sha256(rows_path) if rows_path.exists() else None,
        "summary_path": str(summary_path),
        "summary_sha256": _file_sha256(summary_path) if summary_path.exists() else None,
        "mocked": False,
        "live": condition_receipt.get("live") is True,
        "fixture_backed": False,
        "deterministic_simulator_corpus": True,
        "live_tau_reexecuted_by_this_command": reuse_condition_root is None,
        "live_tau_originated_artifacts_consumed": action_receipt.get("live_tau_originated_artifacts_consumed") is True,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "tau_call_attempts": condition_receipt.get("tau_call_attempts"),
        "tau_live_call_performed": condition_receipt.get("tau_live_call_performed"),
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "checks": checks,
        "counts": {
            "contrast_episodes": expected_episode_count,
            "keep_cooperation_positive_rows": keep_rows,
            "avoid_or_unsafe_cooperation_contrast_rows": avoid_rows,
            "cases": len(case_index),
            "action_cases": len(action_index),
            "rows": len(rows),
            "cd_offer_cooperation_candidates": cd_offer_candidates,
            "cd_offer_keep_candidates": keep_offer_candidates,
            "cd_offer_avoid_or_unsafe_candidates": avoid_offer_candidates,
            "cd_low_confidence_cooperation_interventions": summary.get("cd_low_confidence_cooperation_interventions"),
            "cd_action_change_count": summary.get("cd_action_change_count"),
        },
        "contrast_summary": contrast_summary,
        "metrics": {
            "original_mean_cd_minus_baseline_planning_regret": summary.get("original_mean_cd_minus_baseline_planning_regret"),
            "intervened_mean_cd_minus_baseline_planning_regret": summary.get("intervened_mean_cd_minus_baseline_planning_regret"),
            "mean_improvement_vs_original": summary.get("mean_improvement_vs_original"),
            "intervened_planning_regret_ci": summary.get("intervened_planning_regret_ci"),
            "improvement_ci": summary.get("improvement_ci"),
            "original_direction_counts": summary.get("original_direction_counts"),
            "intervened_direction_counts": summary.get("intervened_direction_counts"),
        },
        "planning_benefit_with_confidence": rule._planning_benefit_with_confidence(summary["intervened_planning_regret_ci"]),
        "slice_conclusion": conclusion,
        "errors": errors,
        "claims": {
            "proves": [
                "the deterministic cooperation-contrast corpus was consumed by the live Tau M/R/D/CD condition runner",
                "contrast cases were sealed before deterministic outcome reveal and then passed through Gate 6 action scoring",
                "the pre-outcome cooperation threshold rule used sealed prediction/action fields and did not use outcome or oracle fields as rule inputs",
                "no human content judgment, LLM judge, Memory write, provider call, canonical write, identity write, or source-memory write was attempted",
            ]
            if status == PASS_STATUS
            else [
                "the cooperation contrast live Tau slice failed closed before accepting a planning-benefit claim",
            ],
            "does_not_prove": [
                "a replacement cooperation feature split is valid",
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
    parser.add_argument("--prefix", default="instr")
    parser.add_argument("--variant-start", type=int, default=29)
    parser.add_argument("--pair-count", type=int, default=4)
    parser.add_argument("--cooperation-threshold", type=float, default=0.5)
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout-s", type=float, default=240.0)
    parser.add_argument("--preflight-timeout-s", type=float, default=None)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--bootstrap-seed", type=int, default=20721029)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--reuse-contrast-receipt", type=Path, default=None)
    parser.add_argument("--reuse-condition-root", type=Path, default=None)
    parser.add_argument("--reuse-action-root", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "live_tau_cooperation_contrast_slice_receipt.v1.json")
    receipt = run_slice(
        derivation_receipt_path=args.derivation_receipt,
        output_root=args.output_root,
        receipt_out=receipt_out,
        prefix=args.prefix,
        variant_start=args.variant_start,
        pair_count=args.pair_count,
        cooperation_threshold=args.cooperation_threshold,
        model=args.model,
        timeout_s=args.timeout_s,
        preflight_timeout_s=args.preflight_timeout_s,
        bootstrap_samples=args.bootstrap_samples,
        bootstrap_seed=args.bootstrap_seed,
        alpha=args.alpha,
        reuse_contrast_receipt=args.reuse_contrast_receipt,
        reuse_condition_root=args.reuse_condition_root,
        reuse_action_root=args.reuse_action_root,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
