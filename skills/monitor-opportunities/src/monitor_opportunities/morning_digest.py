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


def _candidate_id(opp: dict[str, Any]) -> str:
    candidate_id = (
        opp.get("candidate_id")
        or opp.get("opportunity_id")
        or opp.get("id")
    )
    if candidate_id:
        return str(candidate_id)
    org = str(opp.get("organization") or "unknown-org").strip().lower()
    title = str(opp.get("title") or "unknown-title").strip().lower()
    return f"{org}:{title}"


def _balanced_top(
    entries: list[dict[str, Any]], top_n: int, max_per_org: int
) -> list[dict[str, Any]]:
    """Fill the digest with roughly equal employment and consulting.

    Graham (2026-08-13): "we need roughly equal number of employment and
    consulting opportunities". Pure score ordering does not deliver that —
    employment postings vastly outnumber consulting signals in discovery, so a
    global top-N returned 8 employment and 0 consulting even with 14 consulting
    rows shortlisted. Each track therefore gets its own half of the slots,
    filled by that track's own best.

    Under-supply is honest, not padded: if a track cannot fill its half, the
    remaining slots go to the other track rather than admitting weak rows.
    Entries must be pre-sorted best-first; the per-org cap still applies.
    """
    tracks: dict[str, list[dict[str, Any]]] = {"employment": [], "consulting": []}
    for e in entries:
        tracks.setdefault(str(e.get("opportunity_type") or "employment"), []).append(e)

    quota = top_n // 2
    picked: list[dict[str, Any]] = []
    seen_org: dict[str, int] = {}

    def _take(pool: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for e in pool:
            if len(out) >= limit:
                break
            org = str(e.get("organization") or "").lower()
            if seen_org.get(org, 0) >= max_per_org:
                continue
            seen_org[org] = seen_org.get(org, 0) + 1
            out.append(e)
        return out

    consulting = _take(tracks.get("consulting", []), quota)
    employment = _take(tracks.get("employment", []), top_n - len(consulting))
    # A short track releases its slots to the other rather than padding.
    if len(consulting) + len(employment) < top_n:
        already = {id(e) for e in consulting + employment}
        remainder = [e for e in tracks.get("consulting", []) if id(e) not in already]
        consulting += _take(remainder, top_n - len(consulting) - len(employment))
    picked = consulting + employment
    picked.sort(key=lambda e: -float(e.get("response_score") or 0))
    return picked[:top_n]


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


def _exclusion_reason(
    entry: dict[str, Any],
    included: list[dict[str, Any]],
    max_per_org: int,
) -> str:
    org = str(entry.get("organization") or "").lower()
    same_org_included = sum(
        1 for item in included
        if str(item.get("organization") or "").lower() == org
    )
    if same_org_included >= max_per_org:
        return "org_diversity_cap"
    if entry.get("opportunity_type") == "employment":
        return "employment_below_balanced_digest_cutoff"
    if entry.get("opportunity_type") == "consulting":
        return "consulting_below_balanced_digest_cutoff"
    return "below_digest_cutoff"


def _selection_accounting(
    entries: list[dict[str, Any]],
    top: list[dict[str, Any]],
    max_per_org: int,
) -> dict[str, Any]:
    included_ids = {id(entry) for entry in top}
    by_type: dict[str, dict[str, int]] = {}
    candidates: list[dict[str, Any]] = []
    included_count = 0
    excluded_count = 0

    for entry in entries:
        opportunity_type = str(entry.get("opportunity_type") or "unknown")
        bucket = by_type.setdefault(
            opportunity_type,
            {"input": 0, "included": 0, "excluded": 0},
        )
        bucket["input"] += 1
        included = id(entry) in included_ids
        if included:
            disposition = "included"
            reason_code = "selected_for_digest_top"
            bucket["included"] += 1
            included_count += 1
        else:
            disposition = "excluded"
            reason_code = _exclusion_reason(entry, top, max_per_org)
            bucket["excluded"] += 1
            excluded_count += 1
        candidates.append({
            "candidate_id": _candidate_id(entry),
            "organization": entry.get("organization"),
            "title": entry.get("title"),
            "opportunity_type": opportunity_type,
            "disposition": disposition,
            "reason_code": reason_code,
            "response_score": entry.get("response_score"),
        })

    return {
        "schema": "monitor_opportunities.morning_digest.selection_accounting.v1",
        "input": len(entries),
        "included": included_count,
        "excluded": excluded_count,
        "unaccounted": len(entries) - included_count - excluded_count,
        "by_type": by_type,
        "candidates": candidates,
    }


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
            "candidate_id": _candidate_id(opp),
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
    top = _balanced_top(entries, top_n, max_per_org)
    accounting = _selection_accounting(entries, top, max_per_org)
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
        "selection_accounting": accounting,
        "top": top,
    }
