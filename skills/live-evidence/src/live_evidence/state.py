"""Concurrent runtime state and Server-Sent Event projection."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import timezone

from .config import AppSettings, InterviewProfile
from .models import (
    AppSnapshot,
    EvidenceCard,
    LaneActivity,
    LaneState,
    RetrievalLane,
    SessionInfo,
    SessionStatus,
    TranscriptEvent,
    utc_now,
)
from .transcript_dedupe import is_progressive_restatement, richer_transcript_event


class RuntimeState:
    """Own the mutable in-process projection used by the API and UI."""

    def __init__(self, settings: AppSettings, profile: InterviewProfile) -> None:
        self._settings = settings
        self._profile = profile
        self._lock = asyncio.Lock()
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._session = SessionInfo(profile_name=profile.name)
        self._thread = "Waiting for the conversation"
        self._transcript: list[TranscriptEvent] = []
        self._cards: list[EvidenceCard] = []
        self._lanes = self._initial_lanes()

    async def snapshot(self) -> AppSnapshot:
        """Return an immutable validated UI projection."""

        async with self._lock:
            return self._snapshot_unlocked()

    async def start_session(self, consent_confirmed: bool) -> AppSnapshot:
        """Start or restart a session."""

        async with self._lock:
            if self._session.status is SessionStatus.PAUSED:
                self._session.status = SessionStatus.LISTENING
                self._session.consent_confirmed = (
                    self._session.consent_confirmed or consent_confirmed
                )
            elif self._session.status is SessionStatus.LISTENING:
                self._session.consent_confirmed = (
                    self._session.consent_confirmed or consent_confirmed
                )
            else:
                self._session = SessionInfo(
                    status=SessionStatus.LISTENING,
                    started_at=utc_now(),
                    consent_confirmed=consent_confirmed,
                    profile_name=self._profile.name,
                )
                self._thread = "Waiting for the conversation"
                self._transcript = []
                self._cards = []
                self._lanes = self._initial_lanes()
            snapshot = self._snapshot_unlocked()
        await self._broadcast(snapshot)
        return snapshot

    async def pause_session(self) -> AppSnapshot:
        """Pause automatic retrieval while preserving the transcript."""

        async with self._lock:
            self._session.status = SessionStatus.PAUSED
            snapshot = self._snapshot_unlocked()
        await self._broadcast(snapshot)
        return snapshot

    async def stop_session(self) -> AppSnapshot:
        """Stop the session and retain its final projection."""

        async with self._lock:
            self._session.status = SessionStatus.STOPPED
            self._session.stopped_at = utc_now()
            snapshot = self._snapshot_unlocked()
        await self._broadcast(snapshot)
        return snapshot

    async def append_transcript(self, event: TranscriptEvent) -> AppSnapshot:
        """Append or replace one interim event and broadcast state."""

        async with self._lock:
            if event.kind.value == "interim":
                self._transcript = [
                    item
                    for item in self._transcript
                    if not (
                        item.kind.value == "interim"
                        and item.speaker is event.speaker
                        and item.source is event.source
                    )
                ]
            elif event.kind.value in {"stabilized", "final"}:
                self._transcript = [
                    item
                    for item in self._transcript
                    if not (
                        item.kind.value == "interim"
                        and item.speaker is event.speaker
                        and item.source is event.source
                    )
                ]
            replaced = False
            for index, item in enumerate(self._transcript):
                if item.event_id != event.event_id:
                    continue
                self._transcript[index] = event
                replaced = True
                break
            if not replaced and event.kind.value in {"stabilized", "final"}:
                for index in range(len(self._transcript) - 1, -1, -1):
                    item = self._transcript[index]
                    if not is_progressive_restatement(item, event):
                        continue
                    self._transcript[index] = richer_transcript_event(item, event)
                    replaced = True
                    break
            if not replaced:
                self._transcript.append(event)
            self._transcript = self._transcript[-self._settings.max_transcript_events :]
            snapshot = self._snapshot_unlocked()
        await self._broadcast(snapshot)
        return snapshot

    async def set_thread(self, thread: str) -> None:
        """Update the glanceable current-thread label."""

        async with self._lock:
            self._thread = thread
            snapshot = self._snapshot_unlocked()
        await self._broadcast(snapshot)

    async def set_lane(
        self,
        lane: RetrievalLane,
        state: LaneState,
        detail: str,
        *,
        latency_ms: int | None = None,
        result_count: int = 0,
    ) -> None:
        """Record lane progress without converting degradation into success."""

        async with self._lock:
            self._lanes[lane] = LaneActivity(
                lane=lane,
                state=state,
                detail=detail[:300],
                latency_ms=latency_ms,
                result_count=result_count,
                updated_at=utc_now(),
            )
            snapshot = self._snapshot_unlocked()
        await self._broadcast(snapshot)

    async def add_card(self, card: EvidenceCard) -> AppSnapshot:
        """Add a new card, preserving pinned cards when trimming history."""

        async with self._lock:
            self._cards.insert(0, card)
            if len(self._cards) > self._settings.max_cards:
                pinned = [item for item in self._cards if item.pinned]
                unpinned = [item for item in self._cards if not item.pinned]
                self._cards = (pinned + unpinned)[: self._settings.max_cards]
            snapshot = self._snapshot_unlocked()
        await self._broadcast(snapshot)
        return snapshot

    async def set_card_flag(
        self,
        card_id: str,
        *,
        pinned: bool | None = None,
        dismissed: bool | None = None,
    ) -> AppSnapshot:
        """Update user-controlled card flags."""

        async with self._lock:
            found = False
            for card in self._cards:
                if card.card_id != card_id:
                    continue
                found = True
                if pinned is not None:
                    card.pinned = pinned
                if dismissed is not None:
                    card.dismissed = dismissed
                break
            if not found:
                raise KeyError(f"card not found: {card_id}")
            snapshot = self._snapshot_unlocked()
        await self._broadcast(snapshot)
        return snapshot

    async def events(self) -> AsyncIterator[str]:
        """Yield initial and subsequent snapshots as SSE data frames."""

        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=3)
        self._subscribers.add(queue)
        initial = await self.snapshot()
        await queue.put(initial.model_dump_json())
        try:
            while True:
                payload = await queue.get()
                yield f"event: snapshot\ndata: {payload}\n\n"
        finally:
            self._subscribers.discard(queue)

    def session_status(self) -> SessionStatus:
        """Return the current status for low-cost coordinator routing."""

        return self._session.status

    def _initial_lanes(self) -> dict[RetrievalLane, LaneActivity]:
        """Create the truthful initial state for every retrieval lane."""

        lanes: dict[RetrievalLane, LaneActivity] = {}
        for lane in RetrievalLane:
            runner_ready = (
                self._settings.brave_runner is not None
                if lane is RetrievalLane.BRAVE
                else self._settings.dogpile_runner is not None
                if lane is RetrievalLane.DOGPILE
                else self._settings.ask_runner is not None
                if lane is RetrievalLane.ASK
                else True
            )
            is_external = lane in {RetrievalLane.BRAVE, RetrievalLane.DOGPILE}
            is_ask = lane is RetrievalLane.ASK
            lanes[lane] = LaneActivity(
                lane=lane,
                state=(LaneState.IDLE if runner_ready else LaneState.DISABLED),
                detail=(
                    "Manual only"
                    if is_external and runner_ready
                    else "Code-question solver"
                    if is_ask and runner_ready
                    else "Ask runner not configured"
                    if is_ask
                    else "Runner not configured"
                    if is_external
                    else "Waiting"
                ),
            )
        return lanes

    def _snapshot_unlocked(self) -> AppSnapshot:
        return AppSnapshot(
            session=self._session.model_copy(deep=True),
            current_thread=self._thread,
            transcript=[item.model_copy(deep=True) for item in self._transcript],
            cards=[item.model_copy(deep=True) for item in self._cards],
            lanes=[self._lanes[lane].model_copy(deep=True) for lane in RetrievalLane],
            external_search_enabled=bool(
                self._settings.brave_runner or self._settings.dogpile_runner
            ),
            updated_at=utc_now().astimezone(timezone.utc),
        )

    async def _broadcast(self, snapshot: AppSnapshot) -> None:
        payload = snapshot.model_dump_json()
        stale: list[asyncio.Queue[str]] = []
        for queue in self._subscribers:
            try:
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(payload)
            except (asyncio.QueueFull, asyncio.QueueEmpty):
                stale.append(queue)
        for queue in stale:
            self._subscribers.discard(queue)
