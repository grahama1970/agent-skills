"""Build claim-bound local outreach packets for human transmission.

The packet builder is Stage 0 local-only: it writes no Gmail draft, performs no
LinkedIn access, and treats missing roundtable evidence as a readiness blocker.
Unsupported factual claims fail closed before packet creation.
"""

from __future__ import annotations

from typing import Any

from .contracts import IMMUTABLE_GOAL
from .roundtable_gate import validate_roundtable_receipt
from .util import sha256_json, stable_id

OUTREACH_CHANNELS = ("GMAIL", "LINKEDIN")


class OutreachError(ValueError):
    """Stable outreach construction error."""


def approved_claims_by_key(claim_snapshot: dict[str, Any], channel: str) -> dict[str, dict[str, Any]]:
    """Return approved claims allowed for the requested outreach channel."""

    channel_name = {"GMAIL": "email", "LINKEDIN": "linkedin"}.get(channel, channel.lower())
    approved: dict[str, dict[str, Any]] = {}
    for claim in claim_snapshot.get("claims", []):
        if claim.get("approved") is not True:
            continue
        if channel_name not in {str(item).lower() for item in claim.get("allowed_channels", [])}:
            continue
        approved[claim["claim_key"]] = claim
    return approved


def build_outreach_packets(
    *,
    opportunities: list[dict[str, Any]],
    claim_snapshot: dict[str, Any],
    roundtable_receipts: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build report-visible local outreach packets for every shortlisted opportunity."""

    receipts = roundtable_receipts or {}
    packets: list[dict[str, Any]] = []
    for opportunity in opportunities:
        for channel in OUTREACH_CHANNELS:
            packets.append(
                build_outreach_packet(
                    opportunity=opportunity,
                    channel=channel,
                    claim_snapshot=claim_snapshot,
                    roundtable_receipt=receipts.get(_receipt_key(opportunity["opportunity_id"], channel)),
                )
            )
    return packets


def build_outreach_packet(
    *,
    opportunity: dict[str, Any],
    channel: str,
    claim_snapshot: dict[str, Any],
    roundtable_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create one claim-bound local outreach packet."""

    if channel not in OUTREACH_CHANNELS:
        raise OutreachError(f"unsupported outreach channel: {channel}")
    approved = approved_claims_by_key(claim_snapshot, channel)
    claim_keys = list(opportunity.get("claim_keys", []))
    missing = [claim_key for claim_key in claim_keys if claim_key not in approved]
    if missing:
        raise OutreachError("UNSUPPORTED_CLAIM: " + ", ".join(missing))

    recipient = "CONTACT_UNKNOWN"
    contact_provenance = "CONTACT_UNKNOWN"
    subject = None if channel == "LINKEDIN" else f"Relevant background for {opportunity['organization']}"
    body = _body(opportunity, channel, [approved[key] for key in claim_keys])
    basis = {
        "immutable_goal": IMMUTABLE_GOAL,
        "opportunity_id": opportunity["opportunity_id"],
        "channel": channel,
        "recipient": recipient,
        "contact_provenance": contact_provenance,
        "subject": subject,
        "body": body,
        "claim_keys": claim_keys,
        "candidate_transmits": True,
    }
    payload_digest = sha256_json(basis)
    gate = validate_roundtable_receipt(roundtable_receipt, payload_digest)
    ready_state = "REVIEW_PERMITTED" if gate["ok"] else "BLOCKED_ROUNDTABLE"
    return {
        "packet_id": stable_id("outreach", {"opportunity_id": opportunity["opportunity_id"], "channel": channel}),
        "opportunity_id": opportunity["opportunity_id"],
        "channel": channel,
        "recipient": recipient,
        "contact_provenance": contact_provenance,
        "subject": subject,
        "body": body,
        "character_count": len(body),
        "claim_keys": claim_keys,
        "roundtable_status": "PASS" if gate["ok"] else ("NOT_RUN" if roundtable_receipt is None else "BLOCKED"),
        "roundtable_verdict": gate["verdict"],
        "roundtable_receipt_digest": gate["receipt_digest"],
        "payload_digest": payload_digest,
        "readiness_state": ready_state,
        "effect_status": "WOULD_PRESENT_STAGE0",
        "sendable": False,
        "candidate_transmits": True,
        "human_send_steps": _human_steps(channel),
        "action_worthy": True,
        "visible_in_report": True,
    }


def _receipt_key(opportunity_id: str, channel: str) -> str:
    return f"{opportunity_id}:{channel}"


def _body(opportunity: dict[str, Any], channel: str, claims: list[dict[str, Any]]) -> str:
    claim_lines = []
    for claim in claims:
        wording = next((item for item in claim.get("wordings", []) if item.get("approved") is True), None)
        if wording is None:
            raise OutreachError(f"APPROVED_WORDING_MISSING: {claim['claim_key']}")
        claim_lines.append(f"- {wording['text']} [{claim['claim_key']}]")
    opener = (
        f"I found the {opportunity['title']} opportunity at {opportunity['organization']} "
        "and would like to share a concise, claim-bound fit summary."
        if channel == "GMAIL"
        else f"I found the {opportunity['title']} opportunity at {opportunity['organization']}."
    )
    return "\n".join(
        [
            opener,
            "",
            "Relevant approved claims:",
            *claim_lines,
            "",
            "Human transmission note: Graham reviews and sends this text manually.",
        ]
    )


def _human_steps(channel: str) -> list[str]:
    if channel == "GMAIL":
        return [
            "Review the subject and body in the morning report.",
            "Choose the recipient in Gmail from known contact provenance; do not infer a recipient.",
            "Create or edit the draft manually, then send only if Graham decides to transmit.",
        ]
    return [
        "Review the body in the morning report.",
        "Open LinkedIn manually; the skill does not log in, browse, connect, message, or post.",
        "Paste or adapt the text only if Graham decides to transmit.",
    ]
