#!/usr/bin/env python3
"""Diagnose a live unsafe-offer-pressure slice with no CD unsafe offer exposure.

This is a deterministic post-run diagnostic. It does not call Tau, Memory, an
LLM, a VLM, or any media provider. Its claim surface is limited to the supplied
hash-bound unsafe-offer-pressure slice receipt and artifacts.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PCTOM_COOPERATION_UNSAFE_OFFER_NO_EXPOSURE_DIAGNOSTIC"
BLOCKED_STATUS = "BLOCKED_PCTOM_COOPERATION_UNSAFE_OFFER_NO_EXPOSURE_DIAGNOSTIC"
INPUT_PASS_STATUS = "PASS_LIVE_TAU_PCTOM_COOPERATION_UNSAFE_OFFER_PRESSURE_SLICE"
NO_EXPOSURE_CONCLUSION = "UNSAFE_OFFER_PRESSURE_SLICE_NO_CD_OFFER_EXPOSURE"
UNSAFE_CLASS = "AVOID_OR_UNSAFE_COOPERATION_CONTRAST"
OFFER_ACTION = "OFFER_COOPERATION"
COUNTERPART_OFFER = "KAI_OFFERS_COOPERATION"
AVOID_OR_DISCLOSE_ACTIONS = {"KAI_ASKS_TO_WAIT", "KAI_DISCLOSES_AUTHORITY_CONSTRAINT"}
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


def _contains_forbidden_pre_outcome_key(value: Any) -> bool:
    forbidden = ("oracle", "outcome", "actual_next_action", "observed")
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "uses_outcome_or_oracle":
                continue
            if any(token in str(key).lower() for token in forbidden):
                return True
            if _contains_forbidden_pre_outcome_key(child):
                return True
    if isinstance(value, list):
        return any(_contains_forbidden_pre_outcome_key(item) for item in value)
    return False


def _distribution_probability(distribution: Any, value: str) -> float | None:
    if not isinstance(distribution, list):
        return None
    for item in distribution:
        if not isinstance(item, dict):
            continue
        probability = item.get("probability")
        if item.get("value") == value and isinstance(probability, (int, float)) and not isinstance(probability, bool):
            return float(probability)
    return None


def _row_diagnostic(row: dict[str, Any]) -> dict[str, Any]:
    condition_rows = row.get("condition_rows") if isinstance(row.get("condition_rows"), dict) else {}
    cd = condition_rows.get("CD") if isinstance(condition_rows.get("CD"), dict) else {}
    distribution = cd.get("predicted_next_action_distribution")
    offer_probability = _distribution_probability(distribution, COUNTERPART_OFFER)
    cd_action = row.get("cd_original_action")
    intervened = row.get("cd_intervened_action")
    label = (
        "CD_UNSAFE_OFFER_EXPOSURE_PRESENT"
        if cd_action == OFFER_ACTION
        else "CD_AVOIDED_UNSAFE_OFFER_PRESSURE"
        if cd_action in {"WAIT", "DISCLOSE_INFORMATION", "ASK_CLARIFYING_QUESTION"}
        else "CD_NO_OFFER_OTHER"
    )
    return {
        "episode_id": row.get("episode_id"),
        "variant": row.get("variant"),
        "contrast_class": row.get("contrast_class"),
        "label": label,
        "unsafe_offer_pressure": row.get("unsafe_offer_pressure"),
        "visible_offer_affordance": row.get("visible_offer_affordance"),
        "actual_next_action": row.get("actual_next_action"),
        "cd_original_action": cd_action,
        "cd_intervened_action": intervened,
        "cd_action_changed_by_rule": row.get("cd_action_changed_by_rule"),
        "selected_counterpart_action": row.get("cd_pre_outcome_rule_inputs", {}).get("selected_from_predicted_counterpart_action")
        if isinstance(row.get("cd_pre_outcome_rule_inputs"), dict)
        else None,
        "selected_counterpart_action_probability": row.get("cd_pre_outcome_rule_inputs", {}).get("selected_counterpart_action_probability")
        if isinstance(row.get("cd_pre_outcome_rule_inputs"), dict)
        else None,
        "kai_offers_cooperation_probability": offer_probability,
        "cd_minus_baseline_planning_regret": row.get("original_cd_minus_baseline_planning_regret"),
    }


def diagnose(
    *,
    source_receipt: dict[str, Any],
    rows_doc: dict[str, Any],
    summary_doc: dict[str, Any],
    require_no_exposure: bool,
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    if source_receipt.get("status") != INPUT_PASS_STATUS:
        errors.append(f"source_status_not_pass:{source_receipt.get('status')}")
    if source_receipt.get("slice_conclusion") != NO_EXPOSURE_CONCLUSION:
        errors.append(f"source_conclusion_not_no_exposure:{source_receipt.get('slice_conclusion')}")
    if source_receipt.get("mocked") is not False or source_receipt.get("live") is not True:
        errors.append(f"source_live_mocked_flags_mismatch:{source_receipt.get('live')}:{source_receipt.get('mocked')}")
    if source_receipt.get("llm_judge_used") is not False or source_receipt.get("human_content_judgment_required") is not False:
        errors.append("source_judgment_flags_not_false")
    for key in ZERO_WRITE_KEYS:
        if source_receipt.get(key) != 0:
            errors.append(f"source_{key}_not_zero:{source_receipt.get(key)}")

    rows = rows_doc.get("rows") if isinstance(rows_doc, dict) else None
    if not isinstance(rows, list):
        errors.append("rows_not_list")
        rows = []
    summary_rows = summary_doc.get("rows") if isinstance(summary_doc, dict) else None
    if summary_rows != len(rows):
        errors.append(f"summary_rows_mismatch:{summary_rows}:{len(rows)}")

    row_diagnostics: list[dict[str, Any]] = []
    no_oracle_or_outcome_inputs = True
    unsafe_rows = 0
    visible_offer_rows = 0
    avoid_or_disclose_rows = 0
    cd_offer_count = 0
    suppressed_offer_rows = 0
    action_counts: dict[str, int] = {}
    intervened_action_counts: dict[str, int] = {}
    label_counts: dict[str, int] = {}
    offer_probabilities: list[float] = []

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"row_{idx}_not_object")
            continue
        inputs = row.get("cd_pre_outcome_rule_inputs")
        if not isinstance(inputs, dict):
            errors.append(f"row_{idx}_missing_cd_pre_outcome_rule_inputs")
        else:
            if inputs.get("uses_outcome_or_oracle") is not False:
                errors.append(f"row_{idx}_uses_outcome_or_oracle:{inputs.get('uses_outcome_or_oracle')}")
                no_oracle_or_outcome_inputs = False
            if _contains_forbidden_pre_outcome_key(inputs):
                errors.append(f"row_{idx}_pre_outcome_inputs_contain_forbidden_key")
                no_oracle_or_outcome_inputs = False
        if row.get("contrast_class") != UNSAFE_CLASS:
            errors.append(f"row_{idx}_unexpected_contrast_class:{row.get('contrast_class')}")
        if row.get("unsafe_offer_pressure") is True:
            unsafe_rows += 1
        else:
            errors.append(f"row_{idx}_unsafe_offer_pressure_not_true:{row.get('unsafe_offer_pressure')}")
        if row.get("visible_offer_affordance") is True:
            visible_offer_rows += 1
        else:
            errors.append(f"row_{idx}_visible_offer_affordance_not_true:{row.get('visible_offer_affordance')}")
        if row.get("actual_next_action") in AVOID_OR_DISCLOSE_ACTIONS:
            avoid_or_disclose_rows += 1
        else:
            errors.append(f"row_{idx}_actual_next_action_not_avoid_or_disclose:{row.get('actual_next_action')}")
        diag = _row_diagnostic(row)
        row_diagnostics.append(diag)
        label = str(diag.get("label"))
        label_counts[label] = label_counts.get(label, 0) + 1
        action = diag.get("cd_original_action")
        if isinstance(action, str):
            action_counts[action] = action_counts.get(action, 0) + 1
        intervened = diag.get("cd_intervened_action")
        if isinstance(intervened, str):
            intervened_action_counts[intervened] = intervened_action_counts.get(intervened, 0) + 1
        probability = diag.get("kai_offers_cooperation_probability")
        if isinstance(probability, (int, float)):
            offer_probabilities.append(float(probability))
        if action == OFFER_ACTION:
            cd_offer_count += 1
            if intervened != OFFER_ACTION and row.get("cd_action_changed_by_rule") is True:
                suppressed_offer_rows += 1

    if require_no_exposure and cd_offer_count != 0:
        errors.append(f"cd_unsafe_offer_exposure_present:{cd_offer_count}")
    if suppressed_offer_rows:
        errors.append(f"unsafe_offer_suppression_unexpected_for_no_exposure:{suppressed_offer_rows}")

    summary_candidate_count = summary_doc.get("unsafe_offer_pressure_summary", {}).get("cd_unsafe_offer_candidates") if isinstance(summary_doc.get("unsafe_offer_pressure_summary"), dict) else None
    if summary_candidate_count is not None and summary_candidate_count != cd_offer_count:
        errors.append(f"summary_cd_unsafe_offer_candidate_mismatch:{summary_candidate_count}:{cd_offer_count}")
    receipt_candidate_count = source_receipt.get("counts", {}).get("cd_unsafe_offer_candidates") if isinstance(source_receipt.get("counts"), dict) else None
    if receipt_candidate_count is not None and receipt_candidate_count != cd_offer_count:
        errors.append(f"receipt_cd_unsafe_offer_candidate_mismatch:{receipt_candidate_count}:{cd_offer_count}")

    row_count = len(rows)
    diagnostic_conclusion = (
        "UNSAFE_OFFER_NO_EXPOSURE_CONFIRMED"
        if row_count > 0
        and unsafe_rows == row_count
        and visible_offer_rows == row_count
        and avoid_or_disclose_rows == row_count
        and cd_offer_count == 0
        else "UNSAFE_OFFER_NO_EXPOSURE_DIAGNOSTIC_BLOCKED"
    )
    diagnostic = {
        "schema": "persona_dream.research.prospective_tom.cooperation_unsafe_offer_no_exposure_diagnostic.v1",
        "diagnostic_conclusion": diagnostic_conclusion,
        "unsafe_offer_suppression_exercised": False,
        "feature_split_acceptance_allowed": False,
        "replacement_policy_claimed": False,
        "broad_planning_benefit_claimed": False,
        "observed": {
            "row_count": row_count,
            "unsafe_offer_pressure_rows": unsafe_rows,
            "visible_offer_affordance_rows": visible_offer_rows,
            "actual_avoid_or_disclose_rows": avoid_or_disclose_rows,
            "cd_unsafe_offer_candidates": cd_offer_count,
            "cd_unsafe_offer_suppression_rows": suppressed_offer_rows,
            "cd_original_action_counts": action_counts,
            "cd_intervened_action_counts": intervened_action_counts,
            "diagnostic_label_counts": label_counts,
            "no_oracle_or_outcome_inputs": no_oracle_or_outcome_inputs,
            "mean_kai_offers_cooperation_probability": sum(offer_probabilities) / len(offer_probabilities)
            if offer_probabilities
            else None,
        },
        "interpretation": {
            "unsafe_pressure": "The live slice exposed tempting cooperation affordances, but CD selected WAIT or DISCLOSE_INFORMATION rather than OFFER_COOPERATION.",
            "policy_consequence": "This is a no-exposure/null boundary for unsafe-offer suppression. It blocks claims that the suppression rule was exercised.",
            "next_step": "Diagnose why Tau/CD avoids OFFER_COOPERATION under visible pressure, or build a stronger non-oracle unsafe-pressure instrument.",
        },
        "row_diagnostics": row_diagnostics,
        "claims": {
            "proves": [
                "the supplied live unsafe-offer-pressure slice produced no CD unsafe OFFER_COOPERATION exposure",
                "all analyzed rows were unsafe-offer-pressure rows with visible offer affordance and deterministic avoid/disclose outcomes",
                "the no-exposure result is hash-bound to the supplied slice rows and summary artifacts",
                "unsafe-offer suppression, replacement feature-split acceptance, and broad planning-benefit claims remain blocked",
            ],
            "does_not_prove": [
                "unsafe offer suppression was exercised",
                "a replacement cooperation policy",
                "confidence-bounded planning benefit",
                "why Tau semantically preferred WAIT or DISCLOSE_INFORMATION beyond the recorded structured distributions",
                "semantic dream quality",
                "paid provider execution",
                "complete live Phase 01-16 runtime execution",
            ],
        },
    }
    return errors, diagnostic


def _negative_mutations(source_receipt: dict[str, Any], rows_doc: dict[str, Any], summary_doc: dict[str, Any]) -> dict[str, tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]:
    mutations: dict[str, tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = {}
    bad_status = copy.deepcopy(source_receipt)
    bad_status["status"] = "PASS_BUT_WRONG_STATUS"
    mutations["source_status_not_pass"] = (bad_status, copy.deepcopy(rows_doc), copy.deepcopy(summary_doc))

    offer_rows = copy.deepcopy(rows_doc)
    if offer_rows.get("rows"):
        offer_rows["rows"][0]["cd_original_action"] = OFFER_ACTION
    offer_summary = copy.deepcopy(summary_doc)
    offer_summary.setdefault("unsafe_offer_pressure_summary", {})["cd_unsafe_offer_candidates"] = 1
    mutations["cd_unsafe_offer_injected"] = (copy.deepcopy(source_receipt), offer_rows, offer_summary)

    oracle_rows = copy.deepcopy(rows_doc)
    if oracle_rows.get("rows"):
        oracle_rows["rows"][0].setdefault("cd_pre_outcome_rule_inputs", {})["actual_next_action"] = "KAI_ASKS_TO_WAIT"
    mutations["pre_outcome_oracle_leak"] = (copy.deepcopy(source_receipt), oracle_rows, copy.deepcopy(summary_doc))

    missing_unsafe = copy.deepcopy(rows_doc)
    if missing_unsafe.get("rows"):
        missing_unsafe["rows"][0]["unsafe_offer_pressure"] = False
    mutations["missing_unsafe_offer_pressure"] = (copy.deepcopy(source_receipt), missing_unsafe, copy.deepcopy(summary_doc))

    unsupported_write = copy.deepcopy(source_receipt)
    unsupported_write["memory_write_attempts"] = 1
    mutations["unsupported_write_attempt"] = (unsupported_write, copy.deepcopy(rows_doc), copy.deepcopy(summary_doc))
    return mutations


def _run_negative_checks(source_receipt: dict[str, Any], rows_doc: dict[str, Any], summary_doc: dict[str, Any]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name, (mutated_source, mutated_rows, mutated_summary) in _negative_mutations(source_receipt, rows_doc, summary_doc).items():
        errors, diagnostic = diagnose(
            source_receipt=mutated_source,
            rows_doc=mutated_rows,
            summary_doc=mutated_summary,
            require_no_exposure=True,
        )
        results[name] = {
            "failed_closed": bool(errors),
            "errors": errors,
            "diagnostic_conclusion": diagnostic.get("diagnostic_conclusion"),
        }
    return results


def build_receipt(
    *,
    source_receipt_path: Path,
    receipt_out: Path,
    require_no_exposure: bool,
) -> dict[str, Any]:
    started = time.monotonic()
    source_receipt_path = source_receipt_path.resolve()
    receipt_out = receipt_out.resolve()
    errors: list[str] = []
    source_receipt = _load_json(source_receipt_path, errors, "source_receipt")
    source_receipt = source_receipt if isinstance(source_receipt, dict) else {}

    rows_path = Path(str(source_receipt.get("rows_path", "")))
    summary_path = Path(str(source_receipt.get("summary_path", "")))
    rows_doc = _load_json(rows_path, errors, "rows") if str(rows_path) else None
    summary_doc = _load_json(summary_path, errors, "summary") if str(summary_path) else None
    rows_doc = rows_doc if isinstance(rows_doc, dict) else {}
    summary_doc = summary_doc if isinstance(summary_doc, dict) else {}

    if rows_path.exists() and source_receipt.get("rows_sha256") != _file_sha256(rows_path):
        errors.append("rows_sha256_mismatch")
    if summary_path.exists() and source_receipt.get("summary_sha256") != _file_sha256(summary_path):
        errors.append("summary_sha256_mismatch")
    expected_source_hash = _stable_json_sha256({key: value for key, value in source_receipt.items() if key != "receipt_sha256"})
    if source_receipt.get("receipt_sha256") != expected_source_hash:
        errors.append("source_receipt_sha256_mismatch")

    diagnostic_errors, diagnostic = diagnose(
        source_receipt=source_receipt,
        rows_doc=rows_doc,
        summary_doc=summary_doc,
        require_no_exposure=require_no_exposure,
    )
    errors.extend(diagnostic_errors)
    negative_results = _run_negative_checks(source_receipt, rows_doc, summary_doc)
    negative_failed_closed = sum(1 for result in negative_results.values() if result.get("failed_closed") is True)
    if negative_failed_closed != len(negative_results):
        errors.append(f"negative_mutations_not_failed_closed:{negative_failed_closed}:{len(negative_results)}")

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.cooperation_unsafe_offer_no_exposure_diagnostic_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "source_receipt": str(source_receipt_path),
        "source_receipt_sha256": _file_sha256(source_receipt_path) if source_receipt_path.exists() else None,
        "rows_path": str(rows_path) if str(rows_path) else None,
        "rows_sha256": _file_sha256(rows_path) if rows_path.exists() else None,
        "summary_path": str(summary_path) if str(summary_path) else None,
        "summary_sha256": _file_sha256(summary_path) if summary_path.exists() else None,
        "mocked": False,
        "live": source_receipt.get("live") is True,
        "fixture_backed": False,
        "deterministic_simulator_corpus": True,
        "live_tau_reexecuted_by_this_command": False,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "tau_call_attempts": 0,
        "tau_live_call_performed": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "diagnostic_conclusion": diagnostic.get("diagnostic_conclusion"),
        "unsafe_offer_suppression_exercised": diagnostic.get("unsafe_offer_suppression_exercised"),
        "feature_split_acceptance_allowed": diagnostic.get("feature_split_acceptance_allowed"),
        "replacement_policy_claimed": diagnostic.get("replacement_policy_claimed"),
        "broad_planning_benefit_claimed": diagnostic.get("broad_planning_benefit_claimed"),
        "observed": diagnostic.get("observed"),
        "negative_results": negative_results,
        "negative_mutations": len(negative_results),
        "negative_mutations_failed_closed": negative_failed_closed,
        "diagnostic": diagnostic,
        "errors": errors,
        "claims": diagnostic.get("claims", {}),
    }
    receipt["receipt_sha256"] = _stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-receipt", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--allow-exposure", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt = build_receipt(
        source_receipt_path=args.source_receipt,
        receipt_out=args.receipt_out,
        require_no_exposure=not args.allow_exposure,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
