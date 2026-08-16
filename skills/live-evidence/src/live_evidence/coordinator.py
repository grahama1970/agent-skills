"""Transcript-to-evidence orchestration."""

from __future__ import annotations

import asyncio
from time import monotonic

from loguru import logger

from .config import AppSettings, InterviewProfile
from .models import (
    EvidenceCard,
    EvidenceSource,
    LaneState,
    ManualSearchRequest,
    RetrievalLane,
    SessionStatus,
    TranscriptEvent,
)
from .persistence import SessionJournal
from .retrieval import (
    AskSolutionClient,
    ExternalSkillClient,
    MemoryEvidenceClient,
    RipgrepEvidenceClient,
    rank_sources,
)
from .state import RuntimeState
from .summarizer import ExtractiveSummarizer
from .question_window import QuestionWindowBuilder, candidate_thread
from .trigger import TriggerDecision, is_code_question, tokenize


class EvidenceCoordinator:
    """Run bounded retrieval after accepted transcript triggers."""

    def __init__(
        self,
        settings: AppSettings,
        profile: InterviewProfile,
        state: RuntimeState,
        journal: SessionJournal,
    ) -> None:
        self._settings = settings
        self._profile = profile
        self._state = state
        self._journal = journal
        self._question_window = QuestionWindowBuilder(profile)
        self._memory = MemoryEvidenceClient(settings, profile)
        self._ripgrep = RipgrepEvidenceClient(settings, profile)
        self._external = ExternalSkillClient(settings)
        self._ask = AskSolutionClient(settings)
        self._summarizer = ExtractiveSummarizer()
        self._tasks: set[asyncio.Task[None]] = set()
        self._trigger_lock = asyncio.Lock()
        self._ask_lock = asyncio.Lock()
        self._last_auto_ask_key = ""
        self._last_auto_ask_at = 0.0
        self._auto_ask_cooldown_s = 120.0

    async def accept_transcript(self, event: TranscriptEvent) -> None:
        """Persist and project a transcript event, then schedule retrieval."""

        snapshot = await self._state.append_transcript(event)
        await self._journal.append(snapshot.session.session_id, "transcript", event)
        if self._state.session_status() is not SessionStatus.LISTENING:
            return
        outcome = self._question_window.ingest(event)
        if outcome.candidate is None or outcome.duplicate:
            return
        candidate = outcome.candidate
        decision = TriggerDecision(
            event_id=candidate.question_id,
            query=candidate.normalized_question,
            thread=candidate_thread(candidate, self._profile),
            reason=candidate.trigger_reason,
            code_related=is_code_question(candidate.normalized_question),
        )
        await self._state.set_thread(decision.thread)
        task = asyncio.create_task(self._retrieve(decision))
        self._tasks.add(task)
        task.add_done_callback(self._task_done)

    async def manual_search(self, request: ManualSearchRequest) -> EvidenceCard:
        """Run one explicit lane without exposing the full transcript."""

        thread = f"Manual · {request.lane.value}"
        await self._state.set_thread(thread)
        if request.lane in {RetrievalLane.BRAVE, RetrievalLane.DOGPILE}:
            await self._state.set_lane(request.lane, LaneState.RUNNING, "Manual search")
            result = await self._external.retrieve(request.lane, request.query)
            await self._state.set_lane(
                request.lane,
                LaneState.OK if result.ok else LaneState.DEGRADED,
                result.detail,
                latency_ms=result.latency_ms,
                result_count=len(result.sources),
            )
            sources = rank_sources(result.sources, request.query, self._profile)
        elif request.lane is RetrievalLane.RIPGREP:
            await self._state.set_lane(RetrievalLane.RIPGREP, LaneState.RUNNING, "Manual current-source search")
            result = await self._ripgrep.retrieve(request.query)
            await self._state.set_lane(
                RetrievalLane.RIPGREP,
                LaneState.OK if result.ok else LaneState.DEGRADED,
                result.detail,
                latency_ms=result.latency_ms,
                result_count=len(result.sources),
            )
            sources = rank_sources(result.sources, request.query, self._profile)
        elif request.lane is RetrievalLane.ASK:
            await self._state.set_lane(RetrievalLane.ASK, LaneState.RUNNING, "Manual Ask code solution")
            result = await self._ask.solve(request.query, [])
            await self._state.set_lane(
                RetrievalLane.ASK,
                LaneState.OK if result.ok else LaneState.DEGRADED,
                result.detail,
                latency_ms=result.latency_ms,
                result_count=len(result.sources),
            )
            sources = rank_sources(result.sources, request.query, self._profile)
        else:
            await self._state.set_lane(RetrievalLane.MEMORY, LaneState.RUNNING, "Manual memory search")
            result = await self._memory.retrieve(request.query)
            await self._state.set_lane(
                RetrievalLane.MEMORY,
                LaneState.OK if result.ok else LaneState.DEGRADED,
                result.detail,
                latency_ms=result.latency_ms,
                result_count=len(result.sources),
            )
            sources = rank_sources(result.sources, request.query, self._profile)
        card = self._summarizer.build(request.query, thread, sources)
        snapshot = await self._state.add_card(card)
        await self._journal.append(snapshot.session.session_id, "evidence_card", card)
        return card

    async def _retrieve(self, decision: TriggerDecision) -> None:
        if decision.code_related and not self._reserve_code_question(decision.query):
            await self._state.set_lane(
                RetrievalLane.ASK,
                LaneState.OK,
                "Duplicate code-question trigger suppressed",
            )
            return

        await self._state.set_lane(RetrievalLane.MEMORY, LaneState.RUNNING, decision.reason)
        await self._state.set_lane(RetrievalLane.CODE, LaneState.RUNNING, "Indexed code")
        await self._state.set_lane(RetrievalLane.RIPGREP, LaneState.RUNNING, "Current source")
        started = monotonic()
        memory_task = asyncio.create_task(self._memory.retrieve(decision.query))
        ripgrep_task = asyncio.create_task(self._ripgrep.retrieve(decision.query))

        sources: list[EvidenceSource] = []
        memory_result: object | None = None
        if decision.code_related:
            try:
                memory_result = await asyncio.wait_for(
                    asyncio.shield(memory_task),
                    timeout=min(0.75, self._settings.request_timeout_s),
                )
            except TimeoutError:
                await self._state.set_lane(
                    RetrievalLane.MEMORY,
                    LaneState.RUNNING,
                    "Optional Memory still running; showing current-source answer",
                )
                await self._state.set_lane(
                    RetrievalLane.CODE,
                    LaneState.RUNNING,
                    "Optional indexed code still running",
                )
            except Exception as exc:  # memory is optional for the live answer path
                memory_result = exc
        else:
            try:
                memory_result = await memory_task
            except Exception as exc:  # surfaced as explicit lane state below
                memory_result = exc

        if memory_result is not None:
            sources.extend(await self._apply_memory_result(memory_result))

        try:
            ripgrep_result = await ripgrep_task
        except Exception as exc:
            ripgrep_result = exc

        if isinstance(ripgrep_result, Exception):
            await self._state.set_lane(
                RetrievalLane.RIPGREP,
                LaneState.ERROR,
                f"Current-source error: {type(ripgrep_result).__name__}",
            )
        else:
            await self._state.set_lane(
                RetrievalLane.RIPGREP,
                LaneState.OK if ripgrep_result.ok else LaneState.DEGRADED,
                ripgrep_result.detail,
                latency_ms=ripgrep_result.latency_ms,
                result_count=len(ripgrep_result.sources),
            )
            sources.extend(ripgrep_result.sources)

        ranked = rank_sources(sources, decision.query, self._profile)
        ask_sources: list[EvidenceSource] = []
        if decision.code_related:
            await self._state.set_lane(RetrievalLane.ASK, LaneState.RUNNING, "Solving code question")
            async with self._ask_lock:
                ask_result = await self._ask.solve(decision.query, ranked[:4])
            await self._state.set_lane(
                RetrievalLane.ASK,
                LaneState.OK if ask_result.ok else LaneState.DEGRADED,
                ask_result.detail,
                latency_ms=ask_result.latency_ms,
                result_count=len(ask_result.sources),
            )
            ask_sources = ask_result.sources

        card_sources = _card_sources_for_decision(decision, ranked, ask_sources, self._profile)
        card = self._summarizer.build(decision.query, decision.thread, card_sources)
        snapshot = await self._state.add_card(card)
        await self._journal.append(snapshot.session.session_id, "evidence_card", card)
        logger.info(
            "evidence card status={} sources={} latency_ms={}",
            card.status.value,
            len(card.sources),
            int((monotonic() - started) * 1000),
        )
        if memory_result is None:
            try:
                late_memory_result = await memory_task
            except Exception as exc:
                late_memory_result = exc
            await self._apply_memory_result(late_memory_result)

    async def close(self) -> None:
        """Cancel unfinished retrieval tasks during service shutdown."""

        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    def _task_done(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception as exc:  # surfaced as lane error, service remains available
            logger.exception("background evidence retrieval failed: {}", exc)

    async def _apply_memory_result(self, memory_result: object) -> list[EvidenceSource]:
        """Project optional Memory/code result state and return any source evidence."""

        if isinstance(memory_result, Exception):
            await self._state.set_lane(
                RetrievalLane.MEMORY,
                LaneState.ERROR,
                f"Memory error: {type(memory_result).__name__}",
            )
            await self._state.set_lane(
                RetrievalLane.CODE,
                LaneState.ERROR,
                "Indexed code unavailable with Memory lane",
            )
            return []

        memory_sources = [
            source
            for source in memory_result.sources
            if source.lane is RetrievalLane.MEMORY
        ]
        await self._state.set_lane(
            RetrievalLane.MEMORY,
            LaneState.OK if memory_result.ok else LaneState.DEGRADED,
            memory_result.detail,
            latency_ms=memory_result.latency_ms,
            result_count=len(memory_sources),
        )
        code_sources = [
            source
            for source in memory_result.sources
            if source.lane is RetrievalLane.CODE
        ]
        await self._state.set_lane(
            RetrievalLane.CODE,
            LaneState.OK if code_sources else LaneState.DEGRADED,
            f"Indexed code {len(code_sources)}" if code_sources else "No indexed source",
            latency_ms=memory_result.latency_ms,
            result_count=len(code_sources),
        )
        return list(memory_result.sources)

    def _reserve_code_question(self, query: str) -> bool:
        key = _code_problem_key(query)
        now = monotonic()
        if key == self._last_auto_ask_key and now - self._last_auto_ask_at < self._auto_ask_cooldown_s:
            return False
        self._last_auto_ask_key = key
        self._last_auto_ask_at = now
        return True

def _code_problem_key(query: str) -> str:
    """Create a stable live-coding problem key from noisy growing STT text."""

    canon = {
        "parentheses": "parenthesis",
        "strings": "string",
        "removal": "remove",
    }
    terms = [
        canon.get(token.casefold(), token.casefold())
        for token in tokenize(query)
        if canon.get(token.casefold(), token.casefold())
        in {
            "minimum",
            "remove",
            "parenthesis",
            "valid",
            "string",
            "input",
            "output",
            "return",
            "opening",
            "closing",
        }
    ]
    term_set = set(terms)
    if {"valid", "string", "parenthesis", "minimum"} <= term_set:
        return "code:min-valid-parenthesis-string"

    selected: list[str] = []
    for term in terms:
        if term in selected:
            continue
        selected.append(term)
        if len(selected) == 6:
            break
    return "code:" + " ".join(selected) if selected else "code:" + " ".join(tokenize(query)[:8]).casefold()


def _card_sources_for_decision(
    decision: TriggerDecision,
    ranked_sources: list[EvidenceSource],
    ask_sources: list[EvidenceSource],
    profile: InterviewProfile,
) -> list[EvidenceSource]:
    """Prefer Ask receipts, but keep current-source evidence when Ask degrades."""

    if not decision.code_related:
        return ranked_sources
    return rank_sources([*ask_sources, *ranked_sources], decision.query, profile)
