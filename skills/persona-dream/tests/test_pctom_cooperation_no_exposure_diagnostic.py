"""Unit checks for the PCTOM-R cooperation no-exposure diagnostic.

These are deterministic artifact-contract tests only. They do not call Tau,
Memory, providers, or judge semantic dream quality.
"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "research" / "prospective-tom" / "scripts" / "diagnose_cooperation_no_exposure.py"


spec = importlib.util.spec_from_file_location("diagnose_cooperation_no_exposure", SCRIPT_PATH)
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
    }


def _row(episode_id: str, contrast_class: str, cd_action: str, oracle_action: str, offer_probability: float) -> dict:
    if offer_probability >= 0.5:
        distribution = [
            {"value": "KAI_OFFERS_COOPERATION", "probability": offer_probability},
            {"value": "KAI_ASKS_TO_WAIT", "probability": 1.0 - offer_probability},
        ]
    else:
        distribution = [
            {"value": "KAI_ASKS_TO_WAIT", "probability": 1.0 - offer_probability},
            {"value": "KAI_OFFERS_COOPERATION", "probability": offer_probability},
        ]
    return {
        "episode_id": episode_id,
        "variant": 101,
        "contrast_class": contrast_class,
        "cd_original_action": cd_action,
        "original_cd_minus_baseline_planning_regret": 0.0,
        "cd_pre_outcome_rule_inputs": {
            "uses_outcome_or_oracle": False,
            "selected_from_predicted_counterpart_action": distribution[0]["value"],
            "selected_counterpart_action_probability": distribution[0]["probability"],
        },
        "condition_rows": {
            "CD": {
                "oracle_action": oracle_action,
                "predicted_next_action_distribution": distribution,
            }
        },
    }


def _rows_doc() -> dict:
    return {
        "rows": [
            _row(
                "keep-001",
                diagnose_no_exposure.KEEP_CLASS,
                "WAIT",
                diagnose_no_exposure.OFFER_ACTION,
                0.35,
            ),
            _row(
                "avoid-001",
                diagnose_no_exposure.AVOID_CLASS,
                "DISCLOSE_INFORMATION",
                "WAIT",
                0.10,
            ),
        ]
    }


def _summary_doc(rows: list[dict], offer_count: int = 0) -> dict:
    return {"rows": len(rows), "cd_offer_cooperation_candidates": offer_count}


def test_no_exposure_diagnostic_passes_with_keep_and_avoid_rows():
    rows_doc = _rows_doc()
    errors, diagnostic = diagnose_no_exposure.diagnose(
        source_receipt=_source_receipt(),
        rows_doc=rows_doc,
        summary_doc=_summary_doc(rows_doc["rows"]),
        require_no_exposure=True,
    )
    assert errors == []
    assert diagnostic["diagnostic_conclusion"] == "NO_CD_OFFER_EXPOSURE_CONFIRMED"
    assert diagnostic["feature_split_acceptance_allowed"] is False
    assert diagnostic["observed"]["cd_offer_cooperation_candidates"] == 0
    assert diagnostic["observed"]["contrast_class_counts"] == {
        diagnose_no_exposure.KEEP_CLASS: 1,
        diagnose_no_exposure.AVOID_CLASS: 1,
    }


def test_no_exposure_diagnostic_blocks_when_cd_offer_exposure_exists():
    rows_doc = _rows_doc()
    rows_doc["rows"][0]["cd_original_action"] = diagnose_no_exposure.OFFER_ACTION
    errors, diagnostic = diagnose_no_exposure.diagnose(
        source_receipt=_source_receipt(),
        rows_doc=rows_doc,
        summary_doc=_summary_doc(rows_doc["rows"], offer_count=1),
        require_no_exposure=True,
    )
    assert "cd_offer_exposure_present:1" in errors
    assert diagnostic["diagnostic_conclusion"] == "NO_EXPOSURE_DIAGNOSTIC_BLOCKED"


def test_no_exposure_diagnostic_blocks_without_avoid_contrast_rows():
    rows_doc = _rows_doc()
    rows_doc["rows"] = [copy.deepcopy(rows_doc["rows"][0])]
    errors, diagnostic = diagnose_no_exposure.diagnose(
        source_receipt=_source_receipt(),
        rows_doc=rows_doc,
        summary_doc=_summary_doc(rows_doc["rows"]),
        require_no_exposure=True,
    )
    assert "missing_avoid_contrast_rows" in errors
    assert diagnostic["diagnostic_conclusion"] == "NO_EXPOSURE_DIAGNOSTIC_BLOCKED"
