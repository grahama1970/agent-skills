"""Resolve a person's name to CANDIDATE LinkedIn profiles. Never to one answer.

A Meetup attendee gives a name, a group, and an event. That is enough to search
the public web for a profile, and nowhere near enough to assert identity: the
first live probe for "Matthew Gracie" returned five distinct people - a CISSP at
a security company, a Deloitte managing director, a tig welder, and two more.
Picking one automatically would eventually send a stranger a message that reads
as though Graham knows them.

So this returns a ranked candidate list with the query that produced it and the
terms that matched, and marks every row as requiring human confirmation. The
scoring is deliberately transparent - shared context words, nothing learned,
nothing opaque - so a human can see why a row ranks where it does.

Public search only. No LinkedIn login, no scraping, no automated access; the
prohibitions in references/linkedin-policy.md are unchanged by this module.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

BRAVE_SEARCH = Path.home() / ".claude" / "skills" / "brave-search" / "brave_search.py"
STOPWORDS = {
    "the", "and", "for", "with", "group", "meetup", "club", "community", "buffalo",
    "new", "york", "usa", "inc", "llc", "networking", "referral", "virtual",
}
CONFIDENCE_STRONG = 2
CONFIDENCE_WEAK = 1
# A group name is shorthand; a LinkedIn headline is not. "Infosec 716" never
# literally matches "Information Security", so the CISSP who hosts the meetup
# ranked level with a tig welder of the same name until these expansions existed.
TERM_EXPANSIONS = {
    "infosec": ("information", "security", "cyber"),
    "sec": ("security",),
    "ai": ("artificial", "intelligence", "machine", "learning"),
    "ml": ("machine", "learning"),
    "devops": ("devops", "platform", "infrastructure"),
    "data": ("data", "analytics"),
    "cyber": ("cyber", "security"),
    "dev": ("developer", "engineer", "software"),
    "ux": ("design", "experience"),
    "pm": ("product", "manager"),
}


def _context_terms(*sources: str) -> list[str]:
    """Distinctive words from the group/event that a real profile might echo."""

    words: list[str] = []
    for source in sources:
        for word in re.findall(r"[A-Za-z][A-Za-z0-9+#.-]{2,}", str(source or "")):
            low = word.lower()
            if low in STOPWORDS or low in words:
                continue
            words.append(low)
            for extra in TERM_EXPANSIONS.get(low, ()):  # shorthand -> headline vocabulary
                if extra not in words:
                    words.append(extra)
    return words[:16]


def search_profiles(name: str, location: str = "", *, count: int = 5, timeout: int = 60) -> tuple[list[dict[str, Any]], str]:
    """Public web search for LinkedIn profiles. Returns (results, query)."""

    query = f'site:linkedin.com/in "{name}"' + (f" {location}" if location else "")
    if not BRAVE_SEARCH.is_file():
        return [], query
    try:
        proc = subprocess.run(
            ["python3", str(BRAVE_SEARCH), "web", query, "--count", str(count)],
            capture_output=True, text=True, timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError):
        return [], query
    start = proc.stdout.find("{")
    if proc.returncode != 0 or start < 0:
        return [], query
    try:
        payload = json.loads(proc.stdout[start:])
    except ValueError:
        return [], query
    results = (payload.get("web") or {}).get("results") or payload.get("results") or []
    return [r for r in results if isinstance(r, dict)], query


def resolve_candidates(
    name: str,
    *,
    context: str = "",
    location: str = "Buffalo",
    count: int = 5,
) -> dict[str, Any]:
    """Ranked LinkedIn candidates for one person, with the reasoning shown."""

    results, query = search_profiles(name, location, count=count)
    terms = _context_terms(context)
    candidates: list[dict[str, Any]] = []
    name_tokens = [t for t in re.findall(r"[a-z]+", name.lower()) if len(t) > 2]
    for result in results:
        url = str(result.get("url") or "")
        if "linkedin.com/in" not in url:
            continue
        blurb = " ".join([str(result.get("title") or ""), str(result.get("description") or "")]).lower()
        # Identity floor: the profile must actually carry the person's name.
        # Without this, context-term scoring promoted a DIFFERENT person -
        # 'Jonathan Greechan' was assigned arlette-verploegh's profile as a
        # strong candidate on 2026-08-20 because their event blurbs shared
        # 'founder' and 'startup'. Context similarity ranks; it must never
        # substitute for the name.
        # ...and it must carry it in the TITLE or URL SLUG. A description
        # mentioning the searched name is how other people's profiles leak in:
        # ploshansky and fatihmcicek both mention 'Jonathan Greechan' in their
        # page text and sailed through a blurb-wide check.
        identity_haystack = (str(result.get("title") or "").lower() + " " + url.lower())
        name_hits = sum(1 for t in name_tokens if t in identity_haystack)
        if name_tokens and name_hits < min(2, len(name_tokens)):
            continue
        matched = sorted({term for term in terms if term in blurb})
        candidates.append(
            {
                "profile_url": url.split("?")[0],
                "headline": str(result.get("title") or "")[:200],
                "matched_context_terms": matched,
                "match_score": len(matched),
                "confidence": (
                    "strong" if len(matched) >= CONFIDENCE_STRONG
                    else "weak" if len(matched) == CONFIDENCE_WEAK
                    else "name_only"
                ),
            }
        )
    candidates.sort(key=lambda row: -row["match_score"])
    ambiguous = len(candidates) > 1 and (
        len(candidates) < 2 or candidates[0]["match_score"] == candidates[1]["match_score"]
    )
    return {
        "schema": "ops_linkedin.lead_candidates.v1",
        "subject": name,
        "query": query,
        "context_terms": terms,
        "candidates": candidates,
        "candidate_count": len(candidates),
        "ambiguous": ambiguous,
        "human_confirmation_required": True,
        "non_claims": [
            "A search hit is a hypothesis. No row here identifies the person until the human confirms it.",
            "Same-name profiles are common; the first live probe for one attendee returned five distinct people.",
            "Public web search only: no LinkedIn login, no scraping, no automated platform access.",
        ],
        "external_effects": False,
    }
