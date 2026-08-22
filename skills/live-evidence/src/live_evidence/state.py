"""Concurrent runtime state and Server-Sent Event projection."""

from __future__ import annotations

import asyncio
from uuid import uuid4
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
    ActorRole,
    CapabilityPolicy,
    DEFAULT_POLICIES,
    SessionPurpose,
    policy_digest,
    AnswerSource,
    Requirement,
    RequirementStatus,
    ledger_digest,
)
from .transcript_dedupe import is_progressive_restatement, richer_transcript_event


def _status_for_session(consent_confirmed: bool, policy: CapabilityPolicy) -> SessionStatus:
    """Never report LISTENING for a session that may not capture audio.

    Two independent gates: consent (the human agreed) and the frozen policy's
    capture_audio capability (this session KIND is allowed to capture --
    post_interview_review, for example, is post-hoc and never listens). Either
    one absent keeps the session ARMED, and the coordinator refuses retrieval
    for any non-LISTENING session.
    """

    if consent_confirmed and policy.capture_audio:
        return SessionStatus.LISTENING
    return SessionStatus.ARMED


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
        # Single active question. Retrieval plus a solver call runs for tens of
        # seconds, which is long enough for speech to change the question
        # underneath it, so every answer is fenced against the revision that
        # asked for it.
        self._active_question_id: str | None = None
        self._question_last_revision: dict[str, int] = {}
        self._active_question_text: str = ""
        self._active_question_revision: int = 0
        self._active_question_answered: bool = False
        # Requirement ledger per (question_id, revision), append-only (#1454).
        self._ledger: dict[tuple[str, int], list[Requirement]] = {}

    async def snapshot(self) -> AppSnapshot:
        """Return an immutable validated UI projection."""

        async with self._lock:
            return self._snapshot_unlocked()

    async def start_session(
        self,
        consent_confirmed: bool,
        purpose: SessionPurpose = SessionPurpose.MEETING,
        actor_role: ActorRole = ActorRole.PARTICIPANT,
        policy: CapabilityPolicy | None = None,
    ) -> AppSnapshot:
        """Start or restart a session under a frozen capability policy (#1449).

        Purpose, actor role, and policy are bound into a digest at start.
        Requesting a DIFFERENT identity after transcript activity begins does
        not widen the running session: it allocates a new session id, so a UI
        toggle can never silently upgrade a formal assessment into a coached
        one. Consent remains a separate, prior gate that policy supplements.
        """

        resolved_policy = policy or DEFAULT_POLICIES[purpose]
        digest = policy_digest(purpose, actor_role, resolved_policy)

        def fresh_session() -> SessionInfo:
            return SessionInfo(
                status=_status_for_session(consent_confirmed, resolved_policy),
                started_at=utc_now(),
                consent_confirmed=consent_confirmed,
                profile_name=self._profile.name,
                purpose=purpose,
                actor_role=actor_role,
                policy=resolved_policy,
                policy_digest=digest,
                practice_only=purpose is SessionPurpose.REHEARSAL,
            )

        async with self._lock:
            same_identity = self._session.policy_digest == digest
            active = self._session.status in (
                SessionStatus.PAUSED,
                SessionStatus.LISTENING,
                SessionStatus.ARMED,
            )
            if active and same_identity:
                self._session.consent_confirmed = (
                    self._session.consent_confirmed or consent_confirmed
                )
                self._session.status = _status_for_session(
                    self._session.consent_confirmed, self._session.policy
                )
            else:
                # Different identity (or idle/stopped): new session. Activity
                # under the old identity stays bound to the old session id.
                self._session = fresh_session()
                self._thread = "Waiting for the conversation"
                self._transcript = []
                self._cards = []
                self._lanes = self._initial_lanes()
                self._active_question_id = None
                self._active_question_revision = 0
                self._active_question_answered = False
            snapshot = self._snapshot_unlocked()
        await self._broadcast(snapshot)
        return snapshot

    def session_policy(self) -> CapabilityPolicy:
        """Frozen capability policy for coordinator/API enforcement."""

        return self._session.policy

    async def reassign_turn(self, turn_id: str, speaker_slot: str) -> int:
        """Manual speaker-slot correction (#1477): presentation-level only --
        semantic content, cards, ledger, and coverage are untouched."""

        async with self._lock:
            count = 0
            for index, item in enumerate(self._transcript):
                if item.turn_id == turn_id:
                    self._transcript[index] = item.model_copy(update={
                        "speaker_slot": speaker_slot,
                        "attribution_source": "manual",
                        "attribution_confidence": 1.0,
                    })
                    count += 1
            snapshot = self._snapshot_unlocked()
        await self._broadcast(snapshot)
        return count

    def active_question(self) -> str | None:
        return self._active_question_id

    def active_question_revision(self) -> int:
        return self._active_question_revision

    def session_purpose(self):
        return self._session.purpose

    def session_policy_digest(self) -> str:
        return self._session.policy_digest

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
                # (#1477) deterministic turn assignment: consecutive events
                # from the same speaker share a turn; a speaker change opens a
                # new one. Replacements/restatements above inherit the original
                # event's turn, so turn ids are stable across revisions.
                if event.turn_id is None:
                    last = self._transcript[-1] if self._transcript else None
                    if last is not None and last.speaker == event.speaker and last.turn_id:
                        event = event.model_copy(update={
                            "turn_id": last.turn_id,
                            "speaker_slot": last.speaker_slot,
                        })
                    else:
                        slots = {item.speaker: item.speaker_slot
                                 for item in self._transcript if item.speaker_slot}
                        slot = slots.get(event.speaker) or f"speaker_{len(set(slots.values()))}"
                        from uuid import uuid4 as _uuid4

                        event = event.model_copy(update={
                            "turn_id": _uuid4().hex,
                            "speaker_slot": slot,
                        })
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

    async def open_ledger(self, question_id: str, revision: int, entries: list[Requirement]) -> str:
        """Open the requirement ledger for one question revision (#1454).

        Append-only: opening a newer revision leaves prior revisions intact,
        so nothing ever edits a prior ledger state. Returns the digest.
        """

        async with self._lock:
            self._ledger[(question_id, revision)] = list(entries)
            return ledger_digest(self._ledger[(question_id, revision)])

    async def ledger_entries(self, question_id: str, revision: int) -> list[Requirement]:
        async with self._lock:
            return list(self._ledger.get((question_id, revision), []))

    async def blocking_unresolved(self, question_id: str, revision: int) -> list[Requirement]:
        async with self._lock:
            return [
                entry
                for entry in self._ledger.get((question_id, revision), [])
                if entry.blocking and entry.status is RequirementStatus.UNRESOLVED
            ]

    async def amend_requirement(
        self,
        question_id: str,
        revision: int,
        clarification_id: str,
        answer: str,
        source: AnswerSource,
        answer_event_ids: list[str],
    ) -> tuple[str, Requirement | None]:
        """Bind one clarification answer, append-only, revision-fenced.

        Returns (result, entry): result is "amended", "duplicate",
        "stale_revision", or "unknown_clarification". A duplicate answer is
        idempotent -- it never creates a second amendment or re-triggers solver
        work. An answer for a stale or different revision is rejected: an
        answer given about revision N must not amend the ledger of N+1.
        """

        async with self._lock:
            if (question_id, revision) not in self._ledger:
                if self._active_question_id == question_id:
                    return "stale_revision", None
                return "unknown_clarification", None
            entries = self._ledger[(question_id, revision)]
            target = next(
                (e for e in entries if e.clarification_id == clarification_id), None
            )
            if target is None:
                return "unknown_clarification", None
            if target.status is RequirementStatus.CLARIFIED:
                return "duplicate", target
            amended = target.model_copy(
                update={
                    "status": RequirementStatus.CLARIFIED,
                    "clarification_answer": answer[:1_000],
                    "answer_source": source,
                    "clarification_answer_event_ids": answer_event_ids[:8],
                }
            )
            # Append-only: the amended entry supersedes in place-position, but
            # the prior state remains recoverable through the journal.
            entries[entries.index(target)] = amended
            return "amended", amended

    async def revise_question(self, normalized_question: str) -> tuple[str, int]:
        """Open or revise the single active question, returning (id, revision).

        Single-active-question invariant with an explicit close condition:

        - A candidate arriving while the active question is still UNANSWERED is
          treated as a correction and bumps its revision. That is the case the
          fence exists for: the speaker restated or added a constraint while
          retrieval was still running.
        - Once a question has been answered, the next candidate opens a NEW
          question id. Otherwise every question in a session collapses into one
          record and each answered card is evicted by the next turn.
        - A candidate that shares almost no content vocabulary with the active
          question is a DIFFERENT question, not a correction, even while the
          active one is unanswered. Without this fork, a meeting that moves to
          its next question before the previous answer lands absorbs the new
          topic as a revision and the previous question's only completed card
          is fenced out as stale (observed live in the Sparta campaign: the
          hard-rules answer was discarded because the version question had
          become revision 3 of the same question id).

        The fork test is deterministic token overlap on the resolver's
        canonical question text; probabilistic thread identity stays out of
        scope.
        """

        def _content_words(text: str) -> set[str]:
            return {w for w in "".join(
                c if c.isalnum() else " " for c in text.lower()
            ).split() if len(w) > 3}

        async with self._lock:
            fork = False
            if self._active_question_id and not self._active_question_answered:
                prior = _content_words(self._active_question_text)
                new = _content_words(normalized_question)
                if prior and new:
                    overlap = len(prior & new) / min(len(prior), len(new))
                    fork = overlap < 0.3
            if (
                self._active_question_id is None
                or self._active_question_answered
                or fork
            ):
                self._active_question_id = uuid4().hex
                self._active_question_revision = 1
                self._active_question_answered = False
            else:
                self._active_question_revision += 1
            self._active_question_text = normalized_question
            self._question_last_revision[self._active_question_id] = (
                self._active_question_revision
            )
            return self._active_question_id, self._active_question_revision

    async def close_question(self) -> None:
        """Retire the active question so the next candidate allocates a new id."""

        async with self._lock:
            self._active_question_id = None
            self._active_question_revision = 0
            self._active_question_answered = False

    async def publish_card_fenced(self, card: EvidenceCard) -> AppSnapshot | None:
        """Publish only if the card still answers the current question revision.

        Compare-and-swap, not last-writer-wins: a solver that started against
        revision N must not overwrite a card belonging to revision N+1 merely
        because it finished later. Returns None when the result is stale, and
        callers must treat None as "discarded" rather than ignoring it.

        Fails closed: a card carrying no question identity, or arriving after the
        question was closed, is discarded rather than published.
        """

        async with self._lock:
            if card.question_id is None:
                return None
            if card.question_id != self._active_question_id:
                # A finished answer for an EARLIER question that was never
                # superseded within its own revisions still publishes -- as a
                # background card, without reclaiming the active slot. In a
                # fast multi-question meeting the next question must not
                # destroy the previous question's completed answer (observed
                # live: the Sparta campaign's memory answer was discarded
                # because the research question had taken the slot).
                # For a background question the newest COMPLETED answer wins.
                # Requiring the question's very last authored revision was too
                # strict: a cumulative-window question keeps revising until the
                # next question takes the slot, and the only revision whose
                # solve ever completes may be an earlier one (observed live:
                # the hard-rules card was authored at rev 1, discarded because
                # the question had reached rev 4 with no rev-4 solve). The
                # fence's real job is only that an OLDER completed card never
                # replaces a NEWER displayed card for the same question.
                displayed = next(
                    (item for item in self._cards
                     if item.question_id == card.question_id), None,
                )
                if displayed is None or (
                    (displayed.question_revision or 0)
                    <= (card.question_revision or 0)
                ):
                    self._cards = [
                        item for item in self._cards
                        if item.question_id != card.question_id
                    ]
                    self._cards.insert(min(1, len(self._cards)), card)
                    self._cards = self._cards[: self._settings.max_cards]
                    snapshot = self._snapshot_unlocked()
                else:
                    return None
                # fall through to broadcast outside the lock
                background = True
            elif card.question_revision != self._active_question_revision:
                # Older-revision completed answer for the ACTIVE question: the
                # fence's job is that a slower rev-N solve never overwrites a
                # DISPLAYED rev-N+1 card -- not that a completed answer loses
                # to an empty slot because a later turn claimed the revision
                # while this solve was in flight (observed live: rev 3's
                # hard-rules card discarded because rev 4 had claimed and not
                # yet solved). Newest completed card wins; a newer revision's
                # card supersedes it on arrival.
                displayed = next(
                    (item for item in self._cards
                     if item.question_id == card.question_id), None,
                )
                if displayed is not None and (
                    (displayed.question_revision or 0)
                    > (card.question_revision or 0)
                ):
                    return None
                if (card.question_revision or 0) > self._active_question_revision:
                    return None
                background = False
            else:
                background = False
            if not background:
                # Exactly one active card per question_id: a revision supersedes
                # the previous answer in place instead of growing the stream.
                self._cards = [
                    item for item in self._cards if item.question_id != card.question_id
                ]
                self._cards.insert(0, card)
            if not background:
                if len(self._cards) > self._settings.max_cards:
                    pinned = [item for item in self._cards if item.pinned]
                    unpinned = [item for item in self._cards if not item.pinned]
                    self._cards = (pinned + unpinned)[: self._settings.max_cards]
                # Answered: the next candidate opens a new question rather than
                # revising this one and evicting the card just published.
                self._active_question_answered = True
            snapshot = self._snapshot_unlocked()
        await self._broadcast(snapshot)
        return snapshot

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

    def session_id(self) -> str:
        """Return the current session id for journalling outside a snapshot.

        The stale-result path has no published snapshot to read the id from, and
        that path must still be journalled rather than dropped.
        """

        return self._session.session_id

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
