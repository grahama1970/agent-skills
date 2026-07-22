"""Unit checks for sealed-test planning-gap diagnostics."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "research" / "prospective-tom" / "scripts" / "analyze_sealed_test_planning_gap.py"

spec = importlib.util.spec_from_file_location("analyze_sealed_test_planning_gap", SCRIPT_PATH)
assert spec and spec.loader
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


def test_margin_gated_policy_asks_on_low_margin():
    distribution = [
        {"value": "KAI_ASKS_TO_WAIT", "probability": 0.2},
        {"value": "KAI_OFFERS_COOPERATION", "probability": 0.3},
        {"value": "KAI_DISCLOSES_AUTHORITY_CONSTRAINT", "probability": 0.5},
    ]

    selected, rule = diag._select_margin_gated(distribution, 0.2)

    assert selected == "ASK_CLARIFYING_QUESTION"
    assert rule["rule"] == "LOW_MARGIN_EPISTEMIC_ACTION"
    assert round(rule["mapped_action_margin"], 6) == 0.2


def test_margin_gated_policy_uses_clear_top_action():
    distribution = [
        {"value": "KAI_ASKS_TO_WAIT", "probability": 0.2},
        {"value": "KAI_OFFERS_COOPERATION", "probability": 0.55},
        {"value": "KAI_DISCLOSES_AUTHORITY_CONSTRAINT", "probability": 0.25},
    ]

    selected, rule = diag._select_margin_gated(distribution, 0.2)

    assert selected == "OFFER_COOPERATION"
    assert rule["rule"] == "CLEAR_TOP_MAPPED_ACTION"


def test_coordination_symmetry_detects_balanced_oracles():
    rows = []
    for idx, oracle in enumerate(
        ["OFFER_COOPERATION"] * 5 + ["DISCLOSE_INFORMATION"] * 5 + ["WAIT"] * 6,
        start=1,
    ):
        rows.append(
            {
                "episode_id": f"episode-{idx}",
                "baseline_action": "OFFER_COOPERATION",
                "cd_action": "DISCLOSE_INFORMATION",
                "oracle_action": oracle,
                "cd_minus_baseline": 0.0,
                "direction": "TIE",
            }
        )

    result = diag._coordination_symmetry(rows)

    assert result["divergent_d_offer_cd_disclose_rows"] == 16
    assert result["oracle_action_counts"] == {
        "DISCLOSE_INFORMATION": 5,
        "OFFER_COOPERATION": 5,
        "WAIT": 6,
    }
    assert result["diagnosis"] == "balanced_oracle_actions_cancel_cd_planning_advantage"
