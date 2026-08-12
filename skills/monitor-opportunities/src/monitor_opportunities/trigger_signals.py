"""Trigger signal: is a company in a budget+urgency moment (=> more likely to reply)?

A fresh funding round, contract win, award, or hiring surge means budget and
urgency — the strongest predictor of a reply after fit. Computes a 0..1 trigger
score per company from a bounded brave-search over recent news, with the evidence
phrase. Fail-soft: no brave-search / no signal => 0 (never fabricated).

Deliberately bounded (one search per distinct org) so the nightly stays fast.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

BRAVE_SEARCH = Path.home() / ".claude" / "skills" / "brave-search" / "brave_search.py"

# Budget+urgency signals. Weighted: funding/contract/award > hiring/launch.
_STRONG = re.compile(
    r"raises?\s+\$|raised\s+\$|series\s+[a-e]\b|seed round|closes?\s+\$|"
    r"awarded|wins?\s+(?:a\s+)?contract|won\s+(?:a\s+)?contract|sbir|sttr|"
    r"government contract|federal contract|new funding|secures?\s+\$",
    re.I,
)
_MEDIUM = re.compile(
    r"hiring|expands|expanding|launches?|new (?:team|office|product)|"
    r"partnership|grant|selected for|backed by",
    re.I,
)


def _brave(query: str, count: int = 5) -> str:
    """Brave web search; free key first, paid key fallback on quota exhaustion.

    The free plan is 2000 req/month and hard-429s past it (observed 2026-08-12).
    Falling back to BRAVE_API_KEY_PAID for the bounded nightly volume was
    explicitly authorized by Graham on 2026-08-12.
    """
    if not BRAVE_SEARCH.exists():
        return ""
    argv = [
        "python3", str(BRAVE_SEARCH), "web", query,
        "--count", str(count), "--no-json", "--freshness", "pm",
    ]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=40)
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout
        paid = os.environ.get("BRAVE_API_KEY_PAID")
        quota_failed = (
            "429" in proc.stderr or "QUOTA" in proc.stderr.upper()
            or "not found in env" in proc.stderr
        )
        if paid and quota_failed:
            env = dict(os.environ, BRAVE_API_KEY=paid)
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=40, env=env)
            if proc.returncode == 0:
                return proc.stdout
        return ""
    except (subprocess.TimeoutExpired, OSError):
        return ""


def company_trigger(org: str) -> dict[str, object]:
    """0..1 trigger score for a company + the evidence phrase. 0 if none/unavailable."""
    org = (org or "").strip()
    if not org:
        return {"trigger": 0.0, "evidence": None}
    text = _brave(f"{org} funding OR award OR contract OR hiring 2026")
    if not text:
        return {"trigger": 0.0, "evidence": None}
    strong = _STRONG.search(text)
    if strong:
        return {"trigger": 0.9, "evidence": strong.group(0)}
    medium = _MEDIUM.search(text)
    if medium:
        return {"trigger": 0.5, "evidence": medium.group(0)}
    return {"trigger": 0.0, "evidence": None}


def triggers_for_orgs(orgs: list[str], limit: int = 12) -> dict[str, dict[str, object]]:
    """Compute triggers for up to `limit` distinct orgs (bounded for nightly speed)."""
    out: dict[str, dict[str, object]] = {}
    for org in list(dict.fromkeys(o for o in orgs if o))[:limit]:
        out[org] = company_trigger(org)
    return out


def triggers_for_shortlist(
    rows: list[dict[str, object]],
    min_fit: float = 0.6,
    limit: int = 12,
) -> tuple[dict[str, dict[str, object]], dict[str, object]]:
    """Fit-gated, receipted trigger pass over a shortlist.

    Spends the bounded brave-search budget only on orgs whose best role clears
    `min_fit` (a trigger on a role we would not pursue is wasted). Returns the
    org->signal lookup plus a receipt recording, per org, whether it was searched,
    its score, evidence, and — when skipped — why. This makes the trigger signal
    inspectable instead of an invisible 0 (last run: trigger fired but no artifact
    proved what it found).

    Note: we intentionally do NOT skip by org type. The trigger regex matches
    contracts/awards/grants, which hospitals, universities, and gov contractors
    (e.g. Roswell Park, CUBRC) legitimately win — dropping them would lose real
    budget+urgency signal. Fit is the honest gate.
    """
    best_fit: dict[str, float] = {}
    for r in rows:
        org = str(r.get("organization") or "").strip()
        if not org:
            continue
        try:
            fit = float(r.get("fit_score") or r.get("fit") or 0.0)
        except (TypeError, ValueError):
            fit = 0.0
        best_fit[org] = max(best_fit.get(org, 0.0), fit)

    lookup: dict[str, dict[str, object]] = {}
    records: list[dict[str, object]] = []
    # Highest-fit orgs first so the budget lands on the best candidates.
    ranked = sorted(best_fit.items(), key=lambda kv: -kv[1])
    searched = 0
    for org, fit in ranked:
        if fit < min_fit:
            records.append({"org": org, "searched": False, "skip_reason": "below_min_fit",
                            "fit": round(fit, 3), "trigger": 0.0, "evidence": None})
            continue
        if searched >= limit:
            records.append({"org": org, "searched": False, "skip_reason": "over_budget",
                            "fit": round(fit, 3), "trigger": 0.0, "evidence": None})
            continue
        sig = company_trigger(org)
        searched += 1
        lookup[org] = sig
        records.append({"org": org, "searched": True, "fit": round(fit, 3),
                        "trigger": sig.get("trigger"), "evidence": sig.get("evidence")})

    receipt = {
        "schema": "monitor_opportunities.trigger_receipt.v1",
        "min_fit": min_fit,
        "limit": limit,
        "orgs_considered": len(best_fit),
        "orgs_searched": searched,
        "orgs_with_signal": sum(
            1 for r in records if r.get("searched") and (r.get("trigger") or 0.0) > 0.0
        ),
        "brave_search_available": BRAVE_SEARCH.exists(),
        "records": records,
    }
    return lookup, receipt
