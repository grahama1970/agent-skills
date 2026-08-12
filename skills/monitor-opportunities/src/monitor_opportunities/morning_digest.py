"""Build the morning digest: the top opportunities LIKELY TO RESPOND, classified.

Composes the pieces built for the response-first pivot into one ranked digest the
nightly emits:
- classify (employment vs consulting) + the correct action per track,
- response_likelihood score (fit x low-competition x local; warm-path/trigger are
  0 until those signals are wired — noted honestly, not faked),
- decision-maker attachment from config/decision_makers.json where known.

Input: the run's shortlist rows. Output: a ranked digest list (top-N) each with
opportunity_type, action, response tier + reasons, and a named InMail target when
available. No network; the caller persists it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .classify import classify_opportunity
from .response_likelihood import score_opportunity

DECISION_MAKERS = Path(__file__).resolve().parents[2] / "config" / "decision_makers.json"


def _load_dms() -> dict[str, Any]:
    try:
        return json.loads(DECISION_MAKERS.read_text(encoding="utf-8")).get("by_org", {})
    except (OSError, ValueError):
        return {}


def _decision_maker_for(org: str, dms: dict[str, Any]) -> dict[str, Any] | None:
    low = (org or "").lower()
    for key, dm in dms.items():
        if key in low:
            return dm
    return None


def _tier(score: float) -> str:
    if score >= 0.45:
        return "HIGH"
    if score >= 0.25:
        return "MEDIUM"
    return "LOW"


def _fit_of(opp: dict[str, Any]) -> float:
    # Use the ranking fit_score as the fit signal (0..1); fall back to 0.
    try:
        return float(opp.get("fit_score") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def build_digest(shortlist: list[dict[str, Any]], top_n: int = 8) -> dict[str, Any]:
    """Rank the shortlist by response probability and attach type/action/decision-maker."""
    dms = _load_dms()
    entries: list[dict[str, Any]] = []
    for opp in shortlist:
        signals = dict(opp)
        signals["fit"] = _fit_of(opp)  # warm_path / trigger stay 0 until wired
        scored = score_opportunity(signals)
        classified = classify_opportunity(opp)
        dm = _decision_maker_for(str(opp.get("organization") or ""), dms)
        entries.append({
            "organization": opp.get("organization"),
            "title": opp.get("title"),
            "candidate_id": opp.get("candidate_id"),
            "opportunity_type": classified["opportunity_type"],
            "action": classified["action_plan"],
            "response_score": scored["response_score"],
            "response_tier": _tier(scored["response_score"]),
            "why_it_responds": scored["why_it_responds"],
            "inmail_target": dm,
        })
    entries.sort(key=lambda e: -e["response_score"])
    top = entries[:top_n]
    return {
        "schema": "monitor_opportunities.morning_digest.v1",
        "counts": {
            "total": len(entries),
            "employment": sum(1 for e in entries if e["opportunity_type"] == "employment"),
            "consulting": sum(1 for e in entries if e["opportunity_type"] == "consulting"),
        },
        "signals_wired": {"fit": True, "low_competition": True, "local": True, "warm_path": False, "trigger": False},
        "top": top,
    }
