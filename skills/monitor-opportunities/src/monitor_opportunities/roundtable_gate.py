"""Roundtable receipt validation for claim-bound outreach packets.

Inputs are local JSON receipt dictionaries produced by the documented Ask
roundtable path. This module performs no provider calls. It only decides
whether a receipt permits a local human-transmit outreach packet to be marked
review-permitted.
"""

from __future__ import annotations

from typing import Any

from .contracts import IMMUTABLE_GOAL
from .util import sha256_json

PERMITTING_VERDICTS = {"SEND_AS_IS", "SEND_WITH_REVISIONS"}


def validate_roundtable_receipt(receipt: dict[str, Any] | None, packet_digest: str) -> dict[str, Any]:
    """Return a fail-closed validation receipt for one outreach roundtable."""

    errors: list[str] = []
    if receipt is None:
        errors.append("ROUNDTABLE_RECEIPT_MISSING")
        return _result(False, None, None, errors)

    verdict = receipt.get("verdict")
    if verdict not in PERMITTING_VERDICTS:
        errors.append("ROUNDTABLE_VERDICT_NOT_PERMITTING")
    if receipt.get("immutable_goal") != IMMUTABLE_GOAL:
        errors.append("IMMUTABLE_GOAL_MISMATCH")
    if receipt.get("topology") != "concurrent":
        errors.append("ROUNDTABLE_NOT_CONCURRENT")
    if int(receipt.get("rounds", 0)) > 3:
        errors.append("ROUNDTABLE_TOO_MANY_ROUNDS")
    if receipt.get("attributed_synthesis") is not True:
        errors.append("ATTRIBUTED_SYNTHESIS_MISSING")
    if receipt.get("packet_digest") != packet_digest:
        errors.append("PACKET_DIGEST_MISMATCH")

    seats = receipt.get("seats", [])
    pass_count = sum(1 for seat in seats if isinstance(seat, dict) and seat.get("status") == "PASS")
    if pass_count < 2:
        errors.append("INSUFFICIENT_PASS_SEATS")

    return _result(
        not errors,
        str(verdict) if verdict is not None else None,
        sha256_json(receipt),
        errors,
    )


def _result(ok: bool, verdict: str | None, digest: str | None, errors: list[str]) -> dict[str, Any]:
    return {
        "schema": "monitor_opportunities.outreach_roundtable_gate.v1",
        "ok": ok,
        "verdict": verdict,
        "receipt_digest": digest,
        "errors": errors,
        "external_effects": False,
    }
