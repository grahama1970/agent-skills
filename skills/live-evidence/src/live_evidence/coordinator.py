"""Transcript-to-evidence orchestration."""

from __future__ import annotations

import asyncio
import re
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
    AnswerSource,
    Requirement,
    RequirementKind,
    RequirementStatus,
    ledger_digest,
)
from .readiness import ReadinessVerdict
from .resolver import GateEvent, StreamingResolver
from .requirement_ledger import build_requirement_entries
from .salient_facts import SalientFactWriter, extract_decision
from .persistence import SessionJournal
from .retrieval import (
    AskSolutionClient,
    ExternalSkillClient,
    MemoryEvidenceClient,
    RipgrepEvidenceClient,
    rank_sources,
)
from .retrieval.external import derive_manual_search_query
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
        self.journal = journal  # public handle for API routes (#1450)
        self._question_window = QuestionWindowBuilder(profile)
        self._memory = MemoryEvidenceClient(settings, profile)
        self._ripgrep = RipgrepEvidenceClient(settings, profile)
        self._external = ExternalSkillClient(settings)
        self._ask = AskSolutionClient(settings)
        self._summarizer = ExtractiveSummarizer()
        self._resolver = StreamingResolver()
        self._facts = SalientFactWriter(settings.memory_url)
        self._tasks: set[asyncio.Task[None]] = set()
        # (#1454) at-most-once solver per accepted question revision, plus the
        # held retrieval context for questions blocked on unresolved
        # requirements, so an amendment can continue without re-retrieving.
        self._solved_revisions: set[tuple[str, int]] = set()
        self._held: dict[tuple[str, int], dict] = {}
        # Text the assistant is currently speaking aloud (#1453). The mic path
        # hears our own TTS and labels it "interviewer"; without suppression
        # Embry's monologue becomes a question candidate and pollutes the
        # window -- observed live: the "redirect" card after a barge-in was
        # Embry's own breakpoint explanation. We KNOW what we are saying, so
        # transcript events that substantially match it are journaled as
        # assistant echo and never enter the question path.
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
        # Salient-fact capture runs beside question handling, never inside it:
        # an explicit decision is a record to remember, not a question to
        # answer, and its durable write must not block or join the
        # revision-fenced card path. Consent is already enforced above -- an
        # ARMED session returns before reaching this line.
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
        outcome = self._question_window.ingest(event)
        if outcome.candidate is None or outcome.duplicate:
            # (#1454) A final interviewer turn that is NOT a new question, while
            # a blocking clarification is outstanding, is treated as its spoken
            # answer -- bound to the exact question revision and clarification.
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
        # Claim the revision this retrieval answers BEFORE dispatching it. A
        # later turn bumps the revision, so a slow result can be recognised as
        # stale at publication time instead of overwriting a newer answer.
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

    def register_assistant_utterance(self, text: str) -> None:
        """Record text the assistant is about to speak, for echo suppression."""

        normalized = " ".join(text.split()).lower()
        if normalized:
            self._assistant_utterances.append(normalized)
            del self._assistant_utterances[:-4]

    def _strip_assistant_echo(self, text: str) -> str:
        """Redact the assistant's own spoken content, keep everything else.

        Character-level fuzzy matching, not token identity: STT respells our
        own speech ("breakpoint" -> "break point", "forty two" -> "42",
        "set" -> "said"), so exact-token runs missed the echo entirely --
        observed live: the registered monologue survived redaction verbatim.
        difflib matching blocks of 15+ characters against each registered
        utterance are removed; genuinely human speech does not share long
        character runs with the assistant's script by accident.
        """

        if not self._assistant_utterances:
            return text
        import difflib

        # SequenceMatcher yields ONE monotone alignment, but cumulative STT
        # buffers can contain the same echoed phrase more than once -- the
        # second occurrence survived a single pass (observed live: the card
        # question repeated "point I set at line 42" twice). Iterate to a
        # fixed point, bounded.
        for _ in range(6):
            lowered = text.lower()
            cut: list[tuple[int, int]] = []
            for utterance in self._assistant_utterances:
                matcher = difflib.SequenceMatcher(None, lowered, utterance, autojunk=False)
                for block in matcher.get_matching_blocks():
                    if block.size >= 15:
                        cut.append((block.a, block.a + block.size))
            if not cut:
                if _ == 0:
                    return text  # nothing echoed at all: leave text untouched
                break
            cut.sort()
            # Expand each cut to word boundaries: a mid-word cut leaves
            # fragments like "oint" from "breakpoint" that later STT variance
            # turns into card text (observed live: "o the break 42").
            expanded: list[tuple[int, int]] = []
            for start, end in cut:
                while start > 0 and not text[start - 1].isspace():
                    start -= 1
                while end < len(text) and not text[end].isspace():
                    end += 1
                expanded.append((start, end))
            kept: list[str] = []
            cursor = 0
            for start, end in expanded:
                if start > cursor:
                    kept.append(text[cursor:start])
                cursor = max(cursor, end)
            kept.append(text[cursor:])
            text = " ".join("".join(kept).split())
        # Final scrub, only reached when something WAS cut: residual words that
        # fuzzily belong to the assistant's own vocabulary are echo debris, not
        # human content. Fuzzy on purpose -- STT respells our speech
        # ("breakpoint" -> "break"/"oint.42"), so exact-vocab matching misses
        # exactly the debris that survives the character cuts.
        import re as _re

        vocabulary = {
            part
            for utterance in self._assistant_utterances
            for token in utterance.split()
            for part in _re.split(r"[^a-z0-9]+", token)
            if len(part) >= 4 or part.isdigit()
        }

        def is_debris(word: str) -> bool:
            parts = [p for p in _re.split(r"[^a-z0-9]+", word.lower()) if p]
            if not parts:
                return False
            def part_matches(part: str) -> bool:
                if part in vocabulary:
                    return True
                if len(part) >= 4:
                    return any(len(v) >= 5 and (part in v or v in part) for v in vocabulary)
                return False
            return all(part_matches(p) for p in parts)

        return " ".join(word for word in text.split() if not is_debris(word))

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
        seeded_query = f"{query}\n{answers_block}" if answers_block else query
        sources = held["sources"]
        ranked = rank_sources(sources, query, self._profile)
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
            ranked = rank_sources([*sources, *ask_result.sources], query, self._profile)
        card = self._summarizer.build(query, held["thread"], ranked)
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
        # Stage 1 runs BEFORE retrieval so its canonical question can drive the
        # search terms, the Ask seed, and the card, instead of the raw window.
        verdict = await self._resolve_readiness(decision.query)
        query = _bounded_query(decision.query, verdict)
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

        ranked = rank_sources(sources, query, self._profile)

        # When the resolver is unreachable or unconfigured we cannot judge
        # readiness at all, which is different from judging "not ready". Falling
        # back to the legacy predicate keeps local/offline runs working instead
        # of silently disabling the Ask lane whenever SciLLM is absent.
        policy = self._state.session_policy()
        may_ask = (
            verdict.may_invoke_ask
            if verdict is not None
            else _should_solve_with_ask(query, ranked)
        )
        if not policy.candidate_answer_generation:
            # Frozen session policy outranks the readiness verdict: a
            # formal-assessment or interviewer-assist session never generates
            # a candidate answer, however ready the question is (#1449).
            may_ask = False
            await self._state.set_lane(
                RetrievalLane.ASK, LaneState.DISABLED, "Disabled by session policy"
            )

        # (#1454) Requirement ledger for this question revision. The objective
        # is transcript-bound; each blocking clarifying question becomes an
        # UNRESOLVED blocking requirement; a default assumption becomes a
        # visibly labeled ASSUMED entry. A grammatical period never marks the
        # task complete: completeness is judged by the resolver and by this
        # ledger, not punctuation.
        entries = build_requirement_entries(
            question_id, question_revision, query, decision, verdict
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

        if may_ask:
            self._solved_revisions.add((question_id, question_revision))
            await self._state.set_lane(RetrievalLane.ASK, LaneState.RUNNING, "Solving code question")
            ask_result = await self._ask.solve(query, ranked[:4])
            await self._state.set_lane(
                RetrievalLane.ASK,
                LaneState.OK if ask_result.ok else LaneState.DEGRADED,
                ask_result.detail,
                latency_ms=ask_result.latency_ms,
                result_count=len(ask_result.sources),
            )
            ranked = rank_sources([*sources, *ask_result.sources], query, self._profile)
        elif verdict is not None:
            # A judged "not ready" holds the solver back and says why, so the
            # HUD never shows a confident answer to a truncated question.
            await self._state.set_lane(
                RetrievalLane.ASK,
                LaneState.IDLE,
                f"Holding: {verdict.blocking_reason}",
            )

        card = self._summarizer.build(query, decision.thread, ranked)
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
        if snapshot is None:
            # The question moved on while this ran. Keep the work as an audit
            # event rather than discarding it silently, and never let it reach
            # the active card.
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


# A sentence is question-shaped if it ends in '?' OR in a spoken tag question
# ("... come before closing, right" / "... correct"). Live STT drops terminal
# punctuation nondeterministically -- one oracle trial transcribed the same
# clip with almost no '?' at all -- and tag questions are how interviewers
# actually confirm constraints aloud.
_QUESTION_SENTENCE_RE = re.compile(
    r"([^.?!]{8,}(?:\?|,\s*(?:right|correct|okay|yes)\b[.?!]?))", re.IGNORECASE
)


def _bounded_query(raw: str, verdict: ReadinessVerdict | None) -> str:
    """One bounded question for retrieval, Ask, and the card.

    The collapse removed the sentence-selecting _best_retrieval_query on the
    promise that stage-1's canonical_question would replace it, but the
    coordinator kept feeding the raw rolling window downstream. Measured
    consequence on the live YouTube eval: a 1200-char conversational blob as
    the card query, and ripgrep terms so diluted that a fixture file literally
    named valid_parentheses.py went unmatched (card: insufficient, lanes: []).

    Preference order: the resolver's canonical question; else the last
    question-shaped sentence (derive_manual_search_query, deterministic, works
    offline -- on the same eval transcript it yields exactly "A opening
    parentheses always has to come before closing, right?"); else the raw text.
    """

    if verdict is not None:
        canonical = verdict.canonical_question.strip()
        if canonical:
            return canonical[:220]
    # Accumulate trailing question sentences newest-first within the budget,
    # not just the last one: a spoken turn is often a primary question followed
    # by a confirmation tail ("What makes X valid? Y comes before Z, right?"),
    # and keeping only the tail drops the actual question -- caught by
    # eval_real_stt_window when a last-sentence-only fallback shipped here.
    sentences = _QUESTION_SENTENCE_RE.findall(" ".join(raw.split()))
    picked: list[str] = []
    total = 0
    for sentence in reversed(sentences):
        sentence = sentence.strip()
        if total + len(sentence) + 1 > 220:
            break
        picked.insert(0, sentence)
        total += len(sentence) + 1
    if picked:
        return " ".join(picked)
    derived = derive_manual_search_query(raw, max_chars=220)
    return derived or raw


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
