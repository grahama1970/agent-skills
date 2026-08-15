"""Relationship graph exports for opportunity/reconnect consumers.

The monitor owns contact freshness and relationship observations. Consumers
such as monitor-opportunities decide how to rank or display those observations.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any


DEFAULT_CHANNELS = [
    "LINKEDIN_HUMAN_HANDOFF",
    "AUTHORIZED_PERSONA_GMAIL",
    "VERIFIED_CURRENT_EMAIL",
]
DEFAULT_CHANNEL_GUIDANCE = [
    "Corporate email may be blocked or stale after a long contact gap.",
    "Prefer a LinkedIn human handoff when a profile or shared context exists.",
    "Use an authorized persona Gmail address only when owned/approved, non-deceptive, and human-transmitted.",
    "Do not automate outreach, RSVP, LinkedIn messaging, or email sending from this signal.",
]


def relationship_signal_key(source_id: str, subject: str, organization: str) -> str:
    payload = "|".join([source_id, subject, organization]).lower()
    return "rel-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _signal_type(row: dict[str, Any]) -> str:
    raw = str(row.get("relationship_type") or row.get("signal_type") or "").strip().lower()
    if raw in {"direct_contact", "adjacent_contact", "organization_sponsor", "event_copresence"}:
        return raw
    if row.get("event") or row.get("meetup_url"):
        return "event_copresence"
    if row.get("sponsor") or row.get("company_sponsor"):
        return "organization_sponsor"
    return "direct_contact" if row.get("known_direct") is True else "adjacent_contact"


def reconnect_signals_from_observations(
    contacts: list[dict[str, Any]],
    *,
    source_id: str = "monitor-contacts:observations",
) -> list[dict[str, Any]]:
    """Emit local-only relationship signals from observed contact records."""

    signals: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in contacts:
        subject = str(row.get("name") or row.get("subject") or "").strip()
        if not subject or not re.search(r"[A-Za-z]", subject):
            continue
        organization = str(row.get("org") or row.get("organization") or "").strip()
        if not organization:
            organization = "unknown_or_historical_org"
        source = str(row.get("source_id") or source_id)
        signal_id = relationship_signal_key(source, subject, organization)
        if signal_id in seen:
            continue
        seen.add(signal_id)
        relationship_type = _signal_type(row)
        path = _as_str_list(row.get("relationship_path")) or ["Graham Anderson", subject]
        if organization and organization.lower() not in " ".join(path).lower():
            path.append(organization)
        evidence_refs = _as_str_list(row.get("evidence_refs"))
        for field in ("profile", "source_url", "meetup_url"):
            if row.get(field):
                evidence_refs.append(str(row[field]))
        signals.append(
            {
                "signal_id": signal_id,
                "source_opportunity_id": source,
                "signal_type": relationship_type,
                "subject": subject,
                "organization": organization,
                "relationship_path": path,
                "evidence_refs": list(dict.fromkeys(evidence_refs)),
                "source_receipt_ids": _as_str_list(row.get("source_receipt_ids")),
                "provenance": str(row.get("provenance") or "monitor-contacts relationship observation"),
                "recommended_action": str(row.get("recommended_action") or "human_decide_reconnect_or_defer"),
                "contact_channel_risk": "corporate_email_may_be_blocked_after_long_gap",
                "preferred_human_channels": _as_str_list(row.get("preferred_human_channels")) or list(DEFAULT_CHANNELS),
                "channel_guidance": _as_str_list(row.get("channel_guidance")) or list(DEFAULT_CHANNEL_GUIDANCE),
                "external_effects": False,
                "action_worthy": True,
                "visible_in_report": True,
            }
        )
    return signals
