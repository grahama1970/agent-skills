"""Response-likelihood ranking: warm/trigger/low-competition beats cold high-fit."""
from __future__ import annotations
from monitor_opportunities.response_likelihood import score_opportunity, rank_by_response


def test_warm_beats_cold_at_equal_fit() -> None:
    cold = {"organization": "A", "title": "Staff AI Eng", "fit": 0.9, "source": "jobs.ashbyhq.com/a"}
    warm = {"organization": "B", "title": "Staff AI Eng", "fit": 0.9, "warm_path": 0.9, "source": "discover-contacts"}
    assert score_opportunity(warm)["response_score"] > score_opportunity(cold)["response_score"]


def test_trigger_and_lowcomp_lift_score() -> None:
    s = score_opportunity({"organization": "C", "fit": 0.8, "trigger": 0.9, "source": "skima.ai"})
    assert s["drivers"]["trigger"] == 0.9 and s["drivers"]["low_competition"] > 0.5
    assert any("trigger" in r for r in s["why_it_responds"])


def test_cold_application_flagged_low_odds() -> None:
    s = score_opportunity({"organization": "D", "fit": 0.7, "source": "ashbyhq.com"})
    assert any("cold application" in r for r in s["why_it_responds"])  # honest: low reply odds


def test_rank_orders_by_response() -> None:
    opps = [
        {"organization": "cold", "fit": 0.95, "source": "indeed.com"},
        {"organization": "warm-trigger", "fit": 0.7, "warm_path": 0.8, "trigger": 0.7, "source": "discover-contacts"},
    ]
    ranked = rank_by_response(opps)
    assert ranked[0]["organization"] == "warm-trigger"  # response probability, not fit or volume
