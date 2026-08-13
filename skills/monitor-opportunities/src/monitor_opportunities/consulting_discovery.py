"""Find CONSULTING opportunities, which are researched — never scraped.

Graham (2026-08-13): "doesn't consulting opps require deep /brave-search and
looking at samgov and darpa and industry news" — yes, and that was the gap. A
job posting announces itself on a board; a consulting engagement does not.
Nobody posts "we need an agentic-compliance architect". What exists instead is
evidence of a BUYER IN MOTION:

  federal      an open solicitation in his lane (SAM.gov, DARPA, SBIR/STTR)
  contract-win an org that just won work and now needs to staff/subcontract it
  funding      an org that just raised and is buying capability
  initiative   an org publicly standing up an AI/compliance/extraction program
  rfp          an explicit RFP/RFI/sources-sought in his mandate areas

Before this module the consulting track was 12 SAM notices plus two placeholder
rows, and the brave-search "client research" pass ran three queries and DISCARDED
the results (it returned a receipt with no candidates). This turns that research
into actual lane-C candidates.

Queries are DERIVED from config/candidate_profile.json mandates crossed with
buyer-intent phrasing — not a hand-maintained list of companies
(best-practices-opportunities: no bespoke top-N lists).

Fail-soft: no brave-search, no results, or an unparseable response yields zero
candidates and an honest receipt. Nothing here is fabricated.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

BRAVE_SEARCH = Path.home() / ".claude" / "skills" / "brave-search" / "brave_search.py"
PROFILE = Path(__file__).resolve().parents[2] / "config" / "candidate_profile.json"

# Buyer-intent phrasing crossed with the candidate's mandates. Each entry is
# (signal_kind, query_suffix); the mandate supplies the subject.
_BUYER_INTENT: tuple[tuple[str, str], ...] = (
    ("rfp", "RFP OR RFI OR \"sources sought\" 2026"),
    ("contract_win", "awarded contract 2026 implementation partner"),
    ("funding", "raises Series funding 2026 hiring AI team"),
    ("initiative", "launches AI program OR modernization initiative 2026"),
)

# A result is only a lead if the page shows buyer intent, not just the topic.
_INTENT_EVIDENCE = re.compile(
    r"request for (?:proposal|information|solutions)|sources sought|"
    r"seeking (?:a )?(?:vendor|partner|contractor|supplier)|"
    r"awarded|wins?\s+(?:a\s+)?contract|selected (?:to|as)|"
    r"raises?\s+\$|series\s+[a-e]\b|"
    r"launch(?:es|ing)?\s+(?:a\s+)?(?:new\s+)?(?:program|initiative|practice|center)|"
    r"modernization|digital transformation",
    re.I,
)

# Pages that look like leads but are not buyers: aggregators, our own sources,
# and job boards (a job posting is the EMPLOYMENT track, not consulting).
_NOT_A_BUYER = re.compile(
    r"linkedin\.com/jobs|indeed\.com|glassdoor|ziprecruiter|builtin\.com/job|"
    r"wikipedia\.org|reddit\.com|/careers?/|greenhouse\.io|lever\.co|ashbyhq|"
    # RFP directories and procurement portals list OTHER people's solicitations;
    # they are indexes, not buyers (observed: rfpmart, tn.gov, federalregister).
    r"rfpmart|rfpdb|bidnet|govwin|findrfp|instantmarkets|bidprime|"
    r"federalregister\.gov|/procurement/|/bids?/|/solicitations?/",
    re.I,
)


def _mandates() -> list[str]:
    try:
        raw = json.loads(PROFILE.read_text(encoding="utf-8")).get("mandates", [])
    except (OSError, ValueError):
        return []
    out: list[str] = []
    for m in raw:
        # "agentic-compliance (flagship: sparta)" -> "agentic compliance"
        head = re.sub(r"\(.*?\)", "", str(m)).strip().rstrip(",")
        head = head.replace("-", " ").replace("/", " ")
        if head:
            out.append(" ".join(head.split()))
    return out


def build_queries(limit: int = 12) -> list[dict[str, str]]:
    """Derive buyer-intent queries from the profile's mandates."""
    queries: list[dict[str, str]] = []
    for mandate in _mandates():
        for kind, suffix in _BUYER_INTENT:
            queries.append({"kind": kind, "query": f"{mandate} {suffix}"})
            if len(queries) >= limit:
                return queries
    return queries


def _brave_json(query: str, count: int = 5, timeout: int = 45) -> list[dict[str, Any]]:
    """Brave web search returning parsed results; paid-key fallback on quota."""
    if not BRAVE_SEARCH.exists():
        return []
    argv = ["python3", str(BRAVE_SEARCH), "web", query, "--count", str(count),
            "--freshness", "pm"]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0 or not proc.stdout.strip():
            paid = os.environ.get("BRAVE_API_KEY_PAID")
            quota = (
                "429" in proc.stderr or "QUOTA" in proc.stderr.upper()
                or "not found in env" in proc.stderr
            )
            if not (paid and quota):
                return []
            proc = subprocess.run(
                argv, capture_output=True, text=True, timeout=timeout,
                env=dict(os.environ, BRAVE_API_KEY=paid),
            )
            if proc.returncode != 0:
                return []
        data = json.loads(proc.stdout)
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return []
    return [r for r in data.get("results", []) if isinstance(r, dict)]


# The BUYER is the subject of the headline, not the site that published it.
# Taking the domain gave "Prnewswire", "Aol", "Pulse2" and "Finance" for five
# copies of one story about Hadrius (observed live 2026-08-13).
_HEADLINE_SUBJECT = re.compile(
    r"^([A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,3})\s+"
    r"(?:raises?|raised|wins?|won|awarded|lands?|secures?|launch(?:es|ed)?|"
    r"announces?|selects?|selected|names?|partners?|to build|is building)",
    re.I,
)
# Publishers and aggregators: never the buyer.
_PUBLISHER_HOSTS = re.compile(
    r"prnewswire|businesswire|globenewswire|yahoo|aol\.|reuters|bloomberg|"
    r"techcrunch|venturebeat|forbes|pulse2|itdigest|finance\.|news\.|"
    r"marketwatch|benzinga|streetinsider|einpresswire", re.I,
)
# Marketing listicles and vendor round-ups are not opportunities.
_LISTICLE = re.compile(
    r"\btop\s+\d+\b|best\s+\d+|buyer.s guide|vendor comparison|"
    r"software in 20\d\d|tools for|alternatives|review 20\d\d", re.I,
)


def _org_from_result(result: dict[str, Any]) -> str:
    """The buyer: subject of the headline, falling back to a non-publisher host."""
    title = str(result.get("title") or "").strip()
    m = _HEADLINE_SUBJECT.match(title)
    if m:
        subject = " ".join(m.group(1).split())
        if 2 <= len(subject) <= 60:
            return subject
    # No domain fallback. A lead requires a NAMED buyer taking a NAMED action
    # in the headline; falling back to the host produced investor blogs and
    # funding-list sites ("Crv", "Fundraiseinsider", "Qubit") as if they were
    # buyers. Federal solicitations already arrive properly via the SAM.gov
    # lane, so precision here beats recall.
    return ""


def discover(
    limit_queries: int = 8, per_query: int = 5
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Research consulting leads. Returns (lane-C candidates, receipt)."""
    queries = build_queries(limit=limit_queries)
    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    per_query_counts: list[dict[str, Any]] = []

    for q in queries:
        results = _brave_json(q["query"], count=per_query)
        kept = 0
        for r in results:
            url = str(r.get("url") or "")
            title = str(r.get("title") or "").strip()
            desc = str(r.get("description") or "")
            if not url or not title:
                continue
            if _NOT_A_BUYER.search(url):
                continue
            blob = f"{title} {desc}"
            m = _INTENT_EVIDENCE.search(blob)
            if not m:
                continue  # topic without buyer intent is not a lead
            if _LISTICLE.search(title):
                continue  # a "top 30 RFP tools" round-up is marketing, not a buyer
            org = _org_from_result(r)
            if not org:
                continue  # publisher-only row with no identifiable buyer
            # Dedupe by STORY (buyer + signal), not by URL: one funding round is
            # syndicated across many outlets and was landing five times.
            # One row per BUYER per run. A single funding round surfaces under
            # several signal kinds (contract_win and funding both matched the
            # same Hadrius story), which would double-count one opportunity.
            key = hashlib.sha256(org.lower().encode()).hexdigest()[:16]
            if key in seen:
                continue
            seen.add(key)
            candidates.append({
                "lane": "C",
                "source_provider": "consulting-research",
                "source_class": "commercial_signal",
                "source_identity": url,
                "organization": org or title[:60],
                "title": title[:140],
                "location_display": "Consulting engagement; delivery model negotiable",
                "workplace_type": "NOT_APPLICABLE",
                "relocation_required": False,
                "clearance_required": False,
                "posting_url": url,
                "apply_url": None,
                "primary_evidence_url": url,
                "published_at": r.get("page_age") or r.get("age"),
                "updated_at": None,
                "content_hash": hashlib.sha256(url.encode()).hexdigest(),
                "posting_text": f"{title}. {desc}"[:4000],
                "signal_kind": q["kind"],
                "buyer_intent_evidence": m.group(0),
                "matched_query": q["query"],
                "fit_score": 0.6,
                "candidate_id": f"candidate:c:research:{key}",
            })
            kept += 1
        per_query_counts.append({"kind": q["kind"], "query": q["query"],
                                 "results": len(results), "kept": kept})

    receipt = {
        "schema": "monitor_opportunities.consulting_discovery.v1",
        "queries_run": len(queries),
        "brave_search_available": BRAVE_SEARCH.exists(),
        "candidates": len(candidates),
        "by_signal_kind": {
            k: sum(1 for c in candidates if c["signal_kind"] == k)
            for k in {c["signal_kind"] for c in candidates}
        },
        "per_query": per_query_counts,
    }
    if not candidates:
        logger.warning("consulting research produced 0 leads across %d queries", len(queries))
    return candidates, receipt
