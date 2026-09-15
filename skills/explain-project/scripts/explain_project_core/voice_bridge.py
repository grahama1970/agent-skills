"""Live-question bridge: poll the live-evidence service and post accepted
question candidates to cockpit intake.

Polls ``GET {EXPLAIN_PROJECT_LIVE_EVIDENCE_URL}/api/events`` for
``live_evidence.question_candidate.v1`` events, posts unseen candidates to
``CockpitSession.intake_live_evidence`` labeled ``live_evidence_live`` (with
the candidate fingerprint as the live source_fingerprint, which the strict
QuestionInput boundary requires), and degrades honestly when the service is
down: a failed poll touches no cockpit state, so manual input stays
functional.

The payload shape of ``GET /api/events`` is not pinned by a local
live-evidence checkout; this bridge accepts either a bare JSON list of
events or ``{"events": [...]}`` and skips anything that is not a
question candidate. Segmentation, VAD endpointing, and speaker attribution
stay owned by the live-evidence listener; this bridge only relays
already-authored candidates.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

CANDIDATE_SCHEMA = "live_evidence.question_candidate.v1"
INTAKE_SCHEMA = "explain_project.live_evidence_intake.v1"
DEFAULT_BASE_URL = "http://127.0.0.1:8799"
POLL_INTERVAL_SECONDS = 1.0
REQUEST_TIMEOUT_SECONDS = 2.0


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
    """Poll live-evidence for question candidates and post them to intake."""

    def __init__(
        self,
        session: Any,
        url: str | None = None,
        poll_interval: float = POLL_INTERVAL_SECONDS,
    ) -> None:
        self._session = session
        self._base = _base_url(url)
        self.poll_interval = poll_interval
        self._seen: set[str] = set()
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

    def _fetch_candidates(self) -> list[dict[str, Any]]:
        response = httpx.get(
            f"{self._base}/api/events",
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()

        events = (
            payload.get("events")
            if isinstance(payload, dict)
            else payload
        )
        if not isinstance(events, list):
            return []

        return [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("schema") == CANDIDATE_SCHEMA
        ]

    def poll_once(self) -> list[dict[str, str]]:
        """One poll cycle. Returns posted candidates; never raises."""
        try:
            candidates = self._fetch_candidates()
        except (
            httpx.HTTPError,
            ValueError,
            OSError,
        ):
            # Honest degradation: no cockpit state is touched and
            # manual input remains fully functional.
            self.consecutive_failures += 1
            return []

        self.consecutive_failures = 0
        self.last_success_monotonic = time.monotonic()

        posted: list[dict[str, str]] = []
        for candidate in candidates:
            question_id = str(candidate.get("question_id") or "")
            fingerprint = str(candidate.get("fingerprint") or "")
            if not question_id or not fingerprint:
                continue

            with self._lock:
                if question_id in self._seen:
                    continue

                try:
                    result = self._session.intake_live_evidence(
                        {
                            "schema": INTAKE_SCHEMA,
                            "source": "live_evidence_live",
                            "candidate": candidate,
                            "source_fingerprint": fingerprint,
                        }
                    )
                except ValidationError:
                    # Malformed candidate: skip, do not crash the loop.
                    continue

                self._seen.add(question_id)
                posted.append(
                    {
                        "question_id": question_id,
                        "status": result.status,
                    }
                )

        return posted

    def run_forever(self) -> None:
        while True:
            self.poll_once()
            time.sleep(self.poll_interval)
