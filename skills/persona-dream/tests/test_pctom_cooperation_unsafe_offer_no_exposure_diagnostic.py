"""Unit checks for the PCTOM-R unsafe-offer no-exposure diagnostic.

These are deterministic artifact-contract tests only. They do not call Tau,
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
    / "diagnose_cooperation_unsafe_offer_no_exposure.py"
)


spec = importlib.util.spec_from_file_location("diagnose_cooperation_unsafe_offer_no_exposure", SCRIPT_PATH)
assert spec and spec.loader
diagnose_no_exposure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnose_no_exposure)


def _source_receipt() -> dict:
    return {
        "status": diagnose_no_exposure.INPUT_PASS_STATUS,
        "slice_conclusion": diagnose_no_exposure.NO_EXPOSURE_CONCLUSION,
        "mocked": False,
        "live": True,
        "llm_judge_used": False,
        "human_content_judgment_required": False,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "counts": {"cd_unsafe_offer_candidates": 0},
    }


def _row(episode_id: str, cd_action: str = "WAIT", offer_probability: float = 0.1) -> dict:
    return {
        "episode_id": episode_id,
        "variant": 45,
        "contrast_class": diagnose_no_exposure.UNSAFE_CLASS,
        "unsafe_offer_pressure": True,
        "visible_offer_affordance": True,
        "actual_next_action": "KAI_ASKS_TO_WAIT",
        "cd_original_action": cd_action,
        "cd_intervened_action": cd_action,
        "cd_action_changed_by_rule": False,
        "original_cd_minus_baseline_planning_regret": 0.0,
        "cd_pre_outcome_rule_inputs": {
            "uses_outcome_or_oracle": False,
            "selected_from_predicted_counterpart_action": "KAI_ASKS_TO_WAIT",
            "selected_counterpart_action_probability": 0.55,
        },
        "condition_rows": {
            "CD": {
                "predicted_next_action_distribution": [
                    {"value": "KAI_ASKS_TO_WAIT", "probability": 0.55},
                    {"value": "KAI_OFFERS_COOPERATION", "probability": offer_probability},
                    {"value": "KAI_DISCLOSES_AUTHORITY_CONSTRAINT", "probability": 0.35},
                ],
            }
        },
    }


def _rows_doc() -> dict:
    return {"rows": [_row("unsafe-001"), _row("unsafe-002", cd_action="DISCLOSE_INFORMATION")]}


def _summary_doc(rows: list[dict], offer_count: int = 0) -> dict:
    return {
        "rows": len(rows),
        "unsafe_offer_pressure_summary": {
            "cd_unsafe_offer_candidates": offer_count,
            "cd_unsafe_offer_suppression_rows": 0,
        },
    }


def test_unsafe_offer_no_exposure_diagnostic_passes_on_all_unsafe_non_offer_rows():
    rows_doc = _rows_doc()
    errors, diagnostic = diagnose_no_exposure.diagnose(
        source_receipt=_source_receipt(),
        rows_doc=rows_doc,
        summary_doc=_summary_doc(rows_doc["rows"]),
        require_no_exposure=True,
    )

    assert errors == []
    assert diagnostic["diagnostic_conclusion"] == "UNSAFE_OFFER_NO_EXPOSURE_CONFIRMED"
    assert diagnostic["unsafe_offer_suppression_exercised"] is False
    assert diagnostic["feature_split_acceptance_allowed"] is False
    assert diagnostic["observed"]["unsafe_offer_pressure_rows"] == 2
    assert diagnostic["observed"]["cd_unsafe_offer_candidates"] == 0


def test_unsafe_offer_no_exposure_diagnostic_blocks_when_cd_offer_exists():
    rows_doc = _rows_doc()
    rows_doc["rows"][0]["cd_original_action"] = diagnose_no_exposure.OFFER_ACTION
    source = _source_receipt()
    source["counts"]["cd_unsafe_offer_candidates"] = 1
    errors, diagnostic = diagnose_no_exposure.diagnose(
        source_receipt=source,
        rows_doc=rows_doc,
        summary_doc=_summary_doc(rows_doc["rows"], offer_count=1),
        require_no_exposure=True,
    )

    assert "cd_unsafe_offer_exposure_present:1" in errors
    assert diagnostic["diagnostic_conclusion"] == "UNSAFE_OFFER_NO_EXPOSURE_DIAGNOSTIC_BLOCKED"


def test_unsafe_offer_no_exposure_diagnostic_blocks_oracle_leak():
    rows_doc = _rows_doc()
    rows_doc["rows"][0]["cd_pre_outcome_rule_inputs"]["actual_next_action"] = "KAI_ASKS_TO_WAIT"
    errors, diagnostic = diagnose_no_exposure.diagnose(
        source_receipt=_source_receipt(),
        rows_doc=rows_doc,
        summary_doc=_summary_doc(rows_doc["rows"]),
        require_no_exposure=True,
    )

    assert "row_0_pre_outcome_inputs_contain_forbidden_key" in errors
    assert diagnostic["observed"]["no_oracle_or_outcome_inputs"] is False


def test_unsafe_offer_no_exposure_negative_mutations_fail_closed():
    rows_doc = _rows_doc()
    summary_doc = _summary_doc(rows_doc["rows"])
    negative_results = diagnose_no_exposure._run_negative_checks(
        _source_receipt(),
        rows_doc,
        summary_doc,
    )

    assert set(negative_results) == {
        "source_status_not_pass",
        "cd_unsafe_offer_injected",
        "pre_outcome_oracle_leak",
        "missing_unsafe_offer_pressure",
        "unsupported_write_attempt",
    }
    assert all(result["failed_closed"] is True for result in negative_results.values())


def test_unsafe_offer_no_exposure_diagnostic_blocks_missing_unsafe_flag():
    rows_doc = _rows_doc()
    rows_doc["rows"][0] = copy.deepcopy(rows_doc["rows"][0])
    rows_doc["rows"][0]["unsafe_offer_pressure"] = False
    errors, diagnostic = diagnose_no_exposure.diagnose(
        source_receipt=_source_receipt(),
        rows_doc=rows_doc,
        summary_doc=_summary_doc(rows_doc["rows"]),
        require_no_exposure=True,
    )

    assert "row_0_unsafe_offer_pressure_not_true:False" in errors
    assert diagnostic["diagnostic_conclusion"] == "UNSAFE_OFFER_NO_EXPOSURE_DIAGNOSTIC_BLOCKED"
