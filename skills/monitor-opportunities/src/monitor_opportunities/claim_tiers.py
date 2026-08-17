"""Tiered claim policy — what may be asserted, and in which channel.

Panel position (2026-08-17, kimi.ai seat, reaffirmed by Graham), enforced here
rather than left in prose:

- **Tier 1, public artifact** (repo, paper, patent, press release). May be
  asserted as an accomplishment in any channel.
- **Tier 2, attested history** (employment record, self-reported scope). A
  resume may carry it only as "experience with <domain>" or "background in
  <area>" — never with a leadership verb, a metric, or deliverable language.
  Outreach may reference it to establish relevance. An interview may probe it.
- **Tier 3, inferred competence** from an adjacent skill. Interview probing
  only; never asserted.

And the firewall, which all three panel seats reached independently: a reader
who sees a repository name beside a program or agency name infers the
repository was a contract deliverable. In defense contracting that inference is
not a style problem. So no single approved wording may name both.

Nothing here writes or invents a claim. It answers one question — may THIS
wording go in THIS channel — and names the rule that refused it.
"""

from __future__ import annotations

import re
from typing import Any

RESUME = "resume"
OUTREACH = "outreach"
INTERVIEW = "interview"
CHANNELS = (RESUME, OUTREACH, INTERVIEW)

# Verbs that turn attested history into an achievement claim.
LEADERSHIP_VERBS = (
    "led", "leading", "spearheaded", "directed", "managed", "owned", "drove",
    "founded", "architected", "headed", "oversaw", "ran",
)
# Language implying a contracted deliverable.
DELIVERABLE_TERMS = (
    "deliverable", "delivered under", "contract", "funded by", "-funded",
    "on behalf of", "awarded", "prime performer",
)
# Programs and agencies whose names carry public verifiability.
PROGRAM_TERMS = (
    "darpa", "arcos", "afwerx", "sbir", "sttr", "nasa", "dod", "air force",
    "navy", "army", "iarpa", "onr",
)
# Repository and product names in this candidate's corpus.
REPOSITORY_TERMS = (
    "sparta explorer", "sparta-public", "pdf_oxide", "pdf oxide", "extractor",
    "graph-memory-operator",
)
METRIC_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s*(?:%|percent|x|ms|s|k|m|b|hours?|days?|people|engineers?)\b", re.I)
ATTESTED_RESUME_OPENERS = ("experience with", "background in", "experience in", "background with")


def tier_of(claim: dict[str, Any]) -> int:
    """Declared tier. Absent tier is treated as 2 (attested), never as 1."""

    try:
        tier = int(claim.get("tier", 2))
    except (TypeError, ValueError):
        return 2
    return tier if tier in (1, 2, 3) else 2


def _contains_any(text: str, terms: tuple[str, ...]) -> list[str]:
    low = text.lower()
    return [term for term in terms if term in low]


def firewall_violation(text: str) -> dict[str, Any] | None:
    """Repository name and program/agency name in one wording."""

    repos = _contains_any(text, REPOSITORY_TERMS)
    programs = _contains_any(text, PROGRAM_TERMS)
    if repos and programs:
        return {
            "rule": "repository_program_co_occurrence",
            "repositories": repos,
            "programs": programs,
            "why": (
                "A reader infers the repository was a contract deliverable. Split the wording: the artifact "
                "belongs in a projects entry with no agency named, the employment belongs in an experience "
                "entry scoped to the employer."
            ),
        }
    return None


def check_wording(claim: dict[str, Any], wording: dict[str, Any], channel: str) -> dict[str, Any]:
    """May this approved wording be used in this channel? Returns a verdict row."""

    text = str(wording.get("text") or "")
    tier = tier_of(claim)
    violations: list[dict[str, Any]] = []

    firewall = firewall_violation(text)
    if firewall:
        violations.append(firewall)

    if tier == 3:
        violations.append({
            "rule": "tier3_never_asserted",
            "why": "Inferred competence may be probed in an interview, never asserted.",
        })
    elif tier == 2 and channel == RESUME:
        low = text.lower().strip()
        if not low.startswith(ATTESTED_RESUME_OPENERS):
            violations.append({
                "rule": "tier2_resume_requires_experience_framing",
                "why": (
                    "Attested history on a resume must read as 'experience with <domain>' or "
                    "'background in <area>'."
                ),
            })
        verbs = _contains_any(text, LEADERSHIP_VERBS)
        if verbs:
            violations.append({"rule": "tier2_leadership_verb", "found": verbs,
                               "why": "A leadership verb converts attested history into an achievement claim."})
        if METRIC_PATTERN.search(text):
            violations.append({"rule": "tier2_metric", "found": METRIC_PATTERN.search(text).group(0),
                               "why": "A metric on attested history cannot be checked by anyone."})
        deliverables = _contains_any(text, DELIVERABLE_TERMS)
        if deliverables:
            violations.append({"rule": "tier2_deliverable_language", "found": deliverables,
                               "why": "Deliverable language implies a contracted engagement."})

    return {
        "claim_key": claim.get("claim_key"),
        "wording_id": wording.get("wording_id"),
        "tier": tier,
        "channel": channel,
        "allowed": not violations,
        "violations": violations,
        "text": text,
    }


def audit_snapshot(snapshot: dict[str, Any], channels: tuple[str, ...] = CHANNELS) -> dict[str, Any]:
    """Every approved wording against every channel. Local, read-only."""

    rows: list[dict[str, Any]] = []
    for claim in snapshot.get("claims", []):
        if not claim.get("approved"):
            continue
        for wording in claim.get("wordings", []):
            if not wording.get("approved"):
                continue
            for channel in channels:
                rows.append(check_wording(claim, wording, channel))
    by_channel = {
        channel: {
            "allowed": sum(1 for r in rows if r["channel"] == channel and r["allowed"]),
            "refused": sum(1 for r in rows if r["channel"] == channel and not r["allowed"]),
        }
        for channel in channels
    }
    return {
        "schema": "monitor_opportunities.claim_tier_audit.v1",
        "claim_snapshot_profile_id": snapshot.get("candidate_profile_id"),
        "approved_wordings": len({(r["claim_key"], r["wording_id"]) for r in rows}),
        "by_channel": by_channel,
        "rows": rows,
        "non_claims": [
            "This audits WORDING against channel policy. It does not verify that a claim is true.",
            "A Tier 1 verdict means a public artifact exists, not that the artifact proves the sentence.",
        ],
        "external_effects": False,
    }
