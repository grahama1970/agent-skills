"""Local LinkedIn handoff packets with no LinkedIn platform access."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .util import sha256_json, stable_id, utc_now, write_json


class LinkedInHandoffError(ValueError):
    """Stable LinkedIn handoff error."""


def write_linkedin_handoff_packet(*, packet: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    """Write a local human handoff packet and prove no platform call was attempted."""

    if packet.get("channel") != "LINKEDIN":
        raise LinkedInHandoffError("NOT_A_LINKEDIN_PACKET")
    payload = {
        "schema": "monitor_opportunities.linkedin_handoff_packet.v1",
        "handoff_id": stable_id("linkedin-handoff", packet["payload_digest"]),
        "packet_id": packet["packet_id"],
        "body": packet["body"],
        "claim_keys": packet["claim_keys"],
        "human_send_steps": packet["human_send_steps"],
        "linkedin_automated": False,
        "platform_calls_attempted": 0,
        "external_effects": False,
        "created_at": utc_now(),
    }
    path = out_dir / f"{payload['handoff_id'].replace(':', '-')}.json"
    payload["handoff_ref"] = str(path)
    payload["handoff_digest"] = sha256_json(payload)
    write_json(path, payload)
    return payload
