"""Draft-only Gmail handoff adapter with fail-closed promotion gates.

This module can create a mailbox draft only through an injected adapter after a
human promotion receipt grants exactly `gmail_mailbox_draft_create`. It never
implements send, schedule-send, forward, or transmitted-state observation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .util import read_jsonl, sha256_json, stable_id, utc_now, write_jsonl


class GmailDraftAdapter(Protocol):
    """Minimal draft-only adapter surface."""

    def create_draft(self, *, subject: str, body: str, idempotency_marker: str) -> dict[str, Any]:
        """Create one draft or return an indeterminate receipt."""

    def read_draft(self, draft_id: str) -> dict[str, Any]:
        """Read back a draft by id."""

    def find_draft_by_idempotency_marker(self, idempotency_marker: str) -> dict[str, Any] | None:
        """Reconcile an uncertain create by idempotency marker."""


class GmailHandoffError(ValueError):
    """Stable Gmail draft handoff error."""


FORBIDDEN_GMAIL_EFFECTS = ("gmail_send", "gmail_schedule_send", "gmail_forward")


def gmail_send_authority_state() -> dict[str, Any]:
    """Return the permanent no-send authority state."""

    return {
        "schema": "monitor_opportunities.gmail_authority.v1",
        "gmail_mailbox_draft_create": "PROMOTABLE_DRAFT_ONLY",
        "forbidden_effects": list(FORBIDDEN_GMAIL_EFFECTS),
        "gmail_sent": False,
        "external_effects": False,
    }


def create_gmail_mailbox_draft(
    *,
    packet: dict[str, Any],
    promotion_receipt: dict[str, Any] | None,
    adapter: GmailDraftAdapter,
    ledger_path: Path,
    idempotency_key: str,
) -> dict[str, Any]:
    """Create one draft after draft-only promotion, reconciling uncertainty."""

    _require_promoted(promotion_receipt)
    _require_ready_gmail_packet(packet)
    rows = read_jsonl(ledger_path)
    for row in rows:
        if row.get("idempotency_key") == idempotency_key:
            return row

    marker = stable_id("gmail-draft-marker", {"packet": packet["payload_digest"], "key": idempotency_key})
    create_result = adapter.create_draft(
        subject=packet.get("subject") or "",
        body=packet["body"],
        idempotency_marker=marker,
    )
    if create_result.get("status") == "INDETERMINATE":
        reconciled = adapter.find_draft_by_idempotency_marker(marker)
        if reconciled is None:
            receipt = _effect_receipt(
                packet=packet,
                idempotency_key=idempotency_key,
                idempotency_marker=marker,
                state="INDETERMINATE",
                draft=None,
            )
            rows.append(receipt)
            write_jsonl(ledger_path, rows)
            return receipt
        create_result = reconciled

    draft_id = str(create_result.get("draft_id") or "")
    if not draft_id:
        raise GmailHandoffError("GMAIL_DRAFT_ID_MISSING")
    draft = adapter.read_draft(draft_id)
    _verify_draft_readback(packet, draft)
    receipt = _effect_receipt(
        packet=packet,
        idempotency_key=idempotency_key,
        idempotency_marker=marker,
        state="DRAFT_CREATED_NOT_SENT",
        draft=draft,
    )
    rows.append(receipt)
    write_jsonl(ledger_path, rows)
    return receipt


def _require_promoted(promotion: dict[str, Any] | None) -> None:
    if promotion is None:
        raise GmailHandoffError("GMAIL_DRAFT_PROMOTION_MISSING")
    if promotion.get("capability") != "gmail_mailbox_draft_create":
        raise GmailHandoffError("GMAIL_DRAFT_PROMOTION_WRONG_CAPABILITY")
    if promotion.get("actor") != "human" or promotion.get("decision") != "PROMOTE":
        raise GmailHandoffError("GMAIL_DRAFT_PROMOTION_NOT_HUMAN_PROMOTE")
    forbidden = set(promotion.get("does_not_authorize", []))
    if not {"gmail_send", "gmail_schedule_send", "gmail_forward"}.issubset(forbidden):
        raise GmailHandoffError("GMAIL_PROMOTION_MUST_EXCLUDE_SEND_EFFECTS")


def _require_ready_gmail_packet(packet: dict[str, Any]) -> None:
    if packet.get("channel") != "GMAIL":
        raise GmailHandoffError("NOT_A_GMAIL_PACKET")
    if packet.get("roundtable_status") != "PASS" or packet.get("readiness_state") != "REVIEW_PERMITTED":
        raise GmailHandoffError("GMAIL_PACKET_NOT_REVIEW_PERMITTED")
    if packet.get("candidate_transmits") is not True or packet.get("sendable") is not False:
        raise GmailHandoffError("GMAIL_PACKET_TRANSMISSION_POLICY_INVALID")


def _verify_draft_readback(packet: dict[str, Any], draft: dict[str, Any]) -> None:
    if draft.get("sent") is not False:
        raise GmailHandoffError("GMAIL_DRAFT_READBACK_SENT")
    subject = packet.get("subject") or ""
    if draft.get("subject") != subject or draft.get("body") != packet.get("body"):
        raise GmailHandoffError("GMAIL_DRAFT_READBACK_DIGEST_MISMATCH")


def _effect_receipt(
    *,
    packet: dict[str, Any],
    idempotency_key: str,
    idempotency_marker: str,
    state: str,
    draft: dict[str, Any] | None,
) -> dict[str, Any]:
    subject = draft.get("subject") if draft else None
    body = draft.get("body") if draft else None
    payload = {
        "schema": "monitor_opportunities.outreach_effect_receipt.v1",
        "effect_id": stable_id("gmail-draft-effect", {"packet": packet["packet_id"], "key": idempotency_key}),
        "packet_id": packet["packet_id"],
        "channel": "GMAIL",
        "state": state,
        "draft_id": draft.get("draft_id") if draft else None,
        "idempotency_key": idempotency_key,
        "idempotency_marker": idempotency_marker,
        "subject_digest": sha256_json(subject) if subject is not None else None,
        "body_digest": sha256_json(body) if body is not None else None,
        "gmail_sent": False,
        "linkedin_automated": False,
        "external_effects": state == "DRAFT_CREATED_NOT_SENT",
        "created_at": utc_now(),
    }
    return {**payload, "receipt_digest": sha256_json(payload)}
