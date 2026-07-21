"""Unit checks for the PCTOM-R cooperation exposure/contrast live-slice wrapper.

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
    / "run_live_tau_cooperation_exposure_contrast_slice.py"
)


spec = importlib.util.spec_from_file_location("run_live_tau_cooperation_exposure_contrast_slice", SCRIPT_PATH)
assert spec and spec.loader
slice_runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(slice_runner)


def test_attach_contrast_metadata_propagates_variant_and_hidden_class():
    rows = [
        {
            "episode_id": "episode-keep",
            "condition_rows": {"CD": {"condition": "CD"}},
        }
    ]
    metadata = {"episode-keep": {"variant": 37, "contrast_class": "KEEP_COOPERATION_POSITIVE"}}

    slice_runner._attach_contrast_metadata(rows, metadata)

    assert rows[0]["variant"] == 37
    assert rows[0]["contrast_class"] == "KEEP_COOPERATION_POSITIVE"
    assert rows[0]["condition_rows"]["CD"]["variant"] == 37
    assert rows[0]["condition_rows"]["CD"]["contrast_class"] == "KEEP_COOPERATION_POSITIVE"


def test_summarize_contrast_exposure_keeps_keep_and_avoid_buckets_separate():
    rows = [
        {
            "episode_id": "episode-keep",
            "cd_original_action": "OFFER_COOPERATION",
            "cd_intervened_action": "WAIT",
            "cd_action_changed_by_rule": True,
        },
        {
            "episode_id": "episode-avoid",
            "cd_original_action": "ASK_CLARIFYING_QUESTION",
            "cd_intervened_action": "ASK_CLARIFYING_QUESTION",
            "cd_action_changed_by_rule": False,
        },
    ]
    contrast_by_episode = {
        "episode-keep": "KEEP_COOPERATION_POSITIVE",
        "episode-avoid": "AVOID_OR_UNSAFE_COOPERATION_CONTRAST",
    }

    summary = slice_runner._summarize_contrast_exposure(rows, contrast_by_episode)

    assert summary["rows_by_contrast_class"] == {
        "KEEP_COOPERATION_POSITIVE": 1,
        "AVOID_OR_UNSAFE_COOPERATION_CONTRAST": 1,
    }
    assert summary["cd_offer_candidates_by_contrast_class"] == {"KEEP_COOPERATION_POSITIVE": 1}
    assert summary["cd_action_changes_by_contrast_class"] == {"KEEP_COOPERATION_POSITIVE": 1}
    assert summary["cd_original_actions_by_contrast_class"]["AVOID_OR_UNSAFE_COOPERATION_CONTRAST"] == {
        "ASK_CLARIFYING_QUESTION": 1
    }


def test_select_exposure_contrast_conclusion_requires_both_classes_for_full_exposure():
    assert (
        slice_runner._select_exposure_contrast_conclusion(2, 1, 1)
        == "EXPOSURE_CONTRAST_SLICE_HAS_KEEP_AND_AVOID_CD_OFFER_EXPOSURE"
    )
    assert (
        slice_runner._select_exposure_contrast_conclusion(1, 1, 0)
        == "EXPOSURE_CONTRAST_SLICE_PARTIAL_CD_OFFER_EXPOSURE"
    )
    assert (
        slice_runner._select_exposure_contrast_conclusion(0, 0, 0)
        == "EXPOSURE_CONTRAST_SLICE_LIVE_TAU_NO_CD_OFFER_EXPOSURE"
    )
