"""Rank opportunities by RESPONSE PROBABILITY, not volume.

The agent's job is a short daily list of opportunities LIKELY TO GET A RESPONSE,
not a resume firehose. An opportunity's score rewards the drivers that actually
produce replies (brave-search evidence 2026-08-11): genuine JD fit, a WARM PATH
(a network connection / referral), a fresh TRIGGER (funding/award/contract/hiring
surge = budget + urgency), and LOW COMPETITION (niche board / inbound channel /
expert network beats cold ATS). Volume is the opposite of the goal.

score = fit * (BASE + w_warm*warm_path + w_trigger*trigger + w_lowcomp*low_competition)

Each score carries the human-readable REASONS it will respond, so the daily digest
explains itself. No network here — signals are computed upstream and passed in.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CHANNELS = Path(__file__).resolve().parents[2] / "config" / "response_channels.json"

# Weights: warm path and trigger dominate; low competition matters; fit gates all.
BASE = 0.15
W_WARM = 0.45
W_TRIGGER = 0.30
W_LOWCOMP = 0.20


def _channel_competition(source: str, channels: dict[str, Any]) -> float:
    """Competition (0=inbound/none .. 1=cold ATS firehose) for a source; default mid."""
    src = (source or "").lower()
    for ch in channels.get("channels", []):
        for t in ch.get("targets", []):
            if t in src:
                return float(ch["competition"])
        skill = ch.get("skill") or ""
        if ch["id"].split("-")[-1] in src or (skill and skill in src):
            return float(ch["competition"])
    return 0.6


def _load_channels() -> dict[str, Any]:
    try:
        return json.loads(CHANNELS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"channels": []}


def score_opportunity(opp: dict[str, Any], channels: dict[str, Any] | None = None) -> dict[str, Any]:
    """Response-likelihood score + the reasons it will respond.

    opp signals (all 0..1, computed upstream; missing = 0):
      fit           mandate fit from the JD (evaluator)
      warm_path     strength of a network connection / referral path into the company
      trigger       freshness/relevance of a funding/award/contract/hiring signal
      source        discovery source (sets competition unless competition given)
      competition   optional explicit competition override
    """
    channels = channels if channels is not None else _load_channels()
    fit = float(opp.get("fit") or 0.0)
    warm = float(opp.get("warm_path") or 0.0)
    trigger = float(opp.get("trigger") or 0.0)
    competition = opp.get("competition")
    if competition is None:
        competition = _channel_competition(str(opp.get("source") or ""), channels)
    low_comp = 1.0 - float(competition)

    raw = BASE + W_WARM * warm + W_TRIGGER * trigger + W_LOWCOMP * low_comp
    score = round(fit * raw, 4)

    has_driver = warm >= 0.5 or trigger >= 0.5 or low_comp >= 0.6
    reasons: list[str] = []
    if warm >= 0.5:
        reasons.append("warm path: a network connection can refer you in (referral >> cold form)")
    if trigger >= 0.5:
        reasons.append("fresh trigger: recent funding/award/contract/hiring surge = budget + urgency")
    if low_comp >= 0.6:
        reasons.append("low-competition channel (niche board / inbound / expert network), not the applicant pile")
    if fit >= 0.6:
        reasons.append("strong JD mandate-fit for your lane")
    if not has_driver:
        # Fit alone does not earn a reply — flag the cold path honestly.
        reasons.append("cold application, low reply odds (fit alone doesn't get a response)")
    return {
        "opportunity_id": opp.get("candidate_id") or opp.get("id"),
        "organization": opp.get("organization"),
        "title": opp.get("title"),
        "response_score": score,
        "drivers": {"fit": fit, "warm_path": warm, "trigger": trigger, "low_competition": round(low_comp, 2)},
        "why_it_responds": reasons,
    }


def rank_by_response(opps: list[dict[str, Any]], top_n: int = 8) -> list[dict[str, Any]]:
    """Return the daily top-N by response probability (highest first)."""
    channels = _load_channels()
    scored = [score_opportunity(o, channels) for o in opps]
    scored.sort(key=lambda s: -s["response_score"])
    return scored[:top_n]
