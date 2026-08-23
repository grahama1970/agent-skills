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


def _relationship_exclusion(
    signal: dict[str, Any], seen_signal_ids: set[str]
) -> tuple[str | None, bool]:
    """Return an exclusion reason and whether this signal id should be recorded."""
    sid = str(signal.get("signal_id") or "")
    if sid and sid in seen_signal_ids:
        return "duplicate_signal_id", False
    if signal.get("visible_in_report") is False:
        return "not_report_visible", True
    if not str(signal.get("subject") or "").strip():
        return "missing_subject", True
    return None, True


def relationship_prospect_projection(relationship_signals: list[dict[str, Any]]) -> dict[str, Any]:
    """Project relationship signals into prospects plus inclusion/exclusion accounting.

    This is intentionally local-only: it queues a human decision to reconnect,
    attend, watch, skip, or defer. It never sends messages or claims the contact
    is reachable beyond the supplied evidence.
    """
    out: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    seen_signal_ids: set[str] = set()
    for index, signal in enumerate(relationship_signals):
        sid = str(signal.get("signal_id") or "")
        reason, record_signal_id = _relationship_exclusion(signal, seen_signal_ids)
        if record_signal_id and sid:
            seen_signal_ids.add(sid)
        if reason:
            exclusions.append(
                {
                    "index": index,
                    "reason": reason,
                    "signal_id": signal.get("signal_id"),
                    "subject": signal.get("subject"),
                    "organization": signal.get("organization"),
                    "visible_in_report": signal.get("visible_in_report"),
                }
            )
            continue
        subject = str(signal.get("subject") or "").strip()
        org = str(signal.get("organization") or subject).strip()
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
                # The resolved LinkedIn candidates are the actionable half of a
                # Meetup lead; the projection silently dropped them on 2026-08-20
                # (receipt counted strong_top_candidate: 3, queue carried none).
                "subject": signal.get("subject"),
                "linkedin_top_candidate": signal.get("linkedin_top_candidate"),
                "linkedin_candidates": (signal.get("linkedin_candidates") or [])[:3],
                "linkedin_confirmation_required": signal.get("linkedin_confirmation_required", False),
                "event_title": signal.get("event_title"),
                "relationship_path": signal.get("relationship_path", []),
                "recommended_action": signal.get("recommended_action"),
                "contact_channel_risk": signal.get("contact_channel_risk"),
                "preferred_human_channels": signal.get("preferred_human_channels", []),
                "channel_guidance": signal.get("channel_guidance", []),
                "external_effects": False,
            }
        )
    return {
        "prospects": out,
        "relationship_signals": {
            "input": len(relationship_signals),
            "included": len(out),
            "excluded": len(exclusions),
            "exclusions": exclusions,
            "unaccounted": 0,
        },
    }


def relationship_prospects(relationship_signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Direct and adjacent contact paths become reconnect prospects."""
    return list(relationship_prospect_projection(relationship_signals)["prospects"])


def build_prospect_queue_receipt(
    sam_evidence: dict[str, Any] | None,
    shortlist: list[dict[str, Any]],
    relationship_signals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble prospects with relationship inclusion/exclusion accounting."""
    federal = federal_prospects(sam_evidence) if sam_evidence else []
    commercial = commercial_prospects(shortlist)
    relationship = relationship_prospect_projection(relationship_signals or [])
    prospects = [*federal, *commercial, *relationship["prospects"]]
    return {
        "prospects": prospects,
        "counts": {
            "total": len(prospects),
            "federal": len(federal),
            "commercial": len(commercial),
            "relationship": len(relationship["prospects"]),
        },
        "relationship_signals": relationship["relationship_signals"],
    }


def build_prospect_queue(
    sam_evidence: dict[str, Any] | None,
    shortlist: list[dict[str, Any]],
    relationship_signals: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Assemble the full prospect queue from federal + commercial signals."""
    return list(
        build_prospect_queue_receipt(sam_evidence, shortlist, relationship_signals)["prospects"]
    )
