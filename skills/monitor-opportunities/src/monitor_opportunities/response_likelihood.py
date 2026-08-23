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

# Weights: warm path and trigger dominate; low competition + local standout matter;
# fit gates ALL (score = fit * drivers), so a generic local role with weak fit stays
# low — local boosts noticeability only AFTER mandate fit is real (mandate-first).
BASE = 0.15
W_WARM = 0.45
W_TRIGGER = 0.30
W_LOWCOMP = 0.20
W_LOCAL = 0.25
# A LinkedIn "top applicant" is a strong reply signal (LinkedIn tells the poster
# you rank in the top pool); Easy Apply is a low-friction lane worth a small nudge.
W_TOPCAND = 0.35
W_EASYAPPLY = 0.10
_WNY_WORKPLACES = frozenset({"WNY_HYBRID", "WNY_ONSITE"})
# Graded geo: Buffalo hybrid is the hard-constraint ideal; WNY onsite next;
# credible remote is acceptable (partial credit, never zero); onsite-elsewhere
# is rejected before ranking so it never reaches here.
_GEO_WEIGHT = {"WNY_HYBRID": 1.0, "WNY_ONSITE": 0.85, "REMOTE": 0.3}


def _local_weight(opp: dict[str, Any]) -> float:
    if opp.get("local_standout"):
        return 1.0
    return _GEO_WEIGHT.get(str(opp.get("workplace_type") or ""), 0.0)


def _is_top_candidate(opp: dict[str, Any]) -> bool:
    return bool(opp.get("top_candidate") or opp.get("top_candidate_evidence"))


def _channel_competition(source: str, channels: dict[str, Any]) -> float:
    """Competition (0=inbound/none .. 1=cold ATS firehose) for a source; default mid."""
    src = (source or "").lower()
    for ch in channels.get("channels", []):
        for t in ch.get("targets") or []:
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


def _source_of(opp: dict[str, Any]) -> str:
    """The discovery-source string for competition lookup.

    Shortlist rows do not carry a bare `source` key; they carry source_provider /
    source_class / source_identity. Falling through to those keeps low_competition
    a live signal instead of collapsing every row to the default 0.6.
    """
    for key in ("source", "source_provider", "source_class", "source_identity"):
        val = opp.get(key)
        if val:
            return str(val)
    return ""


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
        competition = _channel_competition(_source_of(opp), channels)
    low_comp = 1.0 - float(competition)
    # Local standout: a DARPA/AI-caliber architect is rare in WNY, so Buffalo
    # on-site/hybrid roles get noticed. Fit still gates it (mandate-first).
    local = _local_weight(opp)
    top_cand = 1.0 if _is_top_candidate(opp) else 0.0
    easy_apply = 1.0 if opp.get("easy_apply") else 0.0

    raw = (
        BASE
        + W_WARM * warm
        + W_TRIGGER * trigger
        + W_LOWCOMP * low_comp
        + W_LOCAL * local
        + W_TOPCAND * top_cand
        + W_EASYAPPLY * easy_apply
    )
    score = round(fit * raw, 4)

    has_driver = warm >= 0.5 or trigger >= 0.5 or low_comp >= 0.6 or local >= 0.85 or top_cand >= 1.0
    reasons: list[str] = []
    if top_cand >= 1.0:
        reasons.append("LinkedIn top applicant: you rank in the top pool for this role — recruiters see that, so your reply odds are high")
    if local >= 1.0:
        reasons.append("Buffalo/WNY hybrid: a DARPA/AI-caliber architect is rare here — you get noticed, and you can meet in person")
    elif local >= 0.85:
        reasons.append("Buffalo/WNY onsite: local presence is a standout advantage here")
    if easy_apply >= 1.0:
        reasons.append("Easy Apply: low-friction one-click application — you can apply in seconds")
    if warm >= 0.5:
        reasons.append("warm path: a network connection can refer you in (referral >> cold form)")
    if trigger >= 0.5:
        reasons.append("fresh trigger: recent funding/award/contract/hiring surge = budget + urgency")
    if low_comp >= 0.6:
        reasons.append("low-competition channel (niche board / inbound / expert network), not the applicant pile")
    if fit >= 0.6:
        reasons.append("strong JD mandate-fit for your lane")
    if fit < 0.6 and local >= 0.85:
        reasons.append("BUT weak mandate fit — local alone is not a reason to apply (mandate-first)")
    if not has_driver:
        # Fit alone does not earn a reply — flag the cold path honestly.
        reasons.append("cold application, low reply odds (fit alone doesn't get a response)")
    return {
        "opportunity_id": opp.get("candidate_id") or opp.get("id"),
        "organization": opp.get("organization"),
        "title": opp.get("title"),
        "response_score": score,
        "drivers": {"fit": fit, "warm_path": warm, "trigger": trigger, "low_competition": round(low_comp, 2),
                    "local": local, "top_candidate": top_cand, "easy_apply": easy_apply},
        "why_it_responds": reasons,
    }


def rank_by_response(opps: list[dict[str, Any]], top_n: int = 8) -> list[dict[str, Any]]:
    """Return the daily top-N by response probability (highest first)."""
    channels = _load_channels()
    scored = [score_opportunity(o, channels) for o in opps]
    scored.sort(key=lambda s: -s["response_score"])
    return scored[:top_n]
