#!/usr/bin/env python3
"""Diagnose a live cooperation-contrast slice that produced no CD offer exposure.

This is a deterministic post-run diagnostic. It does not call Tau, Memory, an
LLM, a VLM, or any media provider. Its claim surface is limited to the supplied
hash-bound cooperation-contrast slice receipt and artifacts.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PCTOM_COOPERATION_NO_EXPOSURE_DIAGNOSTIC"
BLOCKED_STATUS = "BLOCKED_PCTOM_COOPERATION_NO_EXPOSURE_DIAGNOSTIC"
INPUT_PASS_STATUS = "PASS_LIVE_TAU_PCTOM_COOPERATION_CONTRAST_SLICE"
NO_EXPOSURE_CONCLUSION = "CONTRAST_SLICE_LIVE_TAU_NO_CD_OFFER_EXPOSURE"
ZERO_WRITE_KEYS = (
    "memory_write_attempts",
    "provider_call_attempts",
    "canonical_memory_write_attempts",
    "identity_write_attempts",
    "source_memory_write_attempts",
)
KEEP_CLASS = "KEEP_COOPERATION_POSITIVE"
AVOID_CLASS = "AVOID_OR_UNSAFE_COOPERATION_CONTRAST"
OFFER_ACTION = "OFFER_COOPERATION"
COUNTERPART_OFFER = "KAI_OFFERS_COOPERATION"


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
        if item.get("value") == value and isinstance(item.get("probability"), (int, float)) and not isinstance(item.get("probability"), bool):
            return float(item["probability"])
    return None


def _top_distribution_value(distribution: Any) -> tuple[str | None, float | None]:
    if not isinstance(distribution, list):
        return None, None
    candidates: list[tuple[str, float]] = []
    for item in distribution:
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        probability = item.get("probability")
        if isinstance(value, str) and isinstance(probability, (int, float)) and not isinstance(probability, bool):
            candidates.append((value, float(probability)))
    if not candidates:
        return None, None
    candidates.sort(key=lambda pair: pair[1], reverse=True)
    return candidates[0]


def _classify_row(row: dict[str, Any]) -> dict[str, Any]:
    condition_rows = row.get("condition_rows") if isinstance(row.get("condition_rows"), dict) else {}
    cd = condition_rows.get("CD") if isinstance(condition_rows.get("CD"), dict) else {}
    distribution = cd.get("predicted_next_action_distribution")
    top_value, top_probability = _top_distribution_value(distribution)
    offer_probability = _distribution_probability(distribution, COUNTERPART_OFFER)
    contrast_class = row.get("contrast_class")
    cd_action = row.get("cd_original_action")
    oracle_action = cd.get("oracle_action")
    if cd_action == OFFER_ACTION:
        label = "CD_OFFER_EXPOSURE_PRESENT"
    elif contrast_class == KEEP_CLASS and oracle_action == OFFER_ACTION:
        label = "KEEP_ROW_CD_AVOIDED_ORACLE_COOPERATION"
    elif contrast_class == AVOID_CLASS and offer_probability is not None and offer_probability < 0.5:
        label = "AVOID_ROW_CD_SUPPRESSED_UNSAFE_COOPERATION"
    else:
        label = "CD_NO_OFFER_OTHER"
    return {
        "episode_id": row.get("episode_id"),
        "variant": row.get("variant"),
        "contrast_class": contrast_class,
        "label": label,
        "cd_original_action": cd_action,
        "oracle_action": oracle_action,
        "selected_counterpart_action": row.get("cd_pre_outcome_rule_inputs", {}).get("selected_from_predicted_counterpart_action")
        if isinstance(row.get("cd_pre_outcome_rule_inputs"), dict)
        else None,
        "selected_counterpart_action_probability": row.get("cd_pre_outcome_rule_inputs", {}).get("selected_counterpart_action_probability")
        if isinstance(row.get("cd_pre_outcome_rule_inputs"), dict)
        else None,
        "top_predicted_counterpart_action": top_value,
        "top_predicted_counterpart_action_probability": top_probability,
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

    class_counts: collections.Counter[str] = collections.Counter()
    cd_actions: collections.Counter[str] = collections.Counter()
    selected_counterpart_actions: collections.Counter[str] = collections.Counter()
    labels: collections.Counter[str] = collections.Counter()
    row_diagnostics: list[dict[str, Any]] = []
    offer_probabilities_by_class: dict[str, list[float]] = {KEEP_CLASS: [], AVOID_CLASS: []}
    no_oracle_or_outcome_inputs = True

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
        row_diag = _classify_row(row)
        row_diagnostics.append(row_diag)
        if isinstance(row_diag.get("contrast_class"), str):
            class_counts[str(row_diag["contrast_class"])] += 1
        if isinstance(row_diag.get("cd_original_action"), str):
            cd_actions[str(row_diag["cd_original_action"])] += 1
        if isinstance(row_diag.get("selected_counterpart_action"), str):
            selected_counterpart_actions[str(row_diag["selected_counterpart_action"])] += 1
        labels[str(row_diag["label"])] += 1
        cls = row_diag.get("contrast_class")
        probability = row_diag.get("kai_offers_cooperation_probability")
        if cls in offer_probabilities_by_class and isinstance(probability, (int, float)):
            offer_probabilities_by_class[str(cls)].append(float(probability))

    cd_offer_count = cd_actions.get(OFFER_ACTION, 0)
    if require_no_exposure and cd_offer_count != 0:
        errors.append(f"cd_offer_exposure_present:{cd_offer_count}")
    if class_counts.get(KEEP_CLASS, 0) <= 0:
        errors.append("missing_keep_contrast_rows")
    if class_counts.get(AVOID_CLASS, 0) <= 0:
        errors.append("missing_avoid_contrast_rows")

    summary_candidate_count = summary_doc.get("cd_offer_cooperation_candidates") if isinstance(summary_doc, dict) else None
    if summary_candidate_count is not None and summary_candidate_count != cd_offer_count:
        errors.append(f"summary_cd_offer_candidate_mismatch:{summary_candidate_count}:{cd_offer_count}")

    def average(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    diagnostic = {
        "schema": "persona_dream.research.prospective_tom.cooperation_no_exposure_diagnostic.v1",
        "diagnostic_conclusion": (
            "NO_CD_OFFER_EXPOSURE_CONFIRMED"
            if cd_offer_count == 0 and class_counts.get(KEEP_CLASS, 0) > 0 and class_counts.get(AVOID_CLASS, 0) > 0
            else "NO_EXPOSURE_DIAGNOSTIC_BLOCKED"
        ),
        "feature_split_acceptance_allowed": False,
        "replacement_policy_claimed": False,
        "broad_planning_benefit_claimed": False,
        "observed": {
            "row_count": len(rows),
            "contrast_class_counts": dict(class_counts),
            "cd_original_action_counts": dict(cd_actions),
            "selected_counterpart_action_counts": dict(selected_counterpart_actions),
            "diagnostic_label_counts": dict(labels),
            "cd_offer_cooperation_candidates": cd_offer_count,
            "no_oracle_or_outcome_inputs": no_oracle_or_outcome_inputs,
            "mean_kai_offers_cooperation_probability_by_class": {
                KEEP_CLASS: average(offer_probabilities_by_class[KEEP_CLASS]),
                AVOID_CLASS: average(offer_probabilities_by_class[AVOID_CLASS]),
            },
        },
        "interpretation": {
            "keep_class": "CD did not expose the intended keep-cooperation action; it selected WAIT or DISCLOSE_INFORMATION even when the simulator oracle action was OFFER_COOPERATION.",
            "avoid_class": "CD also did not expose unsafe cooperation in avoid rows; it selected WAIT or DISCLOSE_INFORMATION while KAI_OFFERS_COOPERATION probability stayed below the threshold.",
            "policy_consequence": "This receipt supports a no-exposure/null boundary only. It blocks replacement feature-split acceptance and broad planning-benefit claims.",
        },
        "row_diagnostics": row_diagnostics,
        "claims": {
            "proves": [
                "the supplied live cooperation-contrast slice produced no CD OFFER_COOPERATION exposure",
                "both keep-cooperation and avoid/unsafe-cooperation contrast classes were present in the analyzed rows",
                "the no-exposure result is hash-bound to the supplied slice rows and summary artifacts",
                "feature-split acceptance and broad planning-benefit claims remain blocked by missing CD offer exposure",
            ],
            "does_not_prove": [
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

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.cooperation_no_exposure_diagnostic_receipt.v1",
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
        "feature_split_acceptance_allowed": diagnostic.get("feature_split_acceptance_allowed"),
        "replacement_policy_claimed": diagnostic.get("replacement_policy_claimed"),
        "broad_planning_benefit_claimed": diagnostic.get("broad_planning_benefit_claimed"),
        "observed": diagnostic.get("observed"),
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
