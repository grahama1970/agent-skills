"""Prospect queue — the consulting/client track, equal in weight to the job track.

Federal solicitations (SAM/DARPA) and commercial signals are not noise to drop;
they are evidence that an organization is buying AI / compliance / document-
extraction work Graham can deliver. This module normalizes those signals into
prospect records and mandate-filters them so the queue carries real leads, not
the facilities/construction contracts a raw SAM sweep returns.

Inputs: SAM federal-capture evidence, lane-C commercial signals. Outputs:
prospect records {organization, signal_type, title, evidence_url, mandate_hits}.
No network, no writes here — routing to the tracker is the caller's job.
"""

from __future__ import annotations

import re
from typing import Any

from .relevance import mandate_hits as _entity_mandate_hits

# Fallback ONLY when /extract-entities or /memory is unavailable. The primary
# path is vocabulary-based whole-phrase matching via relevance.mandate_hits
# (best-practices-python: no regex for classifying unknown text).
_FALLBACK_MANDATE_RE = re.compile(
    r"artificial intelligence|machine learning|\bai\b|\bml\b|\bllm\b|autonom|"
    r"document|extraction|\bocr\b|\bidp\b|complian|assurance|verif|evaluat|"
    r"cyber|software|analytics|modern|digital|\br&d\b|research|model",
    re.I,
)
# Facilities/construction junk safety net (only bites the regex fallback path).
_JUNK_RE = re.compile(
    r"floor|paint|hvac|abatement|roof|plumb|janitor|landscap|construct|renovat|"
    r"elevator|pavement|boiler|carpet|window replace|door replace|grounds|"
    r"custodial|refuse|waste|mowing|snow removal|fencing|masonry|electrical repair",
    re.I,
)


def _mandate_hits(text: str) -> list[str]:
    """Vocabulary match via /extract-entities; regex fallback if unavailable."""
    hits = _entity_mandate_hits(text)
    if hits is not None:
        return hits
    return sorted({m.group(0).lower() for m in _FALLBACK_MANDATE_RE.finditer(text or "")})


def _is_real_opportunity_url(url: str) -> bool:
    # SAM opportunity views are /opp/...; /organization/ links are directory pages.
    u = (url or "").lower()
    return "/organization/" not in u and "/entity/" not in u


def federal_prospects(sam_evidence: dict[str, Any]) -> list[dict[str, Any]]:
    """Mandate-filter SAM solicitations into prospect records (drops junk/org pages)."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for opp in sam_evidence.get("opportunities", []):
        title = str(opp.get("title") or "").strip()
        url = str(opp.get("url") or "")
        if not title or not _is_real_opportunity_url(url):
            continue
        if _JUNK_RE.search(title):
            continue
        hits = _mandate_hits(title)
        if not hits:
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "organization": title,
                "title": f"Federal solicitation: {title}",
                "signal_type": "federal",
                "evidence_url": url,
                "source": "sam.gov_website",
                "mandate_hits": hits,
                "prospect_class": "federal_buyer",
            }
        )
    return out


def commercial_prospects(shortlist: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Lane-C commercial signals become prospect records."""
    out: list[dict[str, Any]] = []
    for c in shortlist:
        if c.get("lane") != "C":
            continue
        title = str(c.get("title") or "").strip()
        org = str(c.get("organization") or "").strip()
        out.append(
            {
                "organization": org or title,
                "title": f"Client signal: {org or title}",
                "signal_type": "commercial",
                "evidence_url": c.get("primary_evidence_url") or c.get("posting_url"),
                "source": c.get("source_provider") or "commercial-research",
                "mandate_hits": _mandate_hits(f"{title} {c.get('posting_text', '')}"),
                "prospect_class": "commercial_signal",
            }
        )
    return out


def relationship_prospects(relationship_signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Direct and adjacent contact paths become reconnect prospects.

    This is intentionally local-only: it queues a human decision to reconnect,
    attend, watch, skip, or defer. It never sends messages or claims the contact
    is reachable beyond the supplied evidence.
    """
    out: list[dict[str, Any]] = []
    for signal in relationship_signals:
        subject = str(signal.get("subject") or "").strip()
        org = str(signal.get("organization") or subject).strip()
        if not subject:
            continue
        out.append(
            {
                "organization": org,
                "title": f"Reconnect signal: {subject} — {org}",
                "signal_type": "relationship",
                "evidence_url": (signal.get("evidence_refs") or [None])[0],
                "source": "monitor-contacts",
                "mandate_hits": ["relationship", str(signal.get("signal_type") or "contact")],
                "prospect_class": "warm_reconnect",
                "relationship_signal_id": signal.get("signal_id"),
                "relationship_path": signal.get("relationship_path", []),
                "recommended_action": signal.get("recommended_action"),
                "contact_channel_risk": signal.get("contact_channel_risk"),
                "preferred_human_channels": signal.get("preferred_human_channels", []),
                "channel_guidance": signal.get("channel_guidance", []),
                "external_effects": False,
            }
        )
    return out


def build_prospect_queue(
    sam_evidence: dict[str, Any] | None,
    shortlist: list[dict[str, Any]],
    relationship_signals: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Assemble the full prospect queue from federal + commercial signals."""
    prospects: list[dict[str, Any]] = []
    if sam_evidence:
        prospects += federal_prospects(sam_evidence)
    prospects += commercial_prospects(shortlist)
    prospects += relationship_prospects(relationship_signals or [])
    return prospects
