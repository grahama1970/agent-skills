"""Suggest WHO to reach out to this week. The grunt work is the point.

If the human has to discover their own contacts, rank them, resolve identities,
and decide the angle, the skill is worthless - Daniel Ayala (Aerospace Corp,
cybersecurity) was exactly the kind of contact it should have surfaced, and the
human found him unaided.

This assembles signals the pipeline already captures - Meetup attendees, GitHub
contributors, the ARCOS network, mailbox warm paths - scores each person by how
well their organization and role fit the mandate, adds a reachability bonus when
a strong LinkedIn match or a warm path exists, and returns a ranked "reach out"
list. Each row carries the person, the profile candidate, WHY they matter, and a
suggested opening angle. The human decides; the machine did the finding.

Never asserts identity or contacts anyone: every LinkedIn match stays a
confirm-first hypothesis, every row is a suggestion.
"""

from __future__ import annotations

import re
from typing import Any

from .relevance import mandate_hits

# Reachability signals that make a suggestion actionable, not just relevant.
STRONG_CONFIDENCE = "strong"


def _relevance(subject: str, org: str, role: str, provenance: str) -> tuple[int, list[str]]:
    """Mandate concepts this person's org/role hits. The Ayala test: aerospace +
    cyber should score, a walking-club member should not."""

    # Repo names arrive underscore/slash-joined (OpenC3_Cosmos_cFS_CFDP), so
    # whole-phrase matching never sees 'OpenC3' or 'cFS'. Split separators.
    raw = " ".join(x for x in (org, role, provenance) if x)
    text = re.sub(r"[_/\-]+", " ", raw)
    hits = mandate_hits(text)
    if hits is None:  # vocabulary unavailable - degrade to zero, never guess relevance
        return 0, []
    return len(hits), hits


def _angle(mandate: list[str], org: str) -> str:
    if any("aerospace" in m or "rd-" in m or "arcos" in m for m in mandate):
        return f"Shared aerospace/certification-evidence background; ask how {org} approaches assurance tooling."
    if any("compliance" in m or "cyber" in m or "security" in m for m in mandate):
        return f"Compliance/security overlap with the Sparta work; compare notes on evidence-to-control tracing at {org}."
    if any("agentic" in m or "ai" in m or "llm" in m or "extraction" in m for m in mandate):
        return f"AI/agentic-pipeline overlap; ask what {org} is building and where extraction/retrieval fits."
    return f"Relevant work at {org}; open with the specific thing you have in common."


def recommend_contacts(
    relationship_signals: list[dict[str, Any]],
    *,
    limit: int = 8,
) -> dict[str, Any]:
    """Ranked reach-out suggestions from the run's relationship signals."""

    scored: list[dict[str, Any]] = []
    seen: set[str] = set()
    for signal in relationship_signals:
        subject = str(signal.get("subject") or "").strip()
        if not subject or subject.lower() in seen:
            continue
        org = str(signal.get("organization") or "").strip()
        role = str(signal.get("role") or signal.get("event_title") or "").strip()
        # The repo name and path carry the domain a bare handle-as-org loses:
        # 'rtinney1' scores nothing, but 'OpenC3 Cosmos cFS' (space-flight
        # software) is exactly the aerospace signal that makes Randi Tinney worth
        # contacting. Fold the path and evidence into the relevance text.
        context = " ".join([
            str(signal.get("provenance") or ""),
            " ".join(str(x) for x in (signal.get("relationship_path") or [])),
            " ".join(str(x) for x in (signal.get("evidence_refs") or [])),
        ])
        relevance, mandate = _relevance(subject, org, role, context)
        if relevance == 0:
            continue  # not mandate-relevant: do not suggest reaching out
        seen.add(subject.lower())

        top = signal.get("linkedin_top_candidate")
        candidates = signal.get("linkedin_candidates") or []
        strong = bool(top) and (candidates and candidates[0].get("confidence") == STRONG_CONFIDENCE)
        reachability = (2 if strong else 1 if candidates else 0) + (1 if signal.get("organizer") else 0)

        scored.append(
            {
                "subject": subject,
                "organization": org,
                "role": role,
                "signal_type": signal.get("signal_type"),
                "why": f"{relevance} mandate match ({', '.join(mandate)}) via {signal.get('signal_type')}",
                "mandate_hits": mandate,
                "linkedin_top_candidate": top,
                "linkedin_confidence": (candidates[0].get("confidence") if candidates else None),
                "linkedin_confirmation_required": True,
                "suggested_angle": _angle(mandate, org or "their team"),
                "score": relevance * 2 + reachability,
                "evidence_refs": signal.get("evidence_refs") or [],
            }
        )
    scored.sort(key=lambda r: -r["score"])
    return {
        "schema": "monitor_opportunities.suggested_contacts.v1",
        "suggestions": scored[:limit],
        "considered": len(relationship_signals),
        "mandate_relevant": len(scored),
        "non_claims": [
            "Every LinkedIn match is a confirm-first hypothesis; no identity is asserted.",
            "Suggestions only. The human decides who to contact and the skill contacts no one.",
        ],
        "external_effects": False,
    }
