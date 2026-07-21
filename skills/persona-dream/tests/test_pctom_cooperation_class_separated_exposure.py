"""Unit checks for the PCTOM-R cooperation class-separation audit.

These tests exercise deterministic helper logic only. They do not call Tau,
Memory, providers, or judge semantic dream quality.
"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    ROOT
    / "research"
    / "prospective-tom"
    / "scripts"
    / "check_cooperation_class_separated_exposure.py"
)


spec = importlib.util.spec_from_file_location("check_cooperation_class_separated_exposure", SCRIPT_PATH)
assert spec and spec.loader
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def _row(episode_id: str, contrast_class: str, action: str, counterpart_action: str) -> dict:
    return {
        "episode_id": episode_id,
        "variant": 37,
        "contrast_class": contrast_class,
        "cd_original_action": action,
        "cd_intervened_action": action,
        "cd_action_changed_by_rule": False,
        "cd_pre_outcome_rule_inputs": {
            "uses_outcome_or_oracle": False,
            "selected_from_predicted_counterpart_action": counterpart_action,
            "original_selected_action": action,
        },
    }


def _docs() -> tuple[dict, dict, dict]:
    rows = [
        _row("keep-1", audit.KEEP_CLASS, audit.OFFER_ACTION, audit.COUNTERPART_OFFER),
        _row("keep-2", audit.KEEP_CLASS, audit.OFFER_ACTION, audit.COUNTERPART_OFFER),
        _row("avoid-1", audit.AVOID_CLASS, "WAIT", "KAI_ASKS_TO_WAIT"),
        _row("avoid-2", audit.AVOID_CLASS, "DISCLOSE_INFORMATION", "KAI_DISCLOSES_AUTHORITY_CONSTRAINT"),
    ]
    rows_doc = {"rows": rows}
    summary_doc = {
        "rows": 4,
        "keep_cooperation_positive_rows": 2,
        "avoid_or_unsafe_cooperation_contrast_rows": 2,
        "offer_cooperation_affordance_rows": 4,
        "cd_action_change_count": 0,
        "cd_offer_cooperation_candidates": 2,
    }
    receipt = {
        "status": audit.LIVE_SLICE_PASS_STATUS,
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "planning_benefit_with_confidence": False,
        "llm_judge_used": False,
        "human_content_judgment_required": False,
        "counts": {
            "rows": 4,
            "keep_cooperation_positive_rows": 2,
            "avoid_or_unsafe_cooperation_contrast_rows": 2,
            "offer_cooperation_affordance_rows": 4,
            "cd_action_change_count": 0,
            "cd_offer_cooperation_candidates": 2,
        },
        **{key: 0 for key in audit.ZERO_WRITE_KEYS},
    }
    return receipt, rows_doc, summary_doc


def test_class_separated_exposure_is_observed_but_feature_split_stays_blocked():
    receipt, rows_doc, summary_doc = _docs()

    errors, checks, result = audit._validate_inputs(
        live_slice_receipt=receipt,
        rows_doc=rows_doc,
        summary_doc=summary_doc,
        require_hashes=False,
    )

    assert errors == []
    assert checks["class_separated_cd_discrimination_observed"] is True
    assert checks["feature_split_acceptance_allowed"] is False
    assert checks["feature_split_blocked_without_unsafe_offer_suppression"] is True
    assert result["conclusion"] == "CD_CLASS_SEPARATED_COOPERATION_OBSERVED_FEATURE_SPLIT_STILL_BLOCKED"
    assert result["observed"]["keep_offer_rows"] == 2
    assert result["observed"]["avoid_offer_rows"] == 0


def test_avoid_offer_fails_class_separation():
    receipt, rows_doc, summary_doc = _docs()
    mutated = copy.deepcopy(rows_doc)
    mutated["rows"][2]["cd_original_action"] = audit.OFFER_ACTION

    errors, checks, result = audit._validate_inputs(
        live_slice_receipt=receipt,
        rows_doc=mutated,
        summary_doc=summary_doc,
        require_hashes=False,
    )

    assert any(error.startswith("avoid_rows_offer_cooperation") for error in errors)
    assert checks["avoid_rows_no_offer_cooperation"] is False
    assert result["class_separated_cd_discrimination_observed"] is False


def test_pre_outcome_oracle_leak_fails_closed():
    receipt, rows_doc, summary_doc = _docs()
    mutated = copy.deepcopy(rows_doc)
    mutated["rows"][0]["cd_pre_outcome_rule_inputs"]["oracle_action"] = audit.OFFER_ACTION

    errors, checks, result = audit._validate_inputs(
        live_slice_receipt=receipt,
        rows_doc=mutated,
        summary_doc=summary_doc,
        require_hashes=False,
    )

    assert any(error.startswith("pre_outcome_rule_inputs_leak") for error in errors)
    assert checks["pre_outcome_inputs_exclude_oracle_or_outcome"] is False
    assert result["class_separated_cd_discrimination_observed"] is False


def test_negative_checks_all_fail_closed():
    receipt, rows_doc, summary_doc = _docs()

    results = audit._negative_checks(
        live_slice_receipt=receipt,
        rows_doc=rows_doc,
        summary_doc=summary_doc,
    )

    assert set(results) == {
        "live_slice_status_not_pass",
        "missing_keep_offer_cooperation",
        "avoid_row_offer_cooperation",
        "pre_outcome_oracle_leak",
        "planning_benefit_claim_injected",
    }
    assert all(result["failed_closed"] is True for result in results.values())
