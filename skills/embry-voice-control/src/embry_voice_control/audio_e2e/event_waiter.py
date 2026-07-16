"""Wait for exact managed-listener events in the canonical journal."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from embry_voice_control.event_journal import session_snapshot


def journal_sequence_boundary(journal_db: Path, *, session_id: str) -> int:
    """Return the last committed sequence for one session."""
    return int(session_snapshot(journal_db, session_id)["through_sequence"])


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
    after_sequence: int = 0,
) -> dict[str, dict[str, Any]]:
    """Return the exact arm/final/completed chain, or fail with the missing type."""
    deadline = time.monotonic() + timeout_seconds
    required = (
        "listener.turn_armed",
        "listener.final_transcript",
        "listener.turn_completed",
    )
    while time.monotonic() < deadline:
        events = [
            event
            for event in session_snapshot(journal_db, session_id)["events"]
            if event["sequence"] > after_sequence
        ]
        armed = next(
            (
                event
                for event in events
                if event["type"] == required[0]
                and managed_fields_match(event, expected)
            ),
            None,
        )
        arm_sequence = armed["sequence"] if armed is not None else after_sequence
        final = next(
            (
                event
                for event in events
                if event["sequence"] > arm_sequence
                and event["type"] == required[1]
                and managed_fields_match(event, expected)
            ),
            None,
        )
        completed = next(
            (
                event for event in events
                if event["sequence"] > arm_sequence
                and event["type"] == required[2]
                and final is not None
                and event["turn_id"] == expected["turn_id"]
                and event["payload"].get("campaign_id") == expected["campaign_id"]
                and event["payload"].get("case_id") == expected["case_id"]
                and event["payload"].get("attempt_id") == expected["attempt_id"]
                and event.get("causation_id") == final["event_id"]
                and event["payload"].get("source_event_id") == final["event_id"]
                and event["payload"].get("source_sequence") == final["sequence"]
            ),
            None,
        )
        matched = {required[0]: armed, required[1]: final, required[2]: completed}
        if all(matched.values()):
            final = matched["listener.final_transcript"]
            completed = matched["listener.turn_completed"]
            if completed.get("causation_id") != final["event_id"]:
                raise ValueError("listener_completed_causation_mismatch")
            if completed["payload"].get("source_event_id") != final["event_id"]:
                raise ValueError("listener_completed_source_event_mismatch")
            if completed["payload"].get("source_sequence") != final["sequence"]:
                raise ValueError("listener_completed_source_sequence_mismatch")
            return matched  # type: ignore[return-value]
        time.sleep(poll_seconds)
    missing = [name for name in required if not matched.get(name)]
    raise TimeoutError("managed_listener_timeout:" + ",".join(missing))


def wait_for_managed_wake(
    journal_db: Path,
    *,
    session_id: str,
    expected: dict[str, str],
    timeout_seconds: float,
    poll_seconds: float = 0.2,
    after_sequence: int = 0,
) -> dict[str, Any]:
    """Return the exact managed wake event after the matching arm event."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        events = [
            event
            for event in session_snapshot(journal_db, session_id)["events"]
            if event["sequence"] > after_sequence
        ]
        armed = next(
            (event for event in events if event["type"] == "listener.turn_armed" and managed_fields_match(event, expected)),
            None,
        )
        wake = next(
            (
                event for event in events
                if armed is not None
                and event["type"] == "listener.wake_detected"
                and event["sequence"] > armed["sequence"]
                and managed_fields_match(event, expected)
            ),
            None,
        )
        if wake is not None:
            return wake
        time.sleep(poll_seconds)
    raise TimeoutError("managed_listener_timeout:listener.wake_detected")
