"""Wait for exact managed-listener events in the canonical journal."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from embry_voice_control.event_journal import session_snapshot


def managed_fields_match(event: dict[str, Any], expected: dict[str, str]) -> bool:
    payload = event.get("payload") or {}
    managed = payload.get("managed_turn") or payload
    projected = dict(managed)
    if event.get("session_id") is not None:
        projected["session_id"] = event["session_id"]
    if event.get("turn_id") is not None:
        projected["turn_id"] = event["turn_id"]
    return all(projected.get(key) == value for key, value in expected.items())


def wait_for_managed_turn(
    journal_db: Path,
    *,
    session_id: str,
    expected: dict[str, str],
    timeout_seconds: float,
    poll_seconds: float = 0.2,
) -> dict[str, dict[str, Any]]:
    """Return the exact arm/final/completed chain, or fail with the missing type."""
    deadline = time.monotonic() + timeout_seconds
    required = (
        "listener.turn_armed",
        "listener.final_transcript",
        "listener.turn_completed",
    )
    while time.monotonic() < deadline:
        events = session_snapshot(journal_db, session_id)["events"]
        armed = next((event for event in events if event["type"] == required[0] and managed_fields_match(event, expected)), None)
        final = next((event for event in events if event["type"] == required[1] and managed_fields_match(event, expected)), None)
        completed = next(
            (
                event for event in events
                if event["type"] == required[2]
                and event["turn_id"] == expected["turn_id"]
                and event["payload"].get("campaign_id") == expected["campaign_id"]
                and event["payload"].get("case_id") == expected["case_id"]
                and event["payload"].get("attempt_id") == expected["attempt_id"]
            ),
            None,
        )
        matched = {required[0]: armed, required[1]: final, required[2]: completed}
        if all(matched.values()):
            final = matched["listener.final_transcript"]
            completed = matched["listener.turn_completed"]
            if completed["payload"].get("source_event_id") != final["event_id"]:
                raise ValueError("listener_completed_source_event_mismatch")
            return matched  # type: ignore[return-value]
        time.sleep(poll_seconds)
    missing = [name for name in required if not matched.get(name)]
    raise TimeoutError("managed_listener_timeout:" + ",".join(missing))
