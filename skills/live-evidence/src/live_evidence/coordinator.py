"""Transcript-to-evidence orchestration."""

from __future__ import annotations

import asyncio
from time import monotonic

from loguru import logger

from .config import AppSettings, InterviewProfile
from .models import (
    ClarificationItem,
    EvidenceCard,
    EvidenceSource,
    LaneState,
    ManualSearchRequest,
    RetrievalLane,
    SessionStatus,
    TranscriptEvent,
)
from .readiness import ReadinessVerdict
from .resolver import GateEvent, StreamingResolver
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
from .trigger import TriggerDecision


class EvidenceCoordinator:
    """Run bounded retrieval after accepted transcript triggers."""

    def __init__(
        self,
        settings: AppSettings,
        profile: InterviewProfile,
        state: RuntimeState,
        journal: SessionJournal,
    ) -> None:
        self._profile = profile
        self._state = state
        self._journal = journal
        self._question_window = QuestionWindowBuilder(profile)
        self._memory = MemoryEvidenceClient(settings, profile)
        self._ripgrep = RipgrepEvidenceClient(settings, profile)
        self._external = ExternalSkillClient(settings)
        self._ask = AskSolutionClient(settings)
        self._summarizer = ExtractiveSummarizer()
        self._resolver = StreamingResolver()
        self._tasks: set[asyncio.Task[None]] = set()

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
        )
        # Claim the revision this retrieval answers BEFORE dispatching it. A
        # later turn bumps the revision, so a slow result can be recognised as
        # stale at publication time instead of overwriting a newer answer.
        question_id, question_revision = await self._state.revise_question(decision.query)
        await self._state.set_thread(decision.thread)
        task = asyncio.create_task(self._retrieve(decision, question_id, question_revision))
        self._tasks.add(task)
        task.add_done_callback(self._task_done)

    async def _resolve_readiness(self, query: str) -> ReadinessVerdict | None:
        """Run the stage-1 gate, surfacing the decision as soon as it streams.

        The resolver is a blocking HTTP client, so it runs off the event loop.
        The gate arrives in the first content delta and is logged the moment it
        does; the remaining clarification text follows about 1.3s later, which
        is latency the HUD does not have to wait for.

        Returns None on any resolver failure. Callers must treat None as "not
        ready": an unreachable or unparseable resolver must never read as
        permission to answer.
        """

        def run() -> tuple[GateEvent | None, ReadinessVerdict | None, str | None, float | None]:
            gate: GateEvent | None = None
            for event in self._resolver.stream(query):
                if isinstance(event, GateEvent):
                    gate = event
                    continue
                return gate, event.verdict, event.error, event.total_elapsed_s
            return gate, None, "resolver_produced_no_outcome", None

        try:
            gate, verdict, error, total_s = await asyncio.to_thread(run)
        except Exception as exc:  # pragma: no cover - defensive, fail closed
            import traceback

            logger.warning(
                "stage1 resolver raised {}: {}\n{}",
                type(exc).__name__,
                exc,
                traceback.format_exc(),
            )
            return None

        if gate is not None:
            logger.info(
                "stage1 gate ready={} reason={} type={} at {:.2f}s",
                gate.ready_to_answer,
                gate.blocking_reason,
                gate.question_type,
                gate.elapsed_s,
            )
        if error is not None or verdict is None:
            logger.warning("stage1 resolver unusable error={} (treating as not ready)", error)
            return None
        logger.info(
            "stage1 verdict may_ask={} clarifications={} total={:.2f}s",
            verdict.may_invoke_ask,
            len(verdict.clarifying_questions),
            total_s or 0.0,
        )
        return verdict

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

    async def _retrieve(
        self,
        decision: TriggerDecision,
        question_id: str,
        question_revision: int,
    ) -> None:
        await self._state.set_lane(RetrievalLane.MEMORY, LaneState.RUNNING, decision.reason)
        await self._state.set_lane(RetrievalLane.CODE, LaneState.RUNNING, "Indexed code")
        await self._state.set_lane(RetrievalLane.RIPGREP, LaneState.RUNNING, "Current source")
        started = monotonic()
        memory_result, ripgrep_result = await asyncio.gather(
            self._memory.retrieve(decision.query),
            self._ripgrep.retrieve(decision.query),
            return_exceptions=True,
        )

        sources: list[EvidenceSource] = []
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
        else:
            await self._state.set_lane(
                RetrievalLane.MEMORY,
                LaneState.OK if memory_result.ok else LaneState.DEGRADED,
                memory_result.detail,
                latency_ms=memory_result.latency_ms,
                result_count=len(
                    [
                        source
                        for source in memory_result.sources
                        if source.lane is RetrievalLane.MEMORY
                    ]
                ),
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
            sources.extend(memory_result.sources)

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

        # Stage 1: decide whether a legitimate, COMPLETE question has been asked
        # yet. This replaces routing on whether local code evidence happened to
        # exist, which fired on any turn that retrieved incidental code and
        # missed real questions with no local match.
        verdict = await self._resolve_readiness(decision.query)

        # When the resolver is unreachable or unconfigured we cannot judge
        # readiness at all, which is different from judging "not ready". Falling
        # back to the legacy predicate keeps local/offline runs working instead
        # of silently disabling the Ask lane whenever SciLLM is absent.
        may_ask = (
            verdict.may_invoke_ask
            if verdict is not None
            else _should_solve_with_ask(decision.query, ranked)
        )

        if may_ask:
            await self._state.set_lane(RetrievalLane.ASK, LaneState.RUNNING, "Solving code question")
            ask_result = await self._ask.solve(decision.query, ranked[:4])
            await self._state.set_lane(
                RetrievalLane.ASK,
                LaneState.OK if ask_result.ok else LaneState.DEGRADED,
                ask_result.detail,
                latency_ms=ask_result.latency_ms,
                result_count=len(ask_result.sources),
            )
            ranked = rank_sources([*sources, *ask_result.sources], decision.query, self._profile)
        elif verdict is not None:
            # A judged "not ready" holds the solver back and says why, so the
            # HUD never shows a confident answer to a truncated question.
            await self._state.set_lane(
                RetrievalLane.ASK,
                LaneState.IDLE,
                f"Holding: {verdict.blocking_reason}",
            )

        card = self._summarizer.build(decision.query, decision.thread, ranked)
        if verdict is not None and verdict.clarifying_questions:
            card = card.model_copy(
                update={
                    "clarifications": [
                        ClarificationItem(
                            id=item.id,
                            question=item.question,
                            why_it_matters=item.why_it_matters,
                            default_assumption=item.default_assumption,
                            blocking=item.blocking,
                        )
                        for item in verdict.clarifying_questions
                    ]
                }
            )
        card = card.model_copy(
            update={"question_id": question_id, "question_revision": question_revision}
        )
        snapshot = await self._state.publish_card_fenced(card)
        if snapshot is None:
            # The question moved on while this ran. Keep the work as an audit
            # event rather than discarding it silently, and never let it reach
            # the active card.
            await self._journal.append(
                self._state.session_id(),
                "evidence_card_discarded_stale_revision",
                card,
            )
            logger.info(
                "discarded stale result question_id={} revision={} latency_ms={}",
                question_id,
                question_revision,
                int((monotonic() - started) * 1000),
            )
            return
        await self._journal.append(snapshot.session.session_id, "evidence_card", card)
        logger.info(
            "evidence card status={} sources={} revision={} latency_ms={}",
            card.status.value,
            len(card.sources),
            question_revision,
            int((monotonic() - started) * 1000),
        )

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
        except Exception as exc:  # surfaced as lane error, service remains available
            logger.exception("background evidence retrieval failed: {}", exc)


def _should_solve_with_ask(query: str, sources: list[EvidenceSource]) -> bool:
    """Deprecated: routed on incidental retrieval rather than on the question.

    Kept only so existing callers and tests keep importing a defined symbol.
    The live path now gates on the stage-1 resolver verdict
    (ReadinessVerdict.may_invoke_ask), because this predicate fired whenever a
    turn happened to retrieve any code and stayed silent for genuine code
    questions with no local match. It never inspected the query at all.
    """

    has_local_code_evidence = any(
        source.lane in {RetrievalLane.CODE, RetrievalLane.RIPGREP} for source in sources
    )
    return has_local_code_evidence
