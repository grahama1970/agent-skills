"""A panel that cannot show which tier answered has not shown what it claims.

Browser lanes recorded `model: None` / `requested_model: None`, so a roundtable
could request `Pro` from three seats and leave no evidence of what actually
answered. Surf's meta carried it all along.
"""

from __future__ import annotations

from ask import model_provenance as mp


def test_a_matching_observation_is_the_only_confirmation() -> None:
    block = mp.from_submit_meta(
        {"requested_reasoning": "Pro", "selected_reasoning": "Pro"}, handler="webgpt"
    )
    assert block["provenance_status"] == mp.CONFIRMED
    assert block["reasoning_proven"] is True


def test_a_request_with_no_confirmation_is_unconfirmed_not_confirmed() -> None:
    """The exact shape observed on disk: asked for Pro, told nothing back."""
    block = mp.from_submit_meta(
        {
            "requested_reasoning": "Pro",
            "selected_reasoning": None,
            "reasoning_selection_status": None,
            "observed_requested_reasoning": None,
        },
        handler="webgpt",
    )
    assert block["provenance_status"] == mp.UNCONFIRMED
    assert block["reasoning_proven"] is False


def test_a_different_observed_tier_is_a_mismatch() -> None:
    block = mp.from_submit_meta(
        {"requested_reasoning": "Pro", "selected_reasoning": "Auto"}, handler="webgpt"
    )
    assert block["provenance_status"] == mp.MISMATCH
    assert block["reasoning_proven"] is False


def test_the_observed_field_also_counts_as_evidence() -> None:
    """Surf reports the observation under two names by code path."""
    block = mp.from_submit_meta(
        {"requested_reasoning": "Pro", "observed_requested_reasoning": "Pro"}
    )
    assert block["provenance_status"] == mp.CONFIRMED


def test_a_selection_error_outranks_a_matching_observation() -> None:
    block = mp.from_submit_meta(
        {
            "requested_reasoning": "Pro",
            "selected_reasoning": "Pro",
            "reasoning_selection_error": "dropdown not found",
        }
    )
    assert block["provenance_status"] == mp.FAILED
    assert block["reasoning_proven"] is False


def test_case_differences_do_not_manufacture_a_mismatch() -> None:
    block = mp.from_submit_meta({"requested_reasoning": "pro", "selected_reasoning": "Pro"})
    assert block["provenance_status"] == mp.CONFIRMED


def test_no_request_is_not_a_failure() -> None:
    block = mp.from_submit_meta({}, handler="webkimi")
    assert block["provenance_status"] == mp.NOT_REQUESTED
    assert block["reasoning_proven"] is False


def test_a_missing_meta_does_not_raise() -> None:
    assert mp.from_submit_meta(None)["provenance_status"] == mp.NOT_REQUESTED


def test_the_summary_names_every_unproven_seat() -> None:
    blocks = [
        mp.from_submit_meta({"requested_reasoning": "Pro", "selected_reasoning": "Pro"}, handler="a"),
        mp.from_submit_meta({"requested_reasoning": "Pro"}, handler="b"),
        mp.from_submit_meta({"requested_reasoning": "Pro", "selected_reasoning": "Auto"}, handler="c"),
    ]
    summary = mp.summarize(blocks)
    assert summary["unproven_handlers"] == ["b", "c"]
    assert summary["all_reasoning_proven"] is False


def test_a_fully_confirmed_panel_says_so() -> None:
    blocks = [
        mp.from_submit_meta({"requested_reasoning": "Pro", "selected_reasoning": "Pro"}, handler=h)
        for h in ("a", "b")
    ]
    assert mp.summarize(blocks)["all_reasoning_proven"] is True


def test_an_empty_panel_is_not_proven() -> None:
    """Zero lanes must never read as 'everything confirmed'."""
    assert mp.summarize([])["all_reasoning_proven"] is False
