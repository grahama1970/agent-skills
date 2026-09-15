"""Live-question bridge: consume the live-evidence SSE snapshot stream and
relay completed interviewer turns to cockpit intake.

The real ``GET {EXPLAIN_PROJECT_LIVE_EVIDENCE_URL}/api/events`` is a
Server-Sent Events stream of full ``live_evidence.app_snapshot.v1`` frames
(verified against skills/live-evidence src 2026-09-15). This bridge streams
those frames, assembles interviewer transcript turns (kind
stabilized/final, grouped by ``turn_id``), posts each CLOSED turn (a final
event exists and a later event from another turn follows it) to
``CockpitSession.intake_live_evidence`` labeled ``live_evidence_live``, and
degrades honestly when the service is unreachable: no cockpit state is
touched, so manual input stays functional.

Fidelity boundary: upstream QuestionWindowBuilder owns full segmentation,
near-duplicate suppression, and correction revisions; agent-skills#1725
tracks exposing the active question in AppSnapshot so this bridge can relay
upstream truth directly instead of deriving turns from transcript events.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from typing import Any, Iterator

import httpx
from pydantic import ValidationError

INTAKE_SCHEMA = "explain_project.live_evidence_intake.v1"
DEFAULT_BASE_URL = "http://127.0.0.1:8799"
RECONNECT_SECONDS = 2.0
STABLE_KINDS = {"stabilized", "final"}


def _base_url(url: str | None) -> str:
    base = (
        url
        or os.environ.get(
            "EXPLAIN_PROJECT_LIVE_EVIDENCE_URL",
            DEFAULT_BASE_URL,
        )
    ).rstrip("/")
    return base


class VoiceBridge:
    """Stream live-evidence snapshots; post closed interviewer turns."""

    def __init__(
        self,
        session: Any,
        url: str | None = None,
        reconnect_seconds: float = RECONNECT_SECONDS,
    ) -> None:
        self._session = session
        self._base = _base_url(url)
        self._reconnect_seconds = reconnect_seconds
        self._posted: set[str] = set()
        self._lock = threading.Lock()
        self.consecutive_failures = 0
        self.last_success_monotonic: float | None = None

    def health(self) -> dict[str, Any]:
        """Honest bridge health; never claims cockpit state."""
        return {
            "reachable": self.consecutive_failures == 0,
            "consecutive_failures": self.consecutive_failures,
            "last_success_monotonic": (
                self.last_success_monotonic
            ),
        }

    # -- snapshot processing -------------------------------------------

    @staticmethod
    def _turn_key(event: dict[str, Any]) -> str:
        turn_id = event.get("turn_id")
        return (
            f"turn:{turn_id}"
            if isinstance(turn_id, str) and turn_id
            else f"event:{event.get('event_id')}"
        )

    def _closed_turns(
        self,
        transcript: list[dict[str, Any]],
    ) -> list[list[dict[str, Any]]]:
        """Interviewer turns that contain a final event and are followed by
        a later event from a different turn."""

        interviewer = [
            event
            for event in transcript
            if isinstance(event, dict)
            and event.get("speaker") == "interviewer"
            and event.get("kind") in STABLE_KINDS
        ]
        turns: dict[str, list[dict[str, Any]]] = {}
        for event in interviewer:
            turns.setdefault(self._turn_key(event), []).append(event)

        closed: list[list[dict[str, Any]]] = []
        for key, events in turns.items():
            if not any(e.get("kind") == "final" for e in events):
                continue
            turn_max_seq = max(
                (e.get("sequence") or 0) for e in events
            )
            followed = any(
                isinstance(event, dict)
                and self._turn_key(event) != key
                and (event.get("sequence") or 0) > turn_max_seq
                for event in transcript
            )
            if followed:
                closed.append(
                    sorted(
                        events,
                        key=lambda e: e.get("sequence") or 0,
                    )
                )
        return closed

    @staticmethod
    def _candidate(turn: list[dict[str, Any]]) -> dict[str, Any]:
        # Same-sequence stabilized+final: keep the final wording.
        by_sequence: dict[int, dict[str, Any]] = {}
        for event in turn:
            seq = event.get("sequence") or 0
            if (
                seq not in by_sequence
                or event.get("kind") == "final"
            ):
                by_sequence[seq] = event
        ordered = [by_sequence[s] for s in sorted(by_sequence)]
        # STT emits stabilized then final wording at different sequence
        # numbers; drop consecutive duplicate texts within the turn.
        deduped: list[dict[str, Any]] = []
        for event in ordered:
            text = " ".join(
                str(event.get("text") or "").split()
            )
            prior = deduped[-1] if deduped else None
            prior_text = (
                " ".join(
                    str(prior.get("text") or "").split()
                )
                if prior
                else None
            )
            if text != prior_text:
                deduped.append(event)
        ordered = deduped
        text = " ".join(
            str(event.get("text") or "") for event in ordered
        ).strip()

        spans: list[dict[str, Any]] = []
        offset = 0
        for index, event in enumerate(ordered):
            length = len(str(event.get("text") or ""))
            if index:
                offset += 1  # the joining space
            spans.append(
                {
                    "event_id": event.get("event_id"),
                    "sequence": event.get("sequence") or 0,
                    "start_offset": offset,
                    "end_offset": offset + length,
                }
            )
            offset += length

        fingerprint = hashlib.sha256(
            text.encode("utf-8")
        ).hexdigest()[:16]
        return {
            "schema": "live_evidence.question_candidate.v1",
            "question_id": f"live_{fingerprint[:20]}",
            "normalized_question": text,
            "speaker": "interviewer",
            "source_event_ids": [
                str(event.get("event_id")) for event in ordered
            ],
            "source_spans": spans,
            "start_sequence": ordered[0].get("sequence") or 0,
            "end_sequence": ordered[-1].get("sequence") or 0,
            "trigger_reason": "interviewer_turn_final",
            "fingerprint": fingerprint,
        }

    def _handle_snapshot(self, snapshot: dict[str, Any]) -> list[dict[str, str]]:
        transcript = snapshot.get("transcript")
        if not isinstance(transcript, list):
            return []

        posted: list[dict[str, str]] = []
        for turn in self._closed_turns(transcript):
            candidate = self._candidate(turn)
            question_id = str(candidate["question_id"])
            with self._lock:
                if question_id in self._posted:
                    continue
                try:
                    result = self._session.intake_live_evidence(
                        {
                            "schema": INTAKE_SCHEMA,
                            "source": "live_evidence_live",
                            "candidate": candidate,
                            "source_fingerprint": candidate[
                                "fingerprint"
                            ],
                        }
                    )
                except ValidationError:
                    continue
                self._posted.add(question_id)
                posted.append(
                    {
                        "question_id": question_id,
                        "status": result.status,
                    }
                )
        return posted

    # -- SSE transport --------------------------------------------------

    def _iter_frames(
        self,
        max_frames: int,
        deadline_monotonic: float,
    ) -> Iterator[dict[str, Any]]:
        with httpx.stream(
            "GET",
            f"{self._base}/api/events",
            timeout=httpx.Timeout(
                connect=5.0, read=None, write=5.0, pool=5.0
            ),
        ) as response:
            response.raise_for_status()
            frames = 0
            for line in response.iter_lines():
                if time.monotonic() > deadline_monotonic:
                    return
                if not line.startswith("data: "):
                    continue
                payload = json.loads(line[len("data: "):])
                if isinstance(payload, dict):
                    frames += 1
                    yield payload
                    if frames >= max_frames:
                        return

    def stream_once(
        self,
        max_frames: int = 2,
        deadline_seconds: float = 8.0,
    ) -> list[dict[str, str]]:
        """Read up to ``max_frames`` snapshot frames; return posted turns.

        Never raises: transport failures degrade honestly.
        """
        try:
            posted: list[dict[str, str]] = []
            deadline = time.monotonic() + deadline_seconds
            for snapshot in self._iter_frames(max_frames, deadline):
                posted.extend(self._handle_snapshot(snapshot))
            self.consecutive_failures = 0
            self.last_success_monotonic = time.monotonic()
            return posted
        except (
            httpx.HTTPError,
            json.JSONDecodeError,
            ValueError,
            OSError,
        ):
            self.consecutive_failures += 1
            return []

    def run_forever(self) -> None:
        while True:
            self.stream_once(
                max_frames=10, deadline_seconds=30.0
            )
            time.sleep(self._reconnect_seconds)
