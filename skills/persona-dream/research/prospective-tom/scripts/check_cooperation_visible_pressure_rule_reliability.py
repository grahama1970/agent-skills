#!/usr/bin/env python3
"""Check visible-pressure cooperation fallback reliability over live Tau receipts.

This deterministic checker consumes two already-created live Tau replay
receipts:

1. the unsafe-offer-pressure lure replay where visible pressure must suppress
   CD's unsafe OFFER_COOPERATION action; and
2. the exposure/contrast replay where the same rule must leave keep rows alone
   and avoid/unsafe rows must not create OFFER_COOPERATION.

It performs no Tau, Memory, model, VLM, media-provider, canonical-memory,
identity, or source-memory writes. The source artifacts are live-originated; the
negative mutations are deterministic fail-closed checks over copies of those
artifacts.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PCTOM_COOPERATION_VISIBLE_PRESSURE_RULE_RELIABILITY"
BLOCKED_STATUS = "BLOCKED_PCTOM_COOPERATION_VISIBLE_PRESSURE_RULE_RELIABILITY"

SUPPRESSION_PASS_STATUS = "PASS_LIVE_TAU_PCTOM_COOPERATION_UNSAFE_OFFER_PRESSURE_SLICE"
SUPPRESSION_CONCLUSION = "UNSAFE_OFFER_PRESSURE_SLICE_SUPPRESSION_EXERCISED"
EXPOSURE_PASS_STATUS = "PASS_LIVE_TAU_PCTOM_COOPERATION_EXPOSURE_CONTRAST_SLICE"
EXPOSURE_CONCLUSION = "EXPOSURE_CONTRAST_SLICE_PARTIAL_CD_OFFER_EXPOSURE"

KEEP_CLASS = "KEEP_COOPERATION_POSITIVE"
AVOID_CLASS = "AVOID_OR_UNSAFE_COOPERATION_CONTRAST"
OFFER_ACTION = "OFFER_COOPERATION"
ASK_ACTION = "ASK_CLARIFYING_QUESTION"
COUNTERPART_OFFER = "KAI_OFFERS_COOPERATION"
VISIBLE_PRESSURE_RULE = "VISIBLE_COOPERATION_PRESSURE_FALLBACK_TO_ASK"
KEEP_RULE = "KEEP_ORIGINAL_ACTION"

ZERO_WRITE_KEYS = (
    "memory_write_attempts",
    "provider_call_attempts",
    "canonical_memory_write_attempts",
    "identity_write_attempts",
    "source_memory_write_attempts",
)

FORBIDDEN_PRE_OUTCOME_KEY_TOKENS = (
    "actual_next_action",
    "oracle",
    "outcome",
    "observed",
    "contrast_class",
    "unsafe_offer_pressure",
    "cooperation_is_unsafe_or_suboptimal",
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


def _rows_from_doc(doc: Any, errors: list[str], label: str) -> list[dict[str, Any]]:
    if not isinstance(doc, dict):
        errors.append(f"{label}_not_object")
        return []
    rows = doc.get("rows")
    if not isinstance(rows, list):
        errors.append(f"{label}_rows_not_list")
        return []
    result: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        if isinstance(row, dict):
            result.append(row)
        else:
            errors.append(f"{label}_row_{idx}_not_object")
    return result


def _contains_forbidden_pre_outcome_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).lower()
            if key_text == "uses_outcome_or_oracle":
                if child is not False:
                    return True
            elif any(token in key_text for token in FORBIDDEN_PRE_OUTCOME_KEY_TOKENS):
                return True
            if _contains_forbidden_pre_outcome_key(child):
                return True
    if isinstance(value, list):
        return any(_contains_forbidden_pre_outcome_key(item) for item in value)
    return False


def _count_actions(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        action = row.get(field)
        if isinstance(action, str):
            counts[action] = counts.get(action, 0) + 1
    return counts


def _require_source_common(
    *,
    label: str,
    receipt: dict[str, Any],
    pass_status: str,
    conclusion: str,
    errors: list[str],
) -> None:
    if receipt.get("status") != pass_status:
        errors.append(f"{label}_status_not_pass:{receipt.get('status')}")
    if receipt.get("slice_conclusion") != conclusion:
        errors.append(f"{label}_conclusion_mismatch:{receipt.get('slice_conclusion')}")
    if receipt.get("mocked") is not False:
        errors.append(f"{label}_mocked_not_false:{receipt.get('mocked')}")
    if receipt.get("live") is not True:
        errors.append(f"{label}_live_not_true:{receipt.get('live')}")
    if receipt.get("fixture_backed") is not False:
        errors.append(f"{label}_fixture_backed_not_false:{receipt.get('fixture_backed')}")
    if receipt.get("deterministic_simulator_corpus") is not True:
        errors.append(f"{label}_deterministic_simulator_corpus_not_true")
    if receipt.get("live_tau_originated_artifacts_consumed") is not True:
        errors.append(f"{label}_live_tau_originated_artifacts_consumed_not_true")
    if receipt.get("live_tau_reexecuted_by_this_command") is not False:
        errors.append(f"{label}_live_tau_reexecuted_by_this_command_not_false")
    if receipt.get("llm_judge_used") is not False:
        errors.append(f"{label}_llm_judge_used_not_false")
    if receipt.get("human_content_judgment_required") is not False:
        errors.append(f"{label}_human_content_judgment_required_not_false")
    if receipt.get("planning_benefit_with_confidence") is not False:
        errors.append(f"{label}_planning_benefit_with_confidence_claimed")
    for key in ZERO_WRITE_KEYS:
        if receipt.get(key) != 0:
            errors.append(f"{label}_{key}_not_zero:{receipt.get(key)}")


def _validate_hashes(
    *,
    label: str,
    receipt_path: Path | None,
    receipt: dict[str, Any],
    rows_path: Path | None,
    summary_path: Path | None,
    errors: list[str],
) -> None:
    if receipt_path is not None and receipt_path.exists():
        expected_receipt_sha = receipt.get("receipt_sha256")
        actual_receipt_sha = _stable_json_sha256(
            {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        )
        if expected_receipt_sha != actual_receipt_sha:
            errors.append(f"{label}_receipt_sha256_mismatch")
    if rows_path is None or not rows_path.exists():
        errors.append(f"{label}_rows_path_missing:{rows_path}")
    elif receipt.get("rows_sha256") != _file_sha256(rows_path):
        errors.append(f"{label}_rows_sha256_mismatch")
    if summary_path is None or not summary_path.exists():
        errors.append(f"{label}_summary_path_missing:{summary_path}")
    elif receipt.get("summary_sha256") != _file_sha256(summary_path):
        errors.append(f"{label}_summary_sha256_mismatch")


def _validate_suppression(
    *,
    receipt: dict[str, Any],
    rows_doc: dict[str, Any],
    summary_doc: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    _require_source_common(
        label="suppression",
        receipt=receipt,
        pass_status=SUPPRESSION_PASS_STATUS,
        conclusion=SUPPRESSION_CONCLUSION,
        errors=errors,
    )
    rows = _rows_from_doc(rows_doc, errors, "suppression_rows_doc")
    counts = receipt.get("counts") if isinstance(receipt.get("counts"), dict) else {}
    expected_counts = {
        "rows": 4,
        "lure_rows": 4,
        "unsafe_offer_pressure_rows": 4,
        "visible_offer_affordance_rows": 4,
        "cd_unsafe_offer_candidates": 4,
        "cd_unsafe_offer_suppression_rows": 4,
        "cd_action_change_count": 4,
    }
    for key, expected in expected_counts.items():
        if counts.get(key) != expected:
            errors.append(f"suppression_count_mismatch:{key}:{counts.get(key)}:{expected}")
    if summary_doc.get("rows") != len(rows):
        errors.append(f"suppression_summary_rows_mismatch:{summary_doc.get('rows')}:{len(rows)}")
    if len(rows) != 4:
        errors.append(f"suppression_row_count_not_4:{len(rows)}")

    observed = {
        "rows": len(rows),
        "cd_original_actions": _count_actions(rows, "cd_original_action"),
        "cd_intervened_actions": _count_actions(rows, "cd_intervened_action"),
        "changed_rows": 0,
        "visible_pressure_rows": 0,
        "visible_pressure_input_rows": 0,
        "pre_outcome_input_leak_rows": [],
    }
    for idx, row in enumerate(rows):
        inputs = row.get("cd_pre_outcome_rule_inputs")
        if not isinstance(inputs, dict):
            errors.append(f"suppression_row_{idx}_missing_cd_pre_outcome_rule_inputs")
            inputs = {}
        if row.get("contrast_class") != AVOID_CLASS:
            errors.append(f"suppression_row_{idx}_unexpected_contrast_class:{row.get('contrast_class')}")
        if row.get("pressure_mode") != "lure":
            errors.append(f"suppression_row_{idx}_pressure_mode_not_lure:{row.get('pressure_mode')}")
        if row.get("unsafe_offer_pressure") is not True:
            errors.append(f"suppression_row_{idx}_unsafe_offer_pressure_not_true:{row.get('unsafe_offer_pressure')}")
        if row.get("visible_offer_affordance") is not True:
            errors.append(f"suppression_row_{idx}_visible_offer_affordance_not_true:{row.get('visible_offer_affordance')}")
        if row.get("visible_cooperation_pressure") is True:
            observed["visible_pressure_rows"] += 1
        else:
            errors.append(f"suppression_row_{idx}_visible_cooperation_pressure_not_true:{row.get('visible_cooperation_pressure')}")
        if row.get("cd_original_action") != OFFER_ACTION:
            errors.append(f"suppression_row_{idx}_cd_original_action_not_offer:{row.get('cd_original_action')}")
        if row.get("cd_intervened_action") != ASK_ACTION:
            errors.append(f"suppression_row_{idx}_cd_intervened_action_not_ask:{row.get('cd_intervened_action')}")
        if row.get("cd_action_changed_by_rule") is True:
            observed["changed_rows"] += 1
        else:
            errors.append(f"suppression_row_{idx}_cd_action_changed_by_rule_not_true:{row.get('cd_action_changed_by_rule')}")
        if inputs.get("rule") != VISIBLE_PRESSURE_RULE:
            errors.append(f"suppression_row_{idx}_rule_mismatch:{inputs.get('rule')}")
        if inputs.get("visible_cooperation_pressure") is True:
            observed["visible_pressure_input_rows"] += 1
        else:
            errors.append(
                f"suppression_row_{idx}_rule_input_visible_pressure_not_true:{inputs.get('visible_cooperation_pressure')}"
            )
        if inputs.get("selected_from_predicted_counterpart_action") != COUNTERPART_OFFER:
            errors.append(
                "suppression_row_"
                f"{idx}_selected_counterpart_action_mismatch:{inputs.get('selected_from_predicted_counterpart_action')}"
            )
        if _contains_forbidden_pre_outcome_key(inputs):
            observed["pre_outcome_input_leak_rows"].append(row.get("episode_id") or idx)
            errors.append(f"suppression_row_{idx}_pre_outcome_rule_inputs_leak")
    return observed


def _validate_exposure(
    *,
    receipt: dict[str, Any],
    rows_doc: dict[str, Any],
    summary_doc: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    _require_source_common(
        label="exposure",
        receipt=receipt,
        pass_status=EXPOSURE_PASS_STATUS,
        conclusion=EXPOSURE_CONCLUSION,
        errors=errors,
    )
    rows = _rows_from_doc(rows_doc, errors, "exposure_rows_doc")
    counts = receipt.get("counts") if isinstance(receipt.get("counts"), dict) else {}
    expected_counts = {
        "rows": 8,
        "keep_cooperation_positive_rows": 4,
        "avoid_or_unsafe_cooperation_contrast_rows": 4,
        "cd_offer_keep_candidates": 4,
        "cd_offer_avoid_or_unsafe_candidates": 0,
        "cd_action_change_count": 0,
    }
    for key, expected in expected_counts.items():
        if counts.get(key) != expected:
            errors.append(f"exposure_count_mismatch:{key}:{counts.get(key)}:{expected}")
    if summary_doc.get("rows") != len(rows):
        errors.append(f"exposure_summary_rows_mismatch:{summary_doc.get('rows')}:{len(rows)}")
    if len(rows) != 8:
        errors.append(f"exposure_row_count_not_8:{len(rows)}")

    keep_rows = [row for row in rows if row.get("contrast_class") == KEEP_CLASS]
    avoid_rows = [row for row in rows if row.get("contrast_class") == AVOID_CLASS]
    unknown_rows = [row for row in rows if row.get("contrast_class") not in {KEEP_CLASS, AVOID_CLASS}]
    if len(keep_rows) != 4:
        errors.append(f"exposure_keep_row_count_not_4:{len(keep_rows)}")
    if len(avoid_rows) != 4:
        errors.append(f"exposure_avoid_row_count_not_4:{len(avoid_rows)}")
    if unknown_rows:
        errors.append(f"exposure_unknown_contrast_class_rows:{len(unknown_rows)}")

    observed = {
        "rows": len(rows),
        "keep_rows": len(keep_rows),
        "avoid_rows": len(avoid_rows),
        "cd_original_actions_by_class": {
            KEEP_CLASS: _count_actions(keep_rows, "cd_original_action"),
            AVOID_CLASS: _count_actions(avoid_rows, "cd_original_action"),
        },
        "cd_intervened_actions_by_class": {
            KEEP_CLASS: _count_actions(keep_rows, "cd_intervened_action"),
            AVOID_CLASS: _count_actions(avoid_rows, "cd_intervened_action"),
        },
        "pre_outcome_input_leak_rows": [],
    }
    for idx, row in enumerate(rows):
        inputs = row.get("cd_pre_outcome_rule_inputs")
        if not isinstance(inputs, dict):
            errors.append(f"exposure_row_{idx}_missing_cd_pre_outcome_rule_inputs")
            inputs = {}
        if row.get("cd_action_changed_by_rule") is not False:
            errors.append(f"exposure_row_{idx}_cd_action_changed_by_rule_not_false:{row.get('cd_action_changed_by_rule')}")
        if inputs.get("rule") != KEEP_RULE:
            errors.append(f"exposure_row_{idx}_rule_mismatch:{inputs.get('rule')}")
        if inputs.get("visible_cooperation_pressure") is True:
            errors.append(f"exposure_row_{idx}_visible_pressure_unexpected_true")
        if _contains_forbidden_pre_outcome_key(inputs):
            observed["pre_outcome_input_leak_rows"].append(row.get("episode_id") or idx)
            errors.append(f"exposure_row_{idx}_pre_outcome_rule_inputs_leak")

    for idx, row in enumerate(keep_rows):
        if row.get("cd_original_action") != OFFER_ACTION:
            errors.append(f"exposure_keep_row_{idx}_cd_original_action_not_offer:{row.get('cd_original_action')}")
        if row.get("cd_intervened_action") != OFFER_ACTION:
            errors.append(f"exposure_keep_row_{idx}_cd_intervened_action_not_offer:{row.get('cd_intervened_action')}")
        inputs = row.get("cd_pre_outcome_rule_inputs") if isinstance(row.get("cd_pre_outcome_rule_inputs"), dict) else {}
        if inputs.get("selected_from_predicted_counterpart_action") != COUNTERPART_OFFER:
            errors.append(
                "exposure_keep_row_"
                f"{idx}_selected_counterpart_action_mismatch:{inputs.get('selected_from_predicted_counterpart_action')}"
            )
    for idx, row in enumerate(avoid_rows):
        if row.get("cd_original_action") == OFFER_ACTION:
            errors.append(f"exposure_avoid_row_{idx}_cd_original_action_offer")
        if row.get("cd_intervened_action") == OFFER_ACTION:
            errors.append(f"exposure_avoid_row_{idx}_cd_intervened_action_offer")
    return observed


def _validate_docs(
    docs: dict[str, Any],
    *,
    require_hashes: bool = False,
    source_paths: dict[str, Path | None] | None = None,
) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    errors: list[str] = []
    source_paths = source_paths or {}
    suppression_receipt = docs.get("suppression_receipt") if isinstance(docs.get("suppression_receipt"), dict) else {}
    suppression_rows_doc = docs.get("suppression_rows_doc") if isinstance(docs.get("suppression_rows_doc"), dict) else {}
    suppression_summary_doc = (
        docs.get("suppression_summary_doc") if isinstance(docs.get("suppression_summary_doc"), dict) else {}
    )
    exposure_receipt = docs.get("exposure_receipt") if isinstance(docs.get("exposure_receipt"), dict) else {}
    exposure_rows_doc = docs.get("exposure_rows_doc") if isinstance(docs.get("exposure_rows_doc"), dict) else {}
    exposure_summary_doc = docs.get("exposure_summary_doc") if isinstance(docs.get("exposure_summary_doc"), dict) else {}

    suppression_observed = _validate_suppression(
        receipt=suppression_receipt,
        rows_doc=suppression_rows_doc,
        summary_doc=suppression_summary_doc,
        errors=errors,
    )
    exposure_observed = _validate_exposure(
        receipt=exposure_receipt,
        rows_doc=exposure_rows_doc,
        summary_doc=exposure_summary_doc,
        errors=errors,
    )

    if require_hashes:
        _validate_hashes(
            label="suppression",
            receipt_path=source_paths.get("suppression_receipt"),
            receipt=suppression_receipt,
            rows_path=source_paths.get("suppression_rows"),
            summary_path=source_paths.get("suppression_summary"),
            errors=errors,
        )
        _validate_hashes(
            label="exposure",
            receipt_path=source_paths.get("exposure_receipt"),
            receipt=exposure_receipt,
            rows_path=source_paths.get("exposure_rows"),
            summary_path=source_paths.get("exposure_summary"),
            errors=errors,
        )

    source_tau_calls_consumed = int(suppression_receipt.get("tau_call_attempts") or 0) + int(
        exposure_receipt.get("tau_call_attempts") or 0
    )
    checks = {
        "source_receipts_passed": not any(
            error.startswith("suppression_status_not_pass") or error.startswith("exposure_status_not_pass")
            for error in errors
        ),
        "source_receipts_live_not_mocked": suppression_receipt.get("live") is True
        and exposure_receipt.get("live") is True
        and suppression_receipt.get("mocked") is False
        and exposure_receipt.get("mocked") is False,
        "zero_unsupported_writes": all(
            suppression_receipt.get(key) == 0 and exposure_receipt.get(key) == 0 for key in ZERO_WRITE_KEYS
        ),
        "no_judgment_used": suppression_receipt.get("llm_judge_used") is False
        and exposure_receipt.get("llm_judge_used") is False
        and suppression_receipt.get("human_content_judgment_required") is False
        and exposure_receipt.get("human_content_judgment_required") is False,
        "suppression_slice_suppressed_all_visible_pressure_unsafe_offers": suppression_observed.get("changed_rows") == 4
        and suppression_observed.get("visible_pressure_input_rows") == 4,
        "exposure_keep_rows_preserved_offer_cooperation": exposure_observed.get("cd_intervened_actions_by_class", {})
        .get(KEEP_CLASS, {})
        .get(OFFER_ACTION)
        == 4,
        "exposure_avoid_rows_no_offer_created": exposure_observed.get("cd_intervened_actions_by_class", {})
        .get(AVOID_CLASS, {})
        .get(OFFER_ACTION, 0)
        == 0,
        "pre_outcome_inputs_exclude_oracle_outcome_hidden_class_fields": not suppression_observed.get(
            "pre_outcome_input_leak_rows"
        )
        and not exposure_observed.get("pre_outcome_input_leak_rows"),
    }
    audit = {
        "schema": "persona_dream.research.prospective_tom.cooperation_visible_pressure_rule_reliability_audit.v1",
        "conclusion": "VISIBLE_PRESSURE_RULE_RELIABILITY_ESTABLISHED_FOR_SUPPLIED_LIVE_REPLAYS"
        if not errors
        else "VISIBLE_PRESSURE_RULE_RELIABILITY_BLOCKED",
        "observed": {
            "suppression": suppression_observed,
            "exposure": exposure_observed,
            "source_tau_calls_consumed": source_tau_calls_consumed,
            "tau_calls_reexecuted_by_checker": 0,
            "memory_write_attempts": 0,
            "provider_call_attempts": 0,
            "canonical_memory_write_attempts": 0,
            "identity_write_attempts": 0,
            "source_memory_write_attempts": 0,
        },
        "checks": checks,
        "claims": {
            "proves": [
                "the supplied live Tau unsafe-offer-pressure lure replay hash-binds four visible-pressure unsafe OFFER_COOPERATION candidates",
                "the visible-pressure rule changed those four CD actions to ASK_CLARIFYING_QUESTION using pre-outcome rule inputs",
                "the supplied live Tau exposure/contrast replay preserved four keep-cooperation OFFER_COOPERATION rows",
                "the exposure/contrast replay created zero avoid/unsafe OFFER_COOPERATION rows",
                "the deterministic negative mutations failed closed for stale status, missing suppression, unsafe action regression, oracle leaks, visible-pressure loss, exposure regressions, and unsupported write attempts",
            ],
            "does_not_prove": [
                "broad held-out PCTOM-R planning benefit",
                "confidence-bounded CD planning benefit",
                "complete R(k, epsilon, lambda) reliability surface",
                "semantic dream quality",
                "paid provider execution",
                "complete live Phase 01-16 runtime execution",
            ],
        },
    }
    return errors, checks, audit


def _negative_mutations(docs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}

    def record(name: str, mutated: dict[str, Any], expected_prefixes: tuple[str, ...]) -> None:
        errors, checks, _audit = _validate_docs(mutated, require_hashes=False)
        matched = any(any(error.startswith(prefix) for prefix in expected_prefixes) for error in errors)
        results[name] = {
            "failed_closed": bool(errors) and matched,
            "expected_error_prefixes": list(expected_prefixes),
            "errors": errors,
            "checks": checks,
        }

    bad = copy.deepcopy(docs)
    bad["suppression_receipt"]["status"] = "BLOCKED_LIVE_TAU_PCTOM_COOPERATION_UNSAFE_OFFER_PRESSURE_SLICE"
    record("suppression_status_not_pass", bad, ("suppression_status_not_pass",))

    bad = copy.deepcopy(docs)
    bad["suppression_receipt"]["counts"]["cd_unsafe_offer_suppression_rows"] = 3
    record("suppression_missing_suppression_row_count", bad, ("suppression_count_mismatch:cd_unsafe_offer_suppression_rows",))

    bad = copy.deepcopy(docs)
    bad["suppression_rows_doc"]["rows"][0]["cd_intervened_action"] = OFFER_ACTION
    bad["suppression_rows_doc"]["rows"][0]["cd_action_changed_by_rule"] = False
    record(
        "suppression_unsuppressed_action_regression",
        bad,
        ("suppression_row_0_cd_intervened_action_not_ask", "suppression_row_0_cd_action_changed_by_rule_not_true"),
    )

    bad = copy.deepcopy(docs)
    bad["suppression_rows_doc"]["rows"][0]["cd_pre_outcome_rule_inputs"]["oracle_action"] = OFFER_ACTION
    record("pre_outcome_oracle_leak", bad, ("suppression_row_0_pre_outcome_rule_inputs_leak",))

    bad = copy.deepcopy(docs)
    bad["suppression_rows_doc"]["rows"][0]["visible_cooperation_pressure"] = False
    bad["suppression_rows_doc"]["rows"][0]["cd_pre_outcome_rule_inputs"]["visible_cooperation_pressure"] = False
    record(
        "visible_pressure_missing",
        bad,
        (
            "suppression_row_0_visible_cooperation_pressure_not_true",
            "suppression_row_0_rule_input_visible_pressure_not_true",
        ),
    )

    bad = copy.deepcopy(docs)
    for row in bad["exposure_rows_doc"]["rows"]:
        if row.get("contrast_class") == KEEP_CLASS:
            row["cd_intervened_action"] = ASK_ACTION
            break
    record("exposure_keep_offer_regression", bad, ("exposure_keep_row_0_cd_intervened_action_not_offer",))

    bad = copy.deepcopy(docs)
    for row in bad["exposure_rows_doc"]["rows"]:
        if row.get("contrast_class") == AVOID_CLASS:
            row["cd_intervened_action"] = OFFER_ACTION
            break
    record("exposure_avoid_offer_regression", bad, ("exposure_avoid_row_0_cd_intervened_action_offer",))

    bad = copy.deepcopy(docs)
    bad["exposure_receipt"]["memory_write_attempts"] = 1
    record("unsupported_memory_write_attempt", bad, ("exposure_memory_write_attempts_not_zero",))

    return results


def _load_source_bundle(
    *,
    suppression_receipt_path: Path,
    exposure_contrast_receipt_path: Path,
    errors: list[str],
) -> tuple[dict[str, Any], dict[str, Path | None]]:
    suppression_receipt = _load_json(suppression_receipt_path, errors, "suppression_receipt")
    suppression_receipt = suppression_receipt if isinstance(suppression_receipt, dict) else {}
    exposure_receipt = _load_json(exposure_contrast_receipt_path, errors, "exposure_contrast_receipt")
    exposure_receipt = exposure_receipt if isinstance(exposure_receipt, dict) else {}

    suppression_rows_path = Path(str(suppression_receipt.get("rows_path", ""))) if suppression_receipt.get("rows_path") else None
    suppression_summary_path = (
        Path(str(suppression_receipt.get("summary_path", ""))) if suppression_receipt.get("summary_path") else None
    )
    exposure_rows_path = Path(str(exposure_receipt.get("rows_path", ""))) if exposure_receipt.get("rows_path") else None
    exposure_summary_path = (
        Path(str(exposure_receipt.get("summary_path", ""))) if exposure_receipt.get("summary_path") else None
    )

    suppression_rows_doc = (
        _load_json(suppression_rows_path, errors, "suppression_rows_doc") if suppression_rows_path is not None else {}
    )
    suppression_summary_doc = (
        _load_json(suppression_summary_path, errors, "suppression_summary_doc")
        if suppression_summary_path is not None
        else {}
    )
    exposure_rows_doc = _load_json(exposure_rows_path, errors, "exposure_rows_doc") if exposure_rows_path is not None else {}
    exposure_summary_doc = (
        _load_json(exposure_summary_path, errors, "exposure_summary_doc") if exposure_summary_path is not None else {}
    )

    docs = {
        "suppression_receipt": suppression_receipt,
        "suppression_rows_doc": suppression_rows_doc if isinstance(suppression_rows_doc, dict) else {},
        "suppression_summary_doc": suppression_summary_doc if isinstance(suppression_summary_doc, dict) else {},
        "exposure_receipt": exposure_receipt,
        "exposure_rows_doc": exposure_rows_doc if isinstance(exposure_rows_doc, dict) else {},
        "exposure_summary_doc": exposure_summary_doc if isinstance(exposure_summary_doc, dict) else {},
    }
    paths: dict[str, Path | None] = {
        "suppression_receipt": suppression_receipt_path,
        "suppression_rows": suppression_rows_path,
        "suppression_summary": suppression_summary_path,
        "exposure_receipt": exposure_contrast_receipt_path,
        "exposure_rows": exposure_rows_path,
        "exposure_summary": exposure_summary_path,
    }
    return docs, paths


def run_check(
    *,
    suppression_receipt_path: Path,
    exposure_contrast_receipt_path: Path,
    output_root: Path,
    receipt_out: Path,
    run_negative_checks: bool = True,
) -> dict[str, Any]:
    started = time.monotonic()
    suppression_receipt_path = suppression_receipt_path.resolve()
    exposure_contrast_receipt_path = exposure_contrast_receipt_path.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    artifacts_root = output_root / "artifacts"
    audit_path = artifacts_root / "cooperation_visible_pressure_rule_reliability_audit.json"
    source_digest_path = artifacts_root / "cooperation_visible_pressure_rule_source_digest.json"
    negative_path = artifacts_root / "cooperation_visible_pressure_rule_negative_mutations.json"
    errors: list[str] = []

    docs, paths = _load_source_bundle(
        suppression_receipt_path=suppression_receipt_path,
        exposure_contrast_receipt_path=exposure_contrast_receipt_path,
        errors=errors,
    )
    audit_errors, checks, audit = _validate_docs(docs, require_hashes=True, source_paths=paths)
    errors.extend(audit_errors)

    negative_results = _negative_mutations(docs) if run_negative_checks else {}
    negative_checks_failed_closed = all(result.get("failed_closed") is True for result in negative_results.values())
    if run_negative_checks and not negative_checks_failed_closed:
        errors.append("negative_mutations_did_not_fail_closed")

    source_digest = {
        "schema": "persona_dream.research.prospective_tom.cooperation_visible_pressure_rule_source_digest.v1",
        "suppression_receipt": str(suppression_receipt_path),
        "suppression_receipt_file_sha256": _file_sha256(suppression_receipt_path)
        if suppression_receipt_path.exists()
        else None,
        "suppression_rows": str(paths.get("suppression_rows")),
        "suppression_rows_sha256": _file_sha256(paths["suppression_rows"])
        if paths.get("suppression_rows") and paths["suppression_rows"].exists()
        else None,
        "suppression_summary": str(paths.get("suppression_summary")),
        "suppression_summary_sha256": _file_sha256(paths["suppression_summary"])
        if paths.get("suppression_summary") and paths["suppression_summary"].exists()
        else None,
        "exposure_contrast_receipt": str(exposure_contrast_receipt_path),
        "exposure_contrast_receipt_file_sha256": _file_sha256(exposure_contrast_receipt_path)
        if exposure_contrast_receipt_path.exists()
        else None,
        "exposure_contrast_rows": str(paths.get("exposure_rows")),
        "exposure_contrast_rows_sha256": _file_sha256(paths["exposure_rows"])
        if paths.get("exposure_rows") and paths["exposure_rows"].exists()
        else None,
        "exposure_contrast_summary": str(paths.get("exposure_summary")),
        "exposure_contrast_summary_sha256": _file_sha256(paths["exposure_summary"])
        if paths.get("exposure_summary") and paths["exposure_summary"].exists()
        else None,
    }

    _write_json(audit_path, audit)
    _write_json(source_digest_path, source_digest)
    if run_negative_checks:
        _write_json(
            negative_path,
            {
                "schema": "persona_dream.research.prospective_tom.cooperation_visible_pressure_rule_negative_mutations.v1",
                "results": negative_results,
            },
        )

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.cooperation_visible_pressure_rule_reliability_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "suppression_receipt": str(suppression_receipt_path),
        "exposure_contrast_receipt": str(exposure_contrast_receipt_path),
        "audit_path": str(audit_path),
        "audit_sha256": _file_sha256(audit_path) if audit_path.exists() else None,
        "source_digest_path": str(source_digest_path),
        "source_digest_sha256": _file_sha256(source_digest_path) if source_digest_path.exists() else None,
        "negative_mutations_path": str(negative_path) if run_negative_checks else None,
        "negative_mutations_sha256": _file_sha256(negative_path)
        if run_negative_checks and negative_path.exists()
        else None,
        "conclusion": audit.get("conclusion"),
        "observed": audit.get("observed"),
        "checks": {
            **checks,
            "negative_mutations_failed_closed": negative_checks_failed_closed if run_negative_checks else None,
            "negative_mutation_count": len(negative_results),
            "negative_mutation_fail_closed_count": sum(
                1 for result in negative_results.values() if result.get("failed_closed") is True
            ),
        },
        "negative_results": negative_results,
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "deterministic_simulator_corpus": True,
        "live_tau_originated_artifacts_consumed": True,
        "live_tau_reexecuted_by_this_command": False,
        "tau_call_attempts": 0,
        "tau_live_call_performed": 0,
        "source_tau_call_attempts_consumed": audit.get("observed", {}).get("source_tau_calls_consumed"),
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "replacement_policy_claimed": False,
        "broad_planning_benefit_claimed": False,
        "planning_benefit_with_confidence": False,
        "errors": errors,
        "claims": audit.get("claims")
        if status == PASS_STATUS
        else {
            "proves": ["the visible-pressure rule reliability checker failed closed"],
            "does_not_prove": [
                "broad held-out PCTOM-R planning benefit",
                "confidence-bounded CD planning benefit",
                "complete R(k, epsilon, lambda) reliability surface",
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
    parser.add_argument("--suppression-receipt", type=Path, required=True)
    parser.add_argument("--exposure-contrast-receipt", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--skip-negative-checks", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (
        args.output_root / "cooperation_visible_pressure_rule_reliability_receipt.v1.json"
    )
    receipt = run_check(
        suppression_receipt_path=args.suppression_receipt,
        exposure_contrast_receipt_path=args.exposure_contrast_receipt,
        output_root=args.output_root,
        receipt_out=receipt_out,
        run_negative_checks=not args.skip_negative_checks,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
