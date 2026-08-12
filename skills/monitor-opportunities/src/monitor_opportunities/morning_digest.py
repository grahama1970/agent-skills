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


def _org_signal(org: str, lookup: dict[str, Any], key: str) -> float:
    """Case-insensitive org-substring lookup of a 0..1 signal (trigger/warm_path)."""
    low = (org or "").lower()
    for k, v in (lookup or {}).items():
        if k.lower() in low or low in k.lower():
            val = v.get(key) if isinstance(v, dict) else v
            try:
                return float(val or 0.0)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _cap_per_org(
    entries: list[dict[str, Any]], top_n: int, max_per_org: int
) -> list[dict[str, Any]]:
    """Take the top-N, but at most `max_per_org` roles from any single org.

    Prevents one company with many open roles from flooding the digest (last run:
    4 of 8 were the same org). Entries must be pre-sorted best-first.
    """
    seen: dict[str, int] = {}
    top: list[dict[str, Any]] = []
    for e in entries:
        org = str(e.get("organization") or "").lower()
        if seen.get(org, 0) >= max_per_org:
            continue
        seen[org] = seen.get(org, 0) + 1
        top.append(e)
        if len(top) >= top_n:
            break
    return top


def build_digest(
    shortlist: list[dict[str, Any]],
    top_n: int = 8,
    triggers: dict[str, Any] | None = None,
    warm_paths: dict[str, Any] | None = None,
    max_per_org: int = 2,
) -> dict[str, Any]:
    """Rank the shortlist by response probability and attach type/action/decision-maker.

    triggers/warm_paths: optional {org: {trigger|warm_path: 0..1, evidence}} lookups
    computed upstream (the nightly passes live trigger signals + the warm-paths
    config). Default empty => those signals are 0 (honest, not faked).
    max_per_org: cap on how many roles from one org may appear in the top (diversity).
    """
    dms = _load_dms()
    entries: list[dict[str, Any]] = []
    for opp in shortlist:
        org = str(opp.get("organization") or "")
        signals = dict(opp)
        signals["fit"] = _fit_of(opp)
        signals["trigger"] = (
            _org_signal(org, triggers or {}, "trigger") or float(opp.get("trigger") or 0.0)
        )
        signals["warm_path"] = (
            _org_signal(org, warm_paths or {}, "warm_path") or float(opp.get("warm_path") or 0.0)
        )
        scored = score_opportunity(signals)
        classified = classify_opportunity(opp)
        dm = _decision_maker_for(str(opp.get("organization") or ""), dms)
        trig_ev = (triggers or {}).get(org) if isinstance((triggers or {}).get(org), dict) else None
        entries.append({
            "organization": opp.get("organization"),
            "title": opp.get("title"),
            "candidate_id": opp.get("candidate_id"),
            "opportunity_type": classified["opportunity_type"],
            "action": classified["action_plan"],
            "response_score": scored["response_score"],
            "response_tier": _tier(scored["response_score"]),
            "why_it_responds": scored["why_it_responds"],
            "drivers": scored["drivers"],
            "trigger_evidence": (trig_ev or {}).get("evidence"),
            "inmail_target": dm,
        })
    entries.sort(key=lambda e: -e["response_score"])
    top = _cap_per_org(entries, top_n, max_per_org)
    return {
        "schema": "monitor_opportunities.morning_digest.v1",
        "counts": {
            "total": len(entries),
            "employment": sum(1 for e in entries if e["opportunity_type"] == "employment"),
            "consulting": sum(1 for e in entries if e["opportunity_type"] == "consulting"),
        },
        "signals_wired": {
            "fit": True, "low_competition": True, "local": True,
            "trigger": bool(triggers),
            # wired via the org-level config OR row-level premium capture signals
            "warm_path": bool(warm_paths) or any(
                float(o.get("warm_path") or 0.0) > 0 for o in shortlist
            ),
        },
        "top": top,
    }
