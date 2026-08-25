"""Transcript-to-evidence orchestration."""

from __future__ import annotations

import asyncio
from time import monotonic

from loguru import logger

from .config import AppSettings, InterviewProfile
from .code_context import current_source_query_from_memory
from .models import (
    ClarificationItem,
    EvidenceCard,
    EvidenceSource,
    LaneState,
    ManualSearchRequest,
    RetrievalLane,
    SessionStatus,
    TranscriptEvent,
    AnswerSource,
    Requirement,
    RequirementKind,
    RequirementStatus,
    ledger_digest,
)
from .readiness import ReadinessVerdict
from .echo import strip_assistant_echo
from .fast_path import stream_fast_answer
from .solver import FastSolver
from .resolver import GateEvent, StreamingResolver
from .requirement_ledger import build_requirement_entries
from .salient_facts import SalientFactWriter, extract_decision
from .persistence import SessionJournal
from .retrieval import (
    AskSolutionClient,
    ExternalSkillClient,
    is_code_location_query,
    MemoryEvidenceClient,
    RipgrepEvidenceClient,
    rank_sources,
)
from .state import RuntimeState
from .summarizer import ExtractiveSummarizer
from .surface_selector import SurfaceSelector
from .surface_policy import should_force_surface_source_backed_code
from .question_window import QuestionWindowBuilder, candidate_thread
from .query_bounds import bounded_query
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
        self.journal = journal  # public handle for API routes (#1450)
        self.settings = settings  # public: action lane memory_url (#1475)
        self.actions = None  # ActionEngine, lazily bound to the session policy
        self.briefing = None  # BriefingMatcher when a pack is loaded
        # Repo basenames this meeting is about; feeds memory project-affinity.
        self._repo_scope = {p.name.casefold() for p in settings.repo_roots}
        self._question_window = QuestionWindowBuilder(profile)
        self._memory = MemoryEvidenceClient(settings, profile)
        self._ripgrep = RipgrepEvidenceClient(settings, profile)
        self._external = ExternalSkillClient(settings)
        self._ask = AskSolutionClient(settings)
        self._summarizer = ExtractiveSummarizer()
        self._selector = SurfaceSelector()
        self._resolver = StreamingResolver()
        self._facts = SalientFactWriter(settings.memory_url)
        self._tasks: set[asyncio.Task[None]] = set()
        # (#1454) at-most-once solver per revision, plus held retrieval context
        # for blocked questions so an amendment continues without re-retrieving.
        self._solved_revisions: set[tuple[str, int]] = set()
        self._held: dict[tuple[str, int], dict] = {}
        # Text the assistant is speaking (#1453): the mic hears our own TTS as
        # "interviewer"; matching events are journaled as echo, not questions.
        self._assistant_utterances: list[str] = []

    async def accept_transcript(self, event: TranscriptEvent) -> None:
        """Persist and project a transcript event, then schedule retrieval."""

        snapshot = await self._state.append_transcript(event)
        digest = self._state.session_policy_digest()
        await self._journal.append(
            snapshot.session.session_id, "transcript", event, policy_digest=digest
        )
        if self._state.session_status() is not SessionStatus.LISTENING:
            return
        policy = self._state.session_policy()
        # Salient-fact capture runs beside question handling: its durable write
        # must not block or join the revision-fenced card path.
        fact = extract_decision(event, self._state.session_id()) if policy.retain_transcript else None
        if fact is not None:
            fact_task = asyncio.create_task(self._write_salient_fact(fact))
            self._tasks.add(fact_task)
            fact_task.add_done_callback(self._task_done)
        if not policy.retrieve_local_evidence:
            return
        stripped = self._strip_assistant_echo(event.text)
        if len(stripped) != len(event.text):
            await self._journal.append(
                self._state.session_id(), "assistant_echo_redacted",
                {"event_id": event.event_id, "before_chars": len(event.text),
                 "after_chars": len(stripped)},
                policy_digest=self._state.session_policy_digest(),
            )
            if len(stripped.split()) < 4:
                return
            event = event.model_copy(update={"text": stripped})
        if self.briefing is not None and event.kind.value == "final":
            # Briefing pack: zero-latency matching; each point binds its events.
            for hit in self.briefing.match(event.event_id, event.text):
                await self._journal.append(
                    self._state.session_id(), "briefing_point_surfaced", hit,
                    policy_digest=self._state.session_policy_digest(),
                )
        outcome = self._question_window.ingest(event)
        if outcome.candidate is None or outcome.duplicate:
            # (#1454) A final non-question turn while a blocking clarification
            # is outstanding is treated as its spoken answer.
            if (
                outcome.candidate is None
                and event.kind.value == "final"
                and self._held
            ):
                (question_id, revision), _context = next(iter(self._held.items()))
                blocking = await self._state.blocking_unresolved(question_id, revision)
                if blocking:
                    task = asyncio.create_task(
                        self.apply_clarification_answer(
                            question_id,
                            revision,
                            blocking[0].clarification_id or "",
                            event.text,
                            AnswerSource.SPEECH,
                            [event.event_id],
                        )
                    )
                    self._tasks.add(task)
                    task.add_done_callback(self._task_done)
            return
        candidate = outcome.candidate
        decision = TriggerDecision(
            event_id=candidate.question_id,
            query=candidate.normalized_question,
            thread=candidate_thread(candidate, self._profile),
            reason=candidate.trigger_reason,
            source_event_ids=tuple(span.event_id for span in candidate.source_spans),
        )
        # Claim the revision this retrieval answers BEFORE dispatching it, so a
        # slow result is recognised as stale at publish time, not overwriting.
        question_id, question_revision = await self._state.revise_question(decision.query)
        await self._state.set_thread(decision.thread)
        task = asyncio.create_task(self._retrieve(decision, question_id, question_revision))
        self._tasks.add(task)
        task.add_done_callback(self._task_done)

    async def _write_salient_fact(self, fact) -> None:
        """Persist one explicit decision; trust only the readback.

        An unconfirmed write degrades the Memory lane and journals the full
        source-bound fact rather than dropping it, so nothing is silently
        lost and nothing unverified is presented as remembered.
        """

        confirmed, detail = await self._facts.write_and_confirm(fact)
        session_id = self._state.session_id()
        if confirmed:
            await self._journal.append(
                session_id, "salient_fact_write_confirmed", fact,
                policy_digest=self._state.session_policy_digest(),
            )
            logger.info("salient fact confirmed fact_id={} ({})", fact.fact_id[:12], detail)
            return
        await self._journal.append(
            session_id, "salient_fact_write_unconfirmed", fact,
            policy_digest=self._state.session_policy_digest(),
        )
        await self._state.set_lane(
            RetrievalLane.MEMORY,
            LaneState.DEGRADED,
            f"Fact write unconfirmed: {detail}",
        )
        logger.warning("salient fact UNCONFIRMED fact_id={} ({})", fact.fact_id[:12], detail)

    async def _surface_order(
        self, query: str, thread: str, ranked: list[EvidenceSource]
    ) -> tuple[list[EvidenceSource], bool]:
        """Return ordered sources and whether the card should surface."""
        if is_code_location_query(query):
            receipt = {"mode": "deterministic_code_location", "applied": True, "surface": True}
            await self._journal.append(self._state.session_id(), "surface_selection", receipt,
                                       policy_digest=self._state.session_policy_digest())
            return ranked, True
        if not SurfaceSelector.enabled() or not ranked:
            return ranked, True
        reordered, receipt = await asyncio.to_thread(
            self._selector.order, query, thread, ranked
        )
        await self._journal.append(
            self._state.session_id(), "surface_selection", receipt,
            policy_digest=self._state.session_policy_digest(),
        )
        surface = bool(receipt.get("surface", True))
        if not surface and should_force_surface_source_backed_code(query, reordered):
            override = {
                "mode": "deterministic_source_backed_code_override",
                "applied": True,
                "surface": True,
                "selector_surface": False,
                "reason": "Current-source coding evidence matched a bounded code problem.",
            }
            await self._journal.append(
                self._state.session_id(),
                "surface_selection",
                override,
                policy_digest=self._state.session_policy_digest(),
            )
            return reordered, True
        return reordered, surface

    async def _journal_latest_publication_decision(self) -> None:
        decision = await self._state.latest_card_publication_decision()
        if decision is None:
            return
        await self._journal.append(
            self._state.session_id(),
            "card_publication_decision",
            decision,
            policy_digest=self._state.session_policy_digest(),
        )

    async def _propose_actions(self, verdict, decision, question_id: str,
                               question_revision: int, policy) -> None:
        """Propose resolver action candidates (propose-only; human approves via
        the API), independent of the card gate."""
        if verdict is None or not verdict.action_candidates:
            return
        from .actions import ActionEngine
        digest = self._state.session_policy_digest()
        if self.actions is None or self.actions._policy_digest != digest:
            self.actions = ActionEngine(purpose=self._state.session_purpose(),
                                        policy=policy, policy_digest=digest)
        proposed = self.actions.propose(
            verdict.action_candidates,
            trigger_event_ids=list(decision.source_event_ids),
            question_id=question_id, question_revision=question_revision,
        )
        for entry in self.actions.journal:
            await self._journal.append(self._state.session_id(), entry.pop("kind"),
                                       entry, policy_digest=digest)
        self.actions.journal.clear()

    def register_assistant_utterance(self, text: str) -> None:
        """Record text the assistant is about to speak, for echo suppression."""

        normalized = " ".join(text.split()).lower()
        if normalized:
            self._assistant_utterances.append(normalized)
            del self._assistant_utterances[:-4]

    def _strip_assistant_echo(self, text: str) -> str:
        return strip_assistant_echo(text, self._assistant_utterances)

    async def apply_clarification_answer(
        self,
        question_id: str,
        revision: int,
        clarification_id: str,
        answer: str,
        source: AnswerSource,
        answer_event_ids: list[str],
    ) -> dict:
        """Bind a clarification answer and continue the held solve if unblocked.

        Append-only and revision-fenced (#1454): a stale or unknown target is a
        typed rejection, a duplicate is idempotent and never duplicates solver
        work, and the solver runs at most once per accepted revision after the
        LAST blocking requirement resolves.
        """

        result, entry = await self._state.amend_requirement(
            question_id, revision, clarification_id, answer, source, answer_event_ids
        )
        await self._journal.append(
            self._state.session_id(),
            "requirement_amendment",
            {"question_id": question_id, "question_revision": revision,
             "clarification_id": clarification_id, "result": result,
             "answer_source": source.value,
             "entry": entry.model_dump(mode="json") if entry else None},
            policy_digest=self._state.session_policy_digest(),
        )
        if result != "amended":
            return {"result": result}

        blocking = await self._state.blocking_unresolved(question_id, revision)
        if blocking:
            return {"result": "amended", "blocking_remaining": len(blocking)}

        held = self._held.pop((question_id, revision), None)
        if held is None or (question_id, revision) in self._solved_revisions:
            return {"result": "amended", "blocking_remaining": 0}
        self._solved_revisions.add((question_id, revision))

        policy = self._state.session_policy()
        entries = await self._state.ledger_entries(question_id, revision)
        answers_block = "\n".join(
            f"Clarified ({e.answer_source.value if e.answer_source else '?'}): {e.text} -> {e.clarification_answer}"
            for e in entries
            if e.status is RequirementStatus.CLARIFIED
        )
        query = held["query"]
        display_query = held.get("card_query", held.get("display_query", query))
        seeded_query = f"{query}\n{answers_block}" if answers_block else query
        sources = held["sources"]
        ranked = rank_sources(sources, query, self._profile, repo_scope=self._repo_scope)
        if policy.candidate_answer_generation:
            await self._state.set_lane(
                RetrievalLane.ASK, LaneState.RUNNING, "Solving after clarification"
            )
            ask_result = await self._ask.solve(seeded_query, ranked[:4])
            await self._state.set_lane(
                RetrievalLane.ASK,
                LaneState.OK if ask_result.ok else LaneState.DEGRADED,
                ask_result.detail,
                latency_ms=ask_result.latency_ms,
                result_count=len(ask_result.sources),
            )
            ranked = rank_sources([*sources, *ask_result.sources], query, self._profile, repo_scope=self._repo_scope)
        card = self._summarizer.build(display_query, held["thread"], ranked)
        verdict = held.get("verdict")
        if verdict is not None and verdict.clarifying_questions:
            answered = {
                e.clarification_id: e.clarification_answer
                for e in entries
                if e.status is RequirementStatus.CLARIFIED
            }
            card = card.model_copy(
                update={
                    "clarifications": [
                        ClarificationItem(
                            id=item.id,
                            question=item.question,
                            why_it_matters=item.why_it_matters,
                            default_assumption=item.default_assumption,
                            blocking=item.blocking,
                            answer=answered.get(item.id),
                        )
                        for item in verdict.clarifying_questions
                    ]
                }
            )
        card = card.model_copy(
            update={
                "question_id": question_id,
                "question_revision": revision,
                "policy_digest": self._state.session_policy_digest(),
                "ledger_digest": ledger_digest(entries) if entries else None,
                "assumptions": [
                    e.text for e in entries if e.status is RequirementStatus.ASSUMED
                ][:8],
            }
        )
        snapshot = await self._state.publish_card_fenced(card)
        await self._journal_latest_publication_decision()
        if snapshot is None:
            await self._journal.append(
                self._state.session_id(),
                "evidence_card_discarded_stale_revision",
                card,
                policy_digest=self._state.session_policy_digest(),
            )
            return {"result": "amended", "blocking_remaining": 0, "published": False}
        await self._journal.append(
            snapshot.session.session_id, "evidence_card", card,
            policy_digest=self._state.session_policy_digest(),
        )
        return {"result": "amended", "blocking_remaining": 0, "published": True}

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
            sources = rank_sources(result.sources, request.query, self._profile, repo_scope=self._repo_scope)
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
            sources = rank_sources(result.sources, request.query, self._profile, repo_scope=self._repo_scope)
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
            sources = rank_sources(result.sources, request.query, self._profile, repo_scope=self._repo_scope)
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
            sources = rank_sources(result.sources, request.query, self._profile, repo_scope=self._repo_scope)
        card = self._summarizer.build(request.query, thread, sources)
        card = card.model_copy(update={"policy_digest": self._state.session_policy_digest()})
        snapshot = await self._state.add_card(card)
        await self._journal.append(
            snapshot.session.session_id, "evidence_card", card,
            policy_digest=self._state.session_policy_digest(),
        )
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
        # Stage 1 runs BEFORE retrieval so its canonical question drives search.
        verdict = await self._resolve_readiness(decision.query)
        display_query = decision.query
        query = bounded_query(display_query, verdict)
        memory_result, ripgrep_result = await asyncio.gather(
            self._memory.retrieve(query),
            self._ripgrep.retrieve(query),
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

        if not any(source.lane is RetrievalLane.RIPGREP for source in sources):
            expanded_query = current_source_query_from_memory(query, sources)
            if expanded_query:
                expanded = await self._ripgrep.retrieve(expanded_query)
                await self._journal.append(
                    self._state.session_id(),
                    "current_source_query_expanded",
                    {"query": expanded_query, "result_count": len(expanded.sources)},
                    policy_digest=self._state.session_policy_digest(),
                )
                await self._state.set_lane(
                    RetrievalLane.RIPGREP,
                    LaneState.OK if expanded.ok else LaneState.DEGRADED,
                    f"{expanded.detail}; expanded from Memory code context",
                    latency_ms=expanded.latency_ms,
                    result_count=len(expanded.sources),
                )
                sources.extend(expanded.sources)

        ranked = rank_sources(sources, query, self._profile, repo_scope=self._repo_scope)

        # Actions are a SEPARATE output from cards: a logistics turn ("push to
        # Friday") proposes a schedule action even when its card is suppressed,
        # so propose actions BEFORE the card-surface gate.
        policy = self._state.session_policy()
        await self._propose_actions(verdict, decision, question_id, question_revision, policy)

        ranked, surface = await self._surface_order(query, decision.thread, ranked)
        if not surface:
            # Filtering agent judged this turn not card-worthy (rhetorical,
            # greeting, logistics, bare project mention) or its evidence
            # irrelevant; suppress to keep the HUD scannable.
            await self._state.set_lane(RetrievalLane.ASK, LaneState.IDLE,
                                       "Suppressed: not card-worthy")
            return

        # No resolver -> cannot judge readiness; fall back to the legacy predicate.
        may_ask = (
            verdict.may_invoke_ask
            if verdict is not None
            else _should_solve_with_ask(query, ranked)
        )
        if not policy.candidate_answer_generation:
            # Frozen policy outranks readiness: a formal-assessment or
            # interviewer-assist session never generates an answer (#1449).
            may_ask = False
            await self._state.set_lane(
                RetrievalLane.ASK, LaneState.DISABLED, "Disabled by session policy"
            )

        # (#1454) Requirement ledger: blocking clarifier -> UNRESOLVED, default -> ASSUMED.
        entries = build_requirement_entries(
            question_id, question_revision, display_query, decision, verdict
        )
        digest = await self._state.open_ledger(question_id, question_revision, entries)
        await self._journal.append(
            self._state.session_id(),
            "requirement_ledger_opened",
            {"question_id": question_id, "question_revision": question_revision,
             "ledger_digest": digest,
             "entries": [e.model_dump(mode="json") for e in entries]},
            policy_digest=self._state.session_policy_digest(),
        )
        blocking = await self._state.blocking_unresolved(question_id, question_revision)
        if blocking:
            # Solver must not start while a blocking requirement is UNRESOLVED.
            may_ask = False
            self._held[(question_id, question_revision)] = {
                "query": query,
                "card_query": query,
                "display_query": display_query,
                "thread": decision.thread,
                "sources": sources,
                "verdict": verdict,
            }
            await self._state.set_lane(
                RetrievalLane.ASK,
                LaneState.IDLE,
                f"Holding: {len(blocking)} unresolved requirement(s)",
            )
        if (question_id, question_revision) in self._solved_revisions:
            # At most one automatic solver run per accepted revision.
            may_ask = False

        fast_pending = False
        if may_ask:
            self._solved_revisions.add((question_id, question_revision))
            if FastSolver.available():
                # (#1473) Publish the card first, then stream the answer in.
                fast_pending = True
                await self._state.set_lane(
                    RetrievalLane.ASK, LaneState.RUNNING, "Fast solver streaming"
                )
            else:
                await self._state.set_lane(RetrievalLane.ASK, LaneState.RUNNING, "Solving code question")
                ask_result = await self._ask.solve(query, ranked[:4])
                await self._state.set_lane(
                    RetrievalLane.ASK,
                    LaneState.OK if ask_result.ok else LaneState.DEGRADED,
                    ask_result.detail,
                    latency_ms=ask_result.latency_ms,
                    result_count=len(ask_result.sources),
                )
                ranked = rank_sources([*sources, *ask_result.sources], query, self._profile, repo_scope=self._repo_scope)
        elif verdict is not None:
            # A judged "not ready" holds the solver back and says why.
            await self._state.set_lane(
                RetrievalLane.ASK,
                LaneState.IDLE,
                f"Holding: {verdict.blocking_reason}",
            )

        card_query = query if ranked else display_query
        card = self._summarizer.build(card_query, decision.thread, ranked)
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
        ledger_entries = await self._state.ledger_entries(question_id, question_revision)
        card = card.model_copy(
            update={
                "question_id": question_id,
                "question_revision": question_revision,
                "policy_digest": self._state.session_policy_digest(),
                "ledger_digest": ledger_digest(ledger_entries) if ledger_entries else None,
                "assumptions": [
                    entry.text
                    for entry in ledger_entries
                    if entry.status is RequirementStatus.ASSUMED
                ][:8],
            }
        )
        snapshot = await self._state.publish_card_fenced(card)
        await self._journal_latest_publication_decision()
        if snapshot is None:
            # The question moved on while this ran; keep the work as an audit
            # event rather than discarding it silently.
            await self._journal.append(
                self._state.session_id(),
                "evidence_card_discarded_stale_revision",
                card,
                policy_digest=self._state.session_policy_digest(),
            )
            logger.info(
                "discarded stale result question_id={} revision={} latency_ms={}",
                question_id,
                question_revision,
                int((monotonic() - started) * 1000),
            )
            return
        await self._journal.append(
            snapshot.session.session_id,
            "evidence_card",
            card,
            policy_digest=self._state.session_policy_digest(),
        )
        from .actions import propose_research, research_warranted

        if policy.external_search and research_warranted(card, verdict, ranked):

            await propose_research(
                self, self._state, self._journal, query=query,
                trigger_event_ids=list(decision.source_event_ids),
                question_id=question_id, question_revision=question_revision,
                policy=policy,
            )
        if fast_pending:
            outcome = await stream_fast_answer(
                state=self._state, journal=self._journal, solver=FastSolver(),
                card=card, query=query,
                evidence_excerpts=[source.excerpt[:1_200] for source in ranked[:4]],
                question_id=question_id, question_revision=question_revision,
            )
            lane_state = (
                LaneState.OK if outcome is not None and outcome.ok else LaneState.DEGRADED
            )
            detail = (
                f"Fast answer in {outcome.total_s:.1f}s" if outcome is not None and outcome.ok
                else "Fast solver unavailable or superseded"
            )
            await self._state.set_lane(RetrievalLane.ASK, lane_state, detail)
            if outcome is not None and not outcome.ok:
                # Escalation: the receipt-heavy $ask path answers instead.
                ask_result = await self._ask.solve(query, ranked[:4])
                if ask_result.ok and ask_result.sources:
                    merged = rank_sources([*ranked, *ask_result.sources], query, self._profile, repo_scope=self._repo_scope)
                    await self._state.publish_card_fenced(
                        card.model_copy(update={"sources": merged[:8]})
                    )
                    await self._journal_latest_publication_decision()
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
    return any(
        source.lane in {RetrievalLane.CODE, RetrievalLane.RIPGREP} for source in sources
    )
