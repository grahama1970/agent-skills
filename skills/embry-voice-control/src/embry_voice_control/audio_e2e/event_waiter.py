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


def find_existing_managed_turn(
    journal_db: Path,
    *,
    session_id: str,
    expected: dict[str, str],
) -> dict[str, dict[str, Any]] | None:
    """Return one exact committed managed-turn chain for crash recovery."""
    events = session_snapshot(journal_db, session_id)["events"]
    arms = [
        event
        for event in events
        if event["type"] == "listener.turn_armed"
        and managed_fields_match(event, expected)
    ]
    if not arms:
        return None
    if len(arms) != 1:
        raise ValueError(
            f"managed_listener_recovery_conflicting_arms:{expected['turn_id']}:"
            f"{len(arms)}"
        )
    armed = arms[0]
    after_arm = [
        event for event in events if event["sequence"] > armed["sequence"]
    ]
    finals = [
        event
        for event in after_arm
        if event["type"] == "listener.final_transcript"
        and managed_fields_match(event, expected)
    ]
    if not finals:
        raise ValueError(
            "managed_listener_recovery_partial_chain_missing_final:"
            f"{expected['turn_id']}:{armed['event_id']}"
        )
    if len(finals) != 1:
        raise ValueError(
            f"managed_listener_recovery_conflicting_finals:{expected['turn_id']}:"
            f"{len(finals)}"
        )
    final = finals[0]
    completion_expected = {
        key: value
        for key, value in expected.items()
        if key != "source_authority_id"
    }
    lineage_completions = [
        event
        for event in after_arm
        if event["type"] == "listener.turn_completed"
        and managed_fields_match(event, completion_expected)
    ]
    completions = [
        event
        for event in lineage_completions
        if event["sequence"] > final["sequence"]
        and event.get("causation_id") == final["event_id"]
        and event.get("payload", {}).get("source_event_id") == final["event_id"]
        and event.get("payload", {}).get("source_sequence") == final["sequence"]
    ]
    if not lineage_completions:
        raise ValueError(
            "managed_listener_recovery_partial_chain_missing_completed:"
            f"{expected['turn_id']}:{final['event_id']}"
        )
    if len(lineage_completions) != 1 or len(completions) != 1:
        raise ValueError(
            "managed_listener_recovery_conflicting_completed:"
            f"{expected['turn_id']}:lineage={len(lineage_completions)}:"
            f"causal={len(completions)}"
        )
    completed = completions[0]
    wakes = [
        event
        for event in after_arm
        if event["type"] == "listener.wake_detected"
        and event["sequence"] < final["sequence"]
        and managed_fields_match(event, expected)
    ]
    if len(wakes) != 1:
        raise ValueError(
            f"managed_listener_recovery_wake_count_invalid:{expected['turn_id']}:"
            f"{len(wakes)}"
        )
    for event in (armed, wakes[0], final, completed):
        if event.get("live") is not True or event.get("mocked") is not False:
            raise ValueError(
                f"managed_listener_recovery_event_not_live:{event['event_id']}"
            )
    return {
        "listener.turn_armed": armed,
        "listener.wake_detected": wakes[0],
        "listener.final_transcript": final,
        "listener.turn_completed": completed,
    }


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


def wait_for_query_capture_armed(
    journal_db: Path,
    *,
    session_id: str,
    expected: dict[str, str],
    timeout_seconds: float,
    poll_seconds: float = 0.1,
    after_sequence: int = 0,
) -> dict[str, Any]:
    """Return the listener.query_capture_armed event after the matching wake.

    This is the observable post-wake readiness signal that replaces the runner's
    fixed post-wake sleep. The listener emits it only once it has re-entered
    post-wake voice-activity listening, so playing the query after this event
    (rather than after an elapsed interval) closes the
    QUERY_PLAYED_BEFORE_POST_WAKE_CAPTURE_ARMED race.
    """
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        events = [
            event
            for event in session_snapshot(journal_db, session_id)["events"]
            if event["sequence"] > after_sequence
        ]
        wake = next(
            (
                event
                for event in events
                if event["type"] == "listener.wake_detected"
                and managed_fields_match(event, expected)
            ),
            None,
        )
        armed = next(
            (
                event
                for event in events
                if wake is not None
                and event["type"] == "listener.query_capture_armed"
                and event["sequence"] > wake["sequence"]
                and managed_fields_match(event, expected)
            ),
            None,
        )
        if armed is not None:
            if armed.get("live") is not True or armed.get("mocked") is not False:
                raise ValueError(
                    f"query_capture_armed_not_live:{armed['event_id']}"
                )
            return armed
        time.sleep(poll_seconds)
    raise TimeoutError("managed_listener_timeout:listener.query_capture_armed")


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
