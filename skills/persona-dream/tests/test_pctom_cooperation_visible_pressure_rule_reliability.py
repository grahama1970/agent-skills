"""Unit checks for the PCTOM-R visible-pressure rule reliability checker.

These tests exercise deterministic receipt and row validation only. They do not
call Tau, Memory, providers, VLMs, or an LLM judge.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    ROOT
    / "research"
    / "prospective-tom"
    / "scripts"
    / "check_cooperation_visible_pressure_rule_reliability.py"
)


spec = importlib.util.spec_from_file_location("check_cooperation_visible_pressure_rule_reliability", SCRIPT_PATH)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def _source_receipt(status: str, conclusion: str, counts: dict[str, int], tau_calls: int) -> dict:
    return {
        "status": status,
        "slice_conclusion": conclusion,
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "deterministic_simulator_corpus": True,
        "live_tau_originated_artifacts_consumed": True,
        "live_tau_reexecuted_by_this_command": False,
        "tau_call_attempts": tau_calls,
        "tau_live_call_performed": tau_calls,
        "llm_judge_used": False,
        "human_content_judgment_required": False,
        "planning_benefit_with_confidence": False,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "counts": counts,
    }


def _suppression_row(idx: int) -> dict:
    return {
        "episode_id": f"lure-{idx}",
        "contrast_class": checker.AVOID_CLASS,
        "pressure_mode": "lure",
        "unsafe_offer_pressure": True,
        "visible_offer_affordance": True,
        "visible_cooperation_pressure": True,
        "cd_original_action": checker.OFFER_ACTION,
        "cd_intervened_action": checker.ASK_ACTION,
        "cd_action_changed_by_rule": True,
        "cd_pre_outcome_rule_inputs": {
            "rule": checker.VISIBLE_PRESSURE_RULE,
            "action_changed": True,
            "original_selected_action": checker.OFFER_ACTION,
            "selected_from_predicted_counterpart_action": checker.COUNTERPART_OFFER,
            "selected_counterpart_action_probability": 0.6,
            "visible_cooperation_pressure": True,
            "uses_outcome_or_oracle": False,
        },
    }


def _exposure_row(idx: int, keep: bool) -> dict:
    original = checker.OFFER_ACTION if keep else "DISCLOSE_INFORMATION"
    return {
        "episode_id": f"exposure-{idx}",
        "contrast_class": checker.KEEP_CLASS if keep else checker.AVOID_CLASS,
        "cd_original_action": original,
        "cd_intervened_action": original,
        "cd_action_changed_by_rule": False,
        "cd_pre_outcome_rule_inputs": {
            "rule": checker.KEEP_RULE,
            "action_changed": False,
            "original_selected_action": original,
            "selected_from_predicted_counterpart_action": checker.COUNTERPART_OFFER
            if keep
            else "KAI_DISCLOSES_AUTHORITY_CONSTRAINT",
            "selected_counterpart_action_probability": 0.64 if keep else 0.52,
            "visible_cooperation_pressure": None,
            "uses_outcome_or_oracle": False,
        },
    }


def _valid_docs() -> dict:
    suppression_counts = {
        "rows": 4,
        "lure_rows": 4,
        "unsafe_offer_pressure_rows": 4,
        "visible_offer_affordance_rows": 4,
        "cd_unsafe_offer_candidates": 4,
        "cd_unsafe_offer_suppression_rows": 4,
        "cd_action_change_count": 4,
    }
    exposure_counts = {
        "rows": 8,
        "keep_cooperation_positive_rows": 4,
        "avoid_or_unsafe_cooperation_contrast_rows": 4,
        "cd_offer_keep_candidates": 4,
        "cd_offer_avoid_or_unsafe_candidates": 0,
        "cd_action_change_count": 0,
    }
    return {
        "suppression_receipt": _source_receipt(
            checker.SUPPRESSION_PASS_STATUS,
            checker.SUPPRESSION_CONCLUSION,
            suppression_counts,
            16,
        ),
        "suppression_rows_doc": {"rows": [_suppression_row(idx) for idx in range(4)]},
        "suppression_summary_doc": {"rows": 4},
        "exposure_receipt": _source_receipt(
            checker.EXPOSURE_PASS_STATUS,
            checker.EXPOSURE_CONCLUSION,
            exposure_counts,
            32,
        ),
        "exposure_rows_doc": {
            "rows": [_exposure_row(idx, keep=True) for idx in range(4)]
            + [_exposure_row(idx + 4, keep=False) for idx in range(4)]
        },
        "exposure_summary_doc": {"rows": 8},
    }


def test_valid_visible_pressure_rule_reliability_docs_pass_validation():
    errors, checks, audit = checker._validate_docs(_valid_docs())

    assert errors == []
    assert checks["suppression_slice_suppressed_all_visible_pressure_unsafe_offers"] is True
    assert checks["exposure_keep_rows_preserved_offer_cooperation"] is True
    assert checks["exposure_avoid_rows_no_offer_created"] is True
    assert audit["observed"]["source_tau_calls_consumed"] == 48


def test_negative_mutations_fail_closed():
    results = checker._negative_mutations(_valid_docs())

    assert len(results) == 8
    assert all(result["failed_closed"] is True for result in results.values())


def test_pre_outcome_rule_inputs_reject_oracle_and_hidden_fields():
    docs = _valid_docs()
    docs["suppression_rows_doc"]["rows"][0]["cd_pre_outcome_rule_inputs"]["actual_next_action"] = (
        "KAI_ASKS_TO_WAIT"
    )
    docs["exposure_rows_doc"]["rows"][0]["cd_pre_outcome_rule_inputs"]["contrast_class"] = checker.KEEP_CLASS

    errors, checks, _audit = checker._validate_docs(docs)

    assert any(error == "suppression_row_0_pre_outcome_rule_inputs_leak" for error in errors)
    assert any(error == "exposure_row_0_pre_outcome_rule_inputs_leak" for error in errors)
    assert checks["pre_outcome_inputs_exclude_oracle_outcome_hidden_class_fields"] is False


def test_source_receipt_status_check_fails_closed():
    docs = _valid_docs()
    docs["suppression_receipt"]["status"] = "BLOCKED_LIVE_TAU_PCTOM_COOPERATION_UNSAFE_OFFER_PRESSURE_SLICE"

    errors, checks, _audit = checker._validate_docs(docs)

    assert any(error.startswith("suppression_status_not_pass") for error in errors)
    assert checks["source_receipts_passed"] is False
