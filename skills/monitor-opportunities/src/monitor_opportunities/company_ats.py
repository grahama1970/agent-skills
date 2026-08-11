"""Resolve an employer's ATS board (Ashby/Greenhouse/Lever) by company name.

The robust alternative to LinkedIn click-through: find the company's own job
board directly via brave-search, so an external-apply LinkedIn job gets its REAL
application form learned (company-level, digest-bound) instead of a LinkedIn-view
stub. Also classifies apply_type so Easy Apply stops looking like a failed
capture.

No LLM. Deterministic pattern-match over brave-search results.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

BRAVE_SEARCH = Path.home() / ".claude" / "skills" / "brave-search" / "brave_search.py"

# ATS board URL patterns -> (provider, slug). Ordered by preference.
_ATS_PATTERNS: tuple[tuple[str, str], ...] = (
    ("ashby", r"jobs\.ashbyhq\.com/([A-Za-z0-9._-]+)"),
    ("greenhouse", r"(?:boards|job-boards)\.greenhouse\.io/([A-Za-z0-9._-]+)"),
    ("lever", r"jobs\.lever\.co/([A-Za-z0-9._-]+)"),
)
# Slugs that are the ATS product itself, not a company board.
_SLUG_BLOCKLIST = frozenset({"embed", "boards", "job-boards", "www", "api", "posting-api"})
# Generic company-name tokens that must NOT be the basis of a match (else
# "Primitive Labs" matches "periodic-labs" on the shared word "labs").
_GENERIC_TOKENS = frozenset({
    "labs", "lab", "inc", "incorporated", "technologies", "technology", "tech",
    "solutions", "solution", "ai", "corp", "corporation", "llc", "ltd", "group",
    "co", "company", "systems", "io", "the", "and", "services",
})


def classify_apply_type(apply_url: str) -> str:
    """direct_ats | linkedin | unknown from a URL alone (no browser)."""
    u = (apply_url or "").lower()
    if any(re.search(p, u) for _, p in _ATS_PATTERNS):
        return "direct_ats"
    if "linkedin.com" in u:
        return "linkedin"  # further split (easy_apply/external) needs the DOM
    return "unknown"


def _brave_web(query: str, count: int = 6) -> str:
    if not BRAVE_SEARCH.exists():
        return ""
    try:
        proc = subprocess.run(
            ["python3", str(BRAVE_SEARCH), "web", query, "--count", str(count), "--no-json"],
            capture_output=True, text=True, timeout=45,
        )
        return proc.stdout if proc.returncode == 0 else ""
    except (subprocess.TimeoutExpired, OSError):
        return ""


def resolve_company_ats(company: str) -> dict[str, Any] | None:
    """Find a company's ATS board slug via brave-search. None if not found.

    Returns {provider, slug, board_url, evidence_query}. The board_url is the
    company's job board; a specific posting's form URL is discovered from it.
    """
    company = (company or "").strip()
    if not company:
        return None
    text = _brave_web(f"{company} careers jobs site:ashbyhq.com OR site:greenhouse.io OR site:lever.co")
    if not text:
        text = _brave_web(f"{company} careers ashby greenhouse lever apply")
    for provider, pattern in _ATS_PATTERNS:
        for m in re.finditer(pattern, text):
            slug = m.group(1).strip("/").lower()
            if slug in _SLUG_BLOCKLIST or len(slug) < 2:
                continue
            # Sanity: the slug must share a WHOLE non-generic token with the
            # company (else "Primitive Labs" matches "periodic-labs" on "labs",
            # or "Glint" matches "glints" on a substring). Whole-segment match on
            # a distinctive token only.
            comp_tokens = {
                t for t in re.split(r"[^a-z0-9]+", company.lower())
                if len(t) > 2 and t not in _GENERIC_TOKENS
            }
            slug_segs = {s for s in re.split(r"[^a-z0-9]+", slug) if s}
            if comp_tokens and not (comp_tokens & slug_segs):
                continue
            board_url = {
                "ashby": f"https://jobs.ashbyhq.com/{slug}",
                "greenhouse": f"https://boards.greenhouse.io/{slug}",
                "lever": f"https://jobs.lever.co/{slug}",
            }[provider]
            return {"provider": provider, "slug": slug, "board_url": board_url, "company": company}
    return None
