"""Trigger signal: is a company in a budget+urgency moment (=> more likely to reply)?

A fresh funding round, contract win, award, or hiring surge means budget and
urgency — the strongest predictor of a reply after fit. Computes a 0..1 trigger
score per company from a bounded brave-search over recent news, with the evidence
phrase. Fail-soft: no brave-search / no signal => 0 (never fabricated).

Deliberately bounded (one search per distinct org) so the nightly stays fast.
"""

from __future__ import annotations

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
    if not BRAVE_SEARCH.exists():
        return ""
    try:
        argv = [
            "python3", str(BRAVE_SEARCH), "web", query,
            "--count", str(count), "--no-json", "--freshness", "pm",
        ]
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=40)
        return proc.stdout if proc.returncode == 0 else ""
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
