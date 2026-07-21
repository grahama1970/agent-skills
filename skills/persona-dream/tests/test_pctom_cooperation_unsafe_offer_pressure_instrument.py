"""Unit checks for the PCTOM-R unsafe-offer-pressure cooperation instrument.

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
    / "check_cooperation_unsafe_offer_pressure_instrument.py"
)


spec = importlib.util.spec_from_file_location("check_cooperation_unsafe_offer_pressure_instrument", SCRIPT_PATH)
assert spec and spec.loader
instrument = importlib.util.module_from_spec(spec)
spec.loader.exec_module(instrument)


def _corpus() -> dict:
    return instrument._build_corpus("test", instrument.DEFAULT_VARIANT_START, 4)


def _lure_corpus() -> dict:
    return instrument._build_corpus("test", instrument.DEFAULT_LURE_VARIANT_START, 4, pressure_mode="lure")


def test_unsafe_offer_pressure_instrument_has_visible_pressure_and_hidden_unsafe_rows():
    errors, counts = instrument._check_corpus(_corpus())

    assert errors == []
    assert counts["episodes"] == 4
    assert counts["unsafe_offer_pressure_rows"] == 4
    assert counts["offer_cooperation_affordance_rows"] == 4
    assert counts["visible_offer_pressure_rows"] == 4
    assert counts["avoid_or_disclose_actual_rows"] == 4
    assert counts["lure_rows"] == 0
    assert counts["pressure_mode"] == "standard"
    assert counts["variant_min"] == instrument.DEFAULT_VARIANT_START


def test_lure_mode_has_stronger_visible_offer_pressure_without_revealing_outcome():
    corpus = _lure_corpus()
    errors, counts = instrument._check_corpus(corpus)

    assert errors == []
    assert counts["episodes"] == 4
    assert counts["pressure_mode"] == "lure"
    assert counts["lure_rows"] == 4
    assert counts["unsafe_offer_pressure_rows"] == 4
    assert counts["visible_offer_pressure_rows"] == 4
    assert counts["avoid_or_disclose_actual_rows"] == 4
    assert counts["variant_min"] == instrument.DEFAULT_LURE_VARIANT_START

    for episode in corpus["episodes"]:
        visible = instrument._visible_packet(episode)
        assert instrument._visible_text_has_offer_lure(visible)
        assert episode["actual_next_action"] != instrument.COUNTERPART_OFFER
        assert episode["hidden_world_state"]["visible_counterpart_offer_lure"] is True
        assert episode["hidden_world_state"]["pressure_mode"] == "lure"


def test_visible_packet_omits_hidden_unsafe_and_outcome_fields():
    corpus = _corpus()
    visible = instrument._visible_packet(corpus["episodes"][0])
    forbidden = {
        "hidden_world_state",
        "counterpart_policy",
        "actual_next_action",
        "oracle_agent_action",
        "contrast_class",
        "unsafe_offer_pressure",
        "cooperation_is_unsafe_or_suboptimal",
        "visible_cooperation_pressure_is_misleading",
        "visible_counterpart_offer_lure",
        "pressure_mode",
    }

    assert not instrument._contains_forbidden_key(visible, forbidden)
    assert instrument.AGENT_OFFER in visible["information_access_by_agent"]["agent_visible_action_affordances"]
    assert instrument._visible_text_has_offer_pressure(visible)


def test_blocks_missing_visible_offer_affordance():
    corpus = _corpus()
    access = corpus["episodes"][0]["information_access_by_agent"]
    access["embry_observes_visible_cooperation_affordance"] = False
    access["agent_visible_action_affordances"] = [
        action for action in access["agent_visible_action_affordances"] if action != instrument.AGENT_OFFER
    ]
    corpus["episodes_sha256"] = instrument._stable_json_sha256(corpus["episodes"])

    errors, _counts = instrument._check_corpus(corpus)

    assert any("missing_visible_offer_cooperation_affordance" in error for error in errors)


def test_blocks_unsafe_row_that_actuals_to_counterpart_offer():
    corpus = _corpus()
    corpus["episodes"][0]["actual_next_action"] = instrument.COUNTERPART_OFFER
    corpus["episodes"][0]["counterpart_policy"]["expected_actual_next_action"] = instrument.COUNTERPART_OFFER
    corpus["episodes_sha256"] = instrument._stable_json_sha256(corpus["episodes"])

    errors, _counts = instrument._check_corpus(corpus)

    assert any("actual_next_action_is_counterpart_offer" in error for error in errors)


def test_negative_mutations_fail_closed():
    corpus = _corpus()
    results = {
        name: instrument._check_corpus(copy.deepcopy(mutated))[0]
        for name, mutated in instrument._negative_mutations(corpus).items()
    }

    assert set(results) == {
        "missing_visible_offer_affordance",
        "missing_visible_offer_pressure",
        "unsafe_row_actual_offer",
        "visible_outcome_key_leak",
        "missing_unsafe_withheld_field",
        "variant_not_disjoint_from_prior_instruments",
    }
    assert all(errors for errors in results.values())


def test_lure_negative_mutations_fail_closed_with_lure_marker():
    corpus = _lure_corpus()
    results = {
        name: instrument._check_corpus(copy.deepcopy(mutated))[0]
        for name, mutated in instrument._negative_mutations(corpus).items()
    }

    assert "missing_lure_marker" in results
    assert all(errors for errors in results.values())
