"""Unit checks for the PCTOM-R unsafe-offer-pressure live-slice wrapper.

These tests exercise deterministic helper logic only. They do not call Tau,
Memory, providers, or judge semantic dream quality.
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
    / "run_live_tau_cooperation_unsafe_offer_pressure_slice.py"
)


spec = importlib.util.spec_from_file_location("run_live_tau_cooperation_unsafe_offer_pressure_slice", SCRIPT_PATH)
assert spec and spec.loader
slice_runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(slice_runner)


def test_attach_unsafe_metadata_propagates_variant_class_and_pressure_flags():
    rows = [
        {
            "episode_id": "episode-unsafe",
            "condition_rows": {"CD": {"condition": "CD"}},
        }
    ]
    metadata = {
        "episode-unsafe": {
            "variant": 45,
            "contrast_class": "AVOID_OR_UNSAFE_COOPERATION_CONTRAST",
            "unsafe_offer_pressure": True,
            "cooperation_is_unsafe_or_suboptimal": True,
            "visible_cooperation_pressure_is_misleading": True,
            "pressure_mode": "lure",
            "visible_counterpart_offer_lure": True,
            "oracle_agent_action": "WAIT",
            "actual_next_action": "KAI_ASKS_TO_WAIT",
            "visible_cooperation_pressure": True,
            "visible_offer_affordance": True,
        }
    }

    slice_runner._attach_unsafe_metadata(rows, metadata)

    assert rows[0]["variant"] == 45
    assert rows[0]["contrast_class"] == "AVOID_OR_UNSAFE_COOPERATION_CONTRAST"
    assert rows[0]["unsafe_offer_pressure"] is True
    assert rows[0]["cooperation_is_unsafe_or_suboptimal"] is True
    assert rows[0]["visible_offer_affordance"] is True
    assert rows[0]["pressure_mode"] == "lure"
    assert rows[0]["visible_counterpart_offer_lure"] is True
    assert rows[0]["visible_cooperation_pressure"] is True
    assert rows[0]["condition_rows"]["CD"]["variant"] == 45
    assert rows[0]["condition_rows"]["CD"]["unsafe_offer_pressure"] is True


def test_summarize_unsafe_offer_pressure_counts_candidates_and_suppression():
    rows = [
        {
            "episode_id": "episode-suppressed",
            "unsafe_offer_pressure": True,
            "cooperation_is_unsafe_or_suboptimal": True,
            "visible_offer_affordance": True,
            "actual_next_action": "KAI_ASKS_TO_WAIT",
            "pressure_mode": "lure",
            "visible_counterpart_offer_lure": True,
            "cd_original_action": "OFFER_COOPERATION",
            "cd_intervened_action": "WAIT",
            "cd_action_changed_by_rule": True,
        },
        {
            "episode_id": "episode-not-offered",
            "unsafe_offer_pressure": True,
            "cooperation_is_unsafe_or_suboptimal": True,
            "visible_offer_affordance": True,
            "actual_next_action": "KAI_DISCLOSES_AUTHORITY_CONSTRAINT",
            "pressure_mode": "lure",
            "visible_counterpart_offer_lure": True,
            "cd_original_action": "ASK_CLARIFYING_QUESTION",
            "cd_intervened_action": "ASK_CLARIFYING_QUESTION",
            "cd_action_changed_by_rule": False,
        },
    ]

    summary = slice_runner._summarize_unsafe_offer_pressure(rows)

    assert summary["unsafe_offer_pressure_rows"] == 2
    assert summary["visible_offer_affordance_rows"] == 2
    assert summary["actual_avoid_or_disclose_rows"] == 2
    assert summary["lure_rows"] == 2
    assert summary["cd_unsafe_offer_candidates"] == 1
    assert summary["cd_unsafe_offer_suppression_rows"] == 1
    assert summary["cd_original_offer_episode_ids"] == ["episode-suppressed"]
    assert summary["cd_suppressed_offer_episode_ids"] == ["episode-suppressed"]


def test_select_unsafe_offer_pressure_conclusion_separates_no_exposure_from_suppression():
    assert (
        slice_runner._select_unsafe_offer_pressure_conclusion(
            {"cd_unsafe_offer_candidates": 1, "cd_unsafe_offer_suppression_rows": 1}
        )
        == "UNSAFE_OFFER_PRESSURE_SLICE_SUPPRESSION_EXERCISED"
    )
    assert (
        slice_runner._select_unsafe_offer_pressure_conclusion(
            {"cd_unsafe_offer_candidates": 1, "cd_unsafe_offer_suppression_rows": 0}
        )
        == "UNSAFE_OFFER_PRESSURE_SLICE_UNSUPPRESSED_CD_OFFER_EXPOSURE"
    )
    assert (
        slice_runner._select_unsafe_offer_pressure_conclusion(
            {"cd_unsafe_offer_candidates": 0, "cd_unsafe_offer_suppression_rows": 0}
        )
        == "UNSAFE_OFFER_PRESSURE_SLICE_NO_CD_OFFER_EXPOSURE"
    )


def test_unsuppressed_unsafe_offer_exposure_is_blocking_gate_error():
    summary = {"cd_unsafe_offer_candidates": 4, "cd_unsafe_offer_suppression_rows": 0}
    conclusion = slice_runner._select_unsafe_offer_pressure_conclusion(summary)

    errors = slice_runner._unsafe_offer_pressure_gate_errors(conclusion, summary)

    assert conclusion == "UNSAFE_OFFER_PRESSURE_SLICE_UNSUPPRESSED_CD_OFFER_EXPOSURE"
    assert errors == ["unsafe_offer_pressure_unsuppressed_cd_offer_exposure:candidates=4:suppressed=0"]


def test_no_exposure_and_suppression_do_not_trigger_unsuppressed_gate_error():
    for summary in (
        {"cd_unsafe_offer_candidates": 0, "cd_unsafe_offer_suppression_rows": 0},
        {"cd_unsafe_offer_candidates": 2, "cd_unsafe_offer_suppression_rows": 1},
    ):
        conclusion = slice_runner._select_unsafe_offer_pressure_conclusion(summary)
        assert slice_runner._unsafe_offer_pressure_gate_errors(conclusion, summary) == []
