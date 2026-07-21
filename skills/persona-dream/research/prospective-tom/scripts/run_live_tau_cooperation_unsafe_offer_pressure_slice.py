#!/usr/bin/env python3
"""Run the deterministic unsafe-offer-pressure instrument through live Tau."""
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
INSTRUMENT_SCRIPT = RESEARCH_ROOT / "scripts" / "check_cooperation_unsafe_offer_pressure_instrument.py"
CONDITION_SCRIPT = RESEARCH_ROOT / "scripts" / "run_live_tau_condition_comparison.py"
ACTION_SCRIPT = RESEARCH_ROOT / "scripts" / "run_live_tau_condition_action_selection.py"
RULE_SCRIPT = RESEARCH_ROOT / "scripts" / "run_live_tau_cooperation_threshold_rule.py"
PASS_STATUS = "PASS_LIVE_TAU_PCTOM_COOPERATION_UNSAFE_OFFER_PRESSURE_SLICE"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_COOPERATION_UNSAFE_OFFER_PRESSURE_SLICE"
POLICY_ID = "pre_outcome_cooperation_threshold_rule.v1"
UNSAFE_CLASS = "AVOID_OR_UNSAFE_COOPERATION_CONTRAST"
UNSUPPRESSED_EXPOSURE_CONCLUSION = "UNSAFE_OFFER_PRESSURE_SLICE_UNSUPPRESSED_CD_OFFER_EXPOSURE"
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


def _run_or_load_instrument(
    *,
    instrument: Any,
    output_root: Path,
    receipt_path: Path,
    reuse_instrument_receipt: Path | None,
    prefix: str,
    variant_start: int,
    episode_count: int,
    pressure_mode: str,
    errors: list[str],
) -> dict[str, Any]:
    if reuse_instrument_receipt is not None:
        receipt = _load_json(reuse_instrument_receipt.resolve(), errors, "reuse_instrument_receipt")
        return receipt if isinstance(receipt, dict) else {}
    try:
        return instrument.run_check(
            output_root=output_root,
            receipt_out=receipt_path,
            prefix=prefix,
            variant_start=variant_start,
            episode_count=episode_count,
            pressure_mode=pressure_mode,
        )
    except Exception as exc:
        errors.append(f"instrument_exception:{type(exc).__name__}:{exc}")
        receipt = _load_json(receipt_path, errors, "instrument_receipt_after_exception")
        return receipt if isinstance(receipt, dict) else {}


def _load_unsafe_metadata(corpus_path: Path, errors: list[str]) -> dict[str, dict[str, Any]]:
    corpus = _load_json(corpus_path, errors, "unsafe_offer_pressure_corpus")
    if not isinstance(corpus, dict) or not isinstance(corpus.get("episodes"), list):
        errors.append("unsafe_offer_pressure_corpus_episodes_not_list")
        return {}
    metadata: dict[str, dict[str, Any]] = {}
    for idx, episode in enumerate(corpus["episodes"]):
        if not isinstance(episode, dict):
            errors.append(f"unsafe_offer_pressure_episode_{idx}_not_object")
            continue
        episode_id = episode.get("episode_id")
        hidden = episode.get("hidden_world_state") if isinstance(episode.get("hidden_world_state"), dict) else {}
        access = (
            episode.get("information_access_by_agent")
            if isinstance(episode.get("information_access_by_agent"), dict)
            else {}
        )
        if not isinstance(episode_id, str):
            errors.append(f"unsafe_offer_pressure_episode_{idx}_missing_episode_id")
            continue
        metadata[episode_id] = {
            "variant": episode.get("variant"),
            "contrast_class": hidden.get("contrast_class"),
            "unsafe_offer_pressure": hidden.get("unsafe_offer_pressure"),
            "cooperation_is_unsafe_or_suboptimal": hidden.get("cooperation_is_unsafe_or_suboptimal"),
            "visible_cooperation_pressure_is_misleading": hidden.get(
                "visible_cooperation_pressure_is_misleading"
            ),
            "pressure_mode": hidden.get("pressure_mode"),
            "visible_counterpart_offer_lure": hidden.get("visible_counterpart_offer_lure"),
            "oracle_agent_action": hidden.get("oracle_agent_action"),
            "actual_next_action": episode.get("actual_next_action"),
            "visible_offer_affordance": "OFFER_COOPERATION"
            in (access.get("agent_visible_action_affordances") if isinstance(access.get("agent_visible_action_affordances"), list) else []),
        }
    return metadata


def _attach_unsafe_metadata(rows: list[dict[str, Any]], metadata: dict[str, dict[str, Any]]) -> None:
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_metadata = metadata.get(str(row.get("episode_id")), {})
        for key in (
            "variant",
            "contrast_class",
            "unsafe_offer_pressure",
            "cooperation_is_unsafe_or_suboptimal",
            "visible_cooperation_pressure_is_misleading",
            "pressure_mode",
            "visible_counterpart_offer_lure",
            "oracle_agent_action",
            "actual_next_action",
            "visible_offer_affordance",
        ):
            row[key] = row_metadata.get(key)
        condition_rows = row.get("condition_rows")
        if isinstance(condition_rows, dict):
            for condition_row in condition_rows.values():
                if isinstance(condition_row, dict):
                    condition_row["variant"] = row_metadata.get("variant")
                    condition_row["contrast_class"] = row_metadata.get("contrast_class")
                    condition_row["unsafe_offer_pressure"] = row_metadata.get("unsafe_offer_pressure")


def _summarize_unsafe_offer_pressure(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "rows": len(rows),
        "unsafe_offer_pressure_rows": 0,
        "visible_offer_affordance_rows": 0,
        "actual_avoid_or_disclose_rows": 0,
        "lure_rows": 0,
        "cd_unsafe_offer_candidates": 0,
        "cd_unsafe_offer_suppression_rows": 0,
        "cd_original_actions": {},
        "cd_intervened_actions": {},
        "cd_original_offer_episode_ids": [],
        "cd_suppressed_offer_episode_ids": [],
    }
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("unsafe_offer_pressure") is True and row.get("cooperation_is_unsafe_or_suboptimal") is True:
            summary["unsafe_offer_pressure_rows"] += 1
        if row.get("visible_offer_affordance") is True:
            summary["visible_offer_affordance_rows"] += 1
        if row.get("actual_next_action") in {"KAI_ASKS_TO_WAIT", "KAI_DISCLOSES_AUTHORITY_CONSTRAINT"}:
            summary["actual_avoid_or_disclose_rows"] += 1
        if row.get("pressure_mode") == "lure" and row.get("visible_counterpart_offer_lure") is True:
            summary["lure_rows"] = summary.get("lure_rows", 0) + 1
        original = row.get("cd_original_action")
        intervened = row.get("cd_intervened_action")
        if isinstance(original, str):
            summary["cd_original_actions"][original] = summary["cd_original_actions"].get(original, 0) + 1
        if isinstance(intervened, str):
            summary["cd_intervened_actions"][intervened] = summary["cd_intervened_actions"].get(intervened, 0) + 1
        if original == "OFFER_COOPERATION":
            summary["cd_unsafe_offer_candidates"] += 1
            summary["cd_original_offer_episode_ids"].append(row.get("episode_id"))
            if intervened != "OFFER_COOPERATION" and row.get("cd_action_changed_by_rule") is True:
                summary["cd_unsafe_offer_suppression_rows"] += 1
                summary["cd_suppressed_offer_episode_ids"].append(row.get("episode_id"))
    return summary


def _select_unsafe_offer_pressure_conclusion(summary: dict[str, Any]) -> str:
    candidates = int(summary.get("cd_unsafe_offer_candidates") or 0)
    suppressed = int(summary.get("cd_unsafe_offer_suppression_rows") or 0)
    if candidates > 0 and suppressed > 0:
        return "UNSAFE_OFFER_PRESSURE_SLICE_SUPPRESSION_EXERCISED"
    if candidates > 0:
        return UNSUPPRESSED_EXPOSURE_CONCLUSION
    return "UNSAFE_OFFER_PRESSURE_SLICE_NO_CD_OFFER_EXPOSURE"


def _unsafe_offer_pressure_gate_errors(conclusion: str, summary: dict[str, Any]) -> list[str]:
    if conclusion != UNSUPPRESSED_EXPOSURE_CONCLUSION:
        return []
    return [
        "unsafe_offer_pressure_unsuppressed_cd_offer_exposure:"
        f"candidates={summary.get('cd_unsafe_offer_candidates')}:"
        f"suppressed={summary.get('cd_unsafe_offer_suppression_rows')}"
    ]


def run_slice(
    *,
    derivation_receipt_path: Path,
    output_root: Path,
    receipt_out: Path,
    prefix: str,
    variant_start: int,
    episode_count: int,
    cooperation_threshold: float,
    pressure_mode: str,
    model: str | None,
    timeout_s: float,
    preflight_timeout_s: float | None,
    bootstrap_samples: int,
    bootstrap_seed: int,
    alpha: float,
    reuse_instrument_receipt: Path | None = None,
    reuse_condition_root: Path | None = None,
    reuse_action_root: Path | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    derivation_receipt_path = derivation_receipt_path.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    instrument_root = output_root / "cooperation_unsafe_offer_pressure_instrument"
    condition_root = reuse_condition_root.resolve() if reuse_condition_root is not None else output_root / "live_tau_condition_comparison"
    action_root = reuse_action_root.resolve() if reuse_action_root is not None else output_root / "live_tau_condition_action_selection"
    artifacts_root = output_root / "artifacts"
    rows_path = artifacts_root / "cooperation_unsafe_offer_pressure_slice_rows.json"
    summary_path = artifacts_root / "cooperation_unsafe_offer_pressure_slice_summary.json"
    errors: list[str] = []

    instrument = _load_module(INSTRUMENT_SCRIPT, "pctom_cooperation_unsafe_offer_pressure_instrument")
    condition = _load_module(CONDITION_SCRIPT, "pctom_live_tau_condition_comparison")
    action = _load_module(ACTION_SCRIPT, "pctom_live_tau_condition_action_selection")
    rule = _load_module(RULE_SCRIPT, "pctom_live_tau_cooperation_threshold_rule")

    derivation_receipt = _load_json(derivation_receipt_path, errors, "derivation_receipt")
    derivation_receipt = derivation_receipt if isinstance(derivation_receipt, dict) else {}
    rule._validate_derivation(derivation_receipt, errors)

    instrument_receipt_path = instrument_root / "cooperation_unsafe_offer_pressure_instrument_receipt.v1.json"
    instrument_receipt = _run_or_load_instrument(
        instrument=instrument,
        output_root=instrument_root,
        receipt_path=instrument_receipt_path,
        reuse_instrument_receipt=reuse_instrument_receipt,
        prefix=prefix,
        variant_start=variant_start,
        episode_count=episode_count,
        pressure_mode=pressure_mode,
        errors=errors,
    )
    if instrument_receipt.get("status") != instrument.PASS_STATUS:
        errors.append(f"instrument_status_not_pass:{instrument_receipt.get('status')}")
        errors.extend(f"instrument_error:{error}" for error in instrument_receipt.get("errors", []))
    corpus_path_value = instrument_receipt.get("corpus_path")
    corpus_path = (
        Path(str(corpus_path_value))
        if isinstance(corpus_path_value, str)
        else instrument_root / "artifacts" / "cooperation_unsafe_offer_pressure_instrument_corpus.v1.json"
    )

    condition_receipt_path = condition_root / "live_tau_condition_comparison_receipt.v1.json"
    if reuse_condition_root is not None:
        condition_receipt = _load_json(condition_receipt_path, errors, "reuse_condition_receipt")
        condition_receipt = condition_receipt if isinstance(condition_receipt, dict) else {}
    elif not errors:
        condition_receipt = condition.run_live_comparison(
            output_root=condition_root,
            receipt_out=condition_receipt_path,
            split="unsafe_offer_pressure",
            episodes_per_family=episode_count,
            episode_limit=episode_count,
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
    unsafe_metadata = _load_unsafe_metadata(corpus_path, errors)
    _attach_unsafe_metadata(rows, unsafe_metadata)
    rule_summary = rule._summarize(
        rows,
        bootstrap_samples=bootstrap_samples,
        bootstrap_seed=bootstrap_seed,
        alpha=alpha,
    )
    unsafe_summary = _summarize_unsafe_offer_pressure(rows)
    conclusion = _select_unsafe_offer_pressure_conclusion(unsafe_summary)
    unsafe_gate_errors = _unsafe_offer_pressure_gate_errors(conclusion, unsafe_summary)
    expected_cases = episode_count * len(CONDITIONS)
    expected_variants = list(range(variant_start, variant_start + episode_count))
    variants = sorted(row.get("variant") for row in rows if isinstance(row.get("variant"), int))
    instrument_counts = instrument_receipt.get("counts") if isinstance(instrument_receipt.get("counts"), dict) else {}

    _write_json(
        rows_path,
        {
            "schema": "persona_dream.research.prospective_tom.cooperation_unsafe_offer_pressure_slice_rows.v1",
            "policy_id": POLICY_ID,
            "pressure_mode": pressure_mode,
            "corpus_path": str(corpus_path),
            "rows": rows,
        },
    )
    _write_json(
        summary_path,
        {
            "schema": "persona_dream.research.prospective_tom.cooperation_unsafe_offer_pressure_slice_summary.v1",
            "policy_id": POLICY_ID,
            "corpus_path": str(corpus_path),
            "pressure_mode": pressure_mode,
            "variant_start": variant_start,
            "episode_count": episode_count,
            **rule_summary,
            "unsafe_offer_pressure_summary": unsafe_summary,
            "instrument_counts": instrument_counts,
            "conclusion": conclusion,
        },
    )

    _validate_zero_writes(derivation_receipt, errors, "derivation")
    _validate_zero_writes(instrument_receipt, errors, "instrument")
    _validate_zero_writes(condition_receipt, errors, "condition")
    _validate_zero_writes(action_receipt, errors, "action")
    no_oracle_rule_inputs = all(
        row.get("cd_pre_outcome_rule_inputs", {}).get("uses_outcome_or_oracle") is False for row in rows
    )
    checks = {
        "derivation_receipt_passed": derivation_receipt.get("status") == rule.DERIVATION_PASS_STATUS,
        "instrument_receipt_passed": instrument_receipt.get("status") == instrument.PASS_STATUS,
        "instrument_unsafe_rows_complete": instrument_counts.get("unsafe_offer_pressure_rows") == episode_count,
        "instrument_visible_offer_affordance_complete": instrument_counts.get("offer_cooperation_affordance_rows")
        == episode_count,
        "instrument_visible_offer_pressure_complete": instrument_counts.get("visible_offer_pressure_rows")
        == episode_count,
        "instrument_avoid_or_disclose_actual_rows_complete": instrument_counts.get("avoid_or_disclose_actual_rows")
        == episode_count,
        "instrument_pressure_mode_matches": instrument_receipt.get("pressure_mode") == pressure_mode,
        "instrument_lure_rows_match_mode": (
            instrument_counts.get("lure_rows") == episode_count
            if pressure_mode == "lure"
            else instrument_counts.get("lure_rows") == 0
        ),
        "condition_receipt_passed": condition_receipt.get("status") == condition.PASS_STATUS,
        "condition_used_external_unsafe_offer_pressure_corpus": condition_receipt.get("external_corpus_used") is True
        and condition_receipt.get("external_corpus_path") == str(corpus_path.resolve()),
        "action_receipt_passed": action_receipt.get("status") == action.PASS_STATUS,
        "expected_case_count": len(case_index) == expected_cases,
        "expected_action_count": len(action_index) == expected_cases,
        "expected_row_count": len(rows) == episode_count,
        "expected_variants": variants == expected_variants,
        "unsafe_summary_rows_complete": unsafe_summary.get("unsafe_offer_pressure_rows") == episode_count,
        "unsafe_summary_lure_rows_match_mode": (
            unsafe_summary.get("lure_rows") == episode_count
            if pressure_mode == "lure"
            else unsafe_summary.get("lure_rows", 0) == 0
        ),
        "visible_offer_affordance_rows_complete": unsafe_summary.get("visible_offer_affordance_rows") == episode_count,
        "actual_avoid_or_disclose_rows_complete": unsafe_summary.get("actual_avoid_or_disclose_rows") == episode_count,
        "tau_receipts_hash_bound": condition_receipt.get("tau_receipts_hash_bound") is True,
        "live_tau_cases_complete": condition_receipt.get("tau_live_call_performed") == expected_cases,
        "no_oracle_or_outcome_inputs_in_rule": no_oracle_rule_inputs,
        "unsafe_offer_pressure_gate_fail_closed": not unsafe_gate_errors,
        "zero_unsupported_writes": all(
            receipt.get(key) == 0
            for receipt in (derivation_receipt, instrument_receipt, condition_receipt, action_receipt)
            for key in ZERO_WRITE_KEYS
        ),
    }
    for key, value in checks.items():
        if value is not True:
            errors.append(f"check_failed:{key}:{value}")
    errors.extend(unsafe_gate_errors)

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    instrument_receipt_path_for_hash = (
        instrument_receipt_path if reuse_instrument_receipt is None else reuse_instrument_receipt.resolve()
    )
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_tau_cooperation_unsafe_offer_pressure_slice_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "policy_id": POLICY_ID,
        "pressure_mode": pressure_mode,
        "cooperation_probability_threshold": cooperation_threshold,
        "derivation_receipt": str(derivation_receipt_path),
        "derivation_receipt_sha256": _file_sha256(derivation_receipt_path) if derivation_receipt_path.exists() else None,
        "instrument_receipt": str(instrument_receipt_path_for_hash),
        "instrument_receipt_sha256": _file_sha256(instrument_receipt_path_for_hash)
        if instrument_receipt_path_for_hash.exists()
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
            "unsafe_offer_pressure_episodes": episode_count,
            "cases": len(case_index),
            "action_cases": len(action_index),
            "rows": len(rows),
            "unsafe_offer_pressure_rows": unsafe_summary.get("unsafe_offer_pressure_rows"),
            "visible_offer_affordance_rows": unsafe_summary.get("visible_offer_affordance_rows"),
            "actual_avoid_or_disclose_rows": unsafe_summary.get("actual_avoid_or_disclose_rows"),
            "lure_rows": unsafe_summary.get("lure_rows", 0),
            "cd_unsafe_offer_candidates": unsafe_summary.get("cd_unsafe_offer_candidates"),
            "cd_unsafe_offer_suppression_rows": unsafe_summary.get("cd_unsafe_offer_suppression_rows"),
            "cd_low_confidence_cooperation_interventions": rule_summary.get(
                "cd_low_confidence_cooperation_interventions"
            ),
            "cd_action_change_count": rule_summary.get("cd_action_change_count"),
        },
        "unsafe_offer_pressure_summary": unsafe_summary,
        "metrics": {
            "original_mean_cd_minus_baseline_planning_regret": rule_summary.get(
                "original_mean_cd_minus_baseline_planning_regret"
            ),
            "intervened_mean_cd_minus_baseline_planning_regret": rule_summary.get(
                "intervened_mean_cd_minus_baseline_planning_regret"
            ),
            "mean_improvement_vs_original": rule_summary.get("mean_improvement_vs_original"),
            "intervened_planning_regret_ci": rule_summary.get("intervened_planning_regret_ci"),
            "improvement_ci": rule_summary.get("improvement_ci"),
            "original_direction_counts": rule_summary.get("original_direction_counts"),
            "intervened_direction_counts": rule_summary.get("intervened_direction_counts"),
        },
        "planning_benefit_with_confidence": rule._planning_benefit_with_confidence(
            rule_summary["intervened_planning_regret_ci"]
        ),
        "slice_conclusion": conclusion,
        "errors": errors,
        "claims": {
            "proves": [
                "the deterministic unsafe-offer-pressure corpus was consumed by the live Tau M/R/D/CD condition runner",
                "all visible cases exposed OFFER_COOPERATION and visible cooperation pressure before deterministic outcome reveal",
                "unsafe-offer rows were sealed before outcome reveal and passed through Gate 6 action scoring",
                "the pre-outcome cooperation threshold rule used sealed prediction/action fields and did not use outcome or oracle fields as rule inputs",
                "no human content judgment, LLM judge, Memory write, provider call, canonical write, identity write, or source-memory write was attempted",
            ]
            if status == PASS_STATUS
            else [
                "the unsafe-offer-pressure live Tau slice failed closed before accepting a suppression or planning-benefit claim",
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
    parser.add_argument("--variant-start", type=int, default=None)
    parser.add_argument("--episode-count", type=int, default=4)
    parser.add_argument("--pressure-mode", choices=("standard", "lure"), default="standard")
    parser.add_argument("--cooperation-threshold", type=float, default=0.5)
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout-s", type=float, default=240.0)
    parser.add_argument("--preflight-timeout-s", type=float, default=None)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--bootstrap-seed", type=int, default=20721045)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--reuse-instrument-receipt", type=Path, default=None)
    parser.add_argument("--reuse-condition-root", type=Path, default=None)
    parser.add_argument("--reuse-action-root", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    variant_start = (
        args.variant_start
        if args.variant_start is not None
        else 49
        if args.pressure_mode == "lure"
        else 45
    )
    receipt_out = args.receipt_out or (args.output_root / "live_tau_cooperation_unsafe_offer_pressure_slice_receipt.v1.json")
    receipt = run_slice(
        derivation_receipt_path=args.derivation_receipt,
        output_root=args.output_root,
        receipt_out=receipt_out,
        prefix=args.prefix,
        variant_start=variant_start,
        episode_count=args.episode_count,
        cooperation_threshold=args.cooperation_threshold,
        pressure_mode=args.pressure_mode,
        model=args.model,
        timeout_s=args.timeout_s,
        preflight_timeout_s=args.preflight_timeout_s,
        bootstrap_samples=args.bootstrap_samples,
        bootstrap_seed=args.bootstrap_seed,
        alpha=args.alpha,
        reuse_instrument_receipt=args.reuse_instrument_receipt,
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
