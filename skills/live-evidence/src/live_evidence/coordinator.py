"""Transcript-to-evidence orchestration."""
from __future__ import annotations
import asyncio
import json
import os
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
    has_reviewed_oracle_answer,
    prefer_reviewed_oracle_answers,
    rank_sources,
)
from .state import RuntimeState
from .summarizer import ExtractiveSummarizer
from .surface_selector import SurfaceSelector
from .surface_policy import should_force_surface_source_backed_code
from .question_window import QuestionWindowBuilder, candidate_thread
from .reviewer import AnswerReviewer
from .scanner import QuestionScanner, scanner_key
from . import scanner_fallback
from .coordinator_review import review_published_answer
from .coordinator_retrieve import _should_solve_with_ask, retrieve
from .query_bounds import bounded_query
from .trigger import TriggerDecision
class CardPublicationHeld(RuntimeError):
    """A manual candidate did not pass the shared publication gate."""


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
        self._solved_revisions: set[tuple[str, int]] = set()
        self._held: dict[tuple[str, int], dict] = {}
        self._missing_input_questions: set[str] = set()
        self._assistant_utterances: list[str] = []
        self._scanner = QuestionScanner()
        from .threader import QuestionThreader

        self._threader = QuestionThreader()
        self._ready_queue: asyncio.Queue[tuple[str, int, TriggerDecision]] = asyncio.Queue()
        self._answer_workers: list[asyncio.Task[None]] = []
        self._scan_in_flight = False
        self._scan_requested = False
        self._scan_cursor = 0
        self._dispatched_questions: set[str] = set()
        self._dispatched_texts: dict[str, str] = {}
        self._follow_up_parents: dict[str, str] = {}
        self._question_categories: dict[str, str] = {}
        self._chars_since_scan = 0
        self._scan_char_interval = int(os.getenv("LIVE_EVIDENCE_SCAN_CHAR_INTERVAL", "300"))
        self._wake_words = tuple(
            word.strip().lower()
            for word in os.getenv("LIVE_EVIDENCE_SCAN_WAKE_WORDS", "let me see").split(",")
            if word.strip()
        )

    @staticmethod
    def _scanner_mode() -> bool:
        return os.getenv("LIVE_EVIDENCE_SCANNER_MODE", "true").lower() not in {"0", "false", "no"}

    def _ensure_answer_workers(self) -> None:
        if self._answer_workers:
            return
        for index in range(2):
            worker = asyncio.create_task(self._answer_worker(f"answer-worker-{index + 1}"))
            self._answer_workers.append(worker)

    async def _answer_worker(self, worker_id: str) -> None:
        while True:
            question_id, revision, decision = await self._ready_queue.get()
            acquired = await self._state.acquire_lease(question_id, worker_id)
            if not acquired:
                # Another worker owns this question; never write over its card.
                self._ready_queue.task_done()
                continue
            try:
                await self._retrieve(
                    decision,
                    question_id,
                    revision,
                    session_id=self._state.session_id(),
                    policy_digest=self._state.session_policy_digest(),
                )
            except Exception:  # noqa: BLE001 - a worker crash must not kill the pool
                logger.exception("answer worker {} failed on {}", worker_id, question_id[:8])
            finally:
                await self._state.release_lease(question_id, worker_id)
                self._dispatched_questions.discard(question_id)
                self._ready_queue.task_done()

    _review_published_answer = review_published_answer

    def _scanner_client_context(self) -> str:
        lines: list[str] = [f"profile: {self._profile.name}"]
        if self._profile.watch_terms:
            lines.append("watch_terms: " + ", ".join(self._profile.watch_terms[:24]))
        if self.briefing is not None:
            titles = [point.title for point in self.briefing.pack.points[:16]]
            if titles:
                lines.append("prepared_briefing_topics:")
                lines.extend(f"- {title}" for title in titles)
        return "\n".join(lines)

    _same_progressive_question = staticmethod(scanner_fallback.same_progressive_question)
    _fallback_question_key = staticmethod(scanner_fallback.fallback_question_key)

    def _restatement_match(self, text: str) -> str | None:
        """Return the id of an already-dispatched question this text restates."""

        key = self._fallback_question_key(text)
        for known_id, known_text in self._dispatched_texts.items():
            if self._same_progressive_question(known_text, text):
                return known_id
            if key == self._fallback_question_key(known_text):
                return known_id
        return None
    _scanner_skip_text = staticmethod(scanner_fallback.scanner_skip_text)
    _matching_progressive_question_id = staticmethod(scanner_fallback.matching_progressive_question_id)
    _ledger_text = staticmethod(scanner_fallback.ledger_text)
    _fallback_scan = staticmethod(scanner_fallback.fallback_scan)

    _coherent_tail = staticmethod(scanner_fallback.coherent_tail)

    async def _run_scan(self) -> None:
        if self._scan_in_flight:
            self._scan_requested = True
            return
        self._scan_in_flight = True
        try:
            snapshot = await self._state.snapshot()
            new_events = [
                item for item in snapshot.transcript
                if int(item.sequence or 0) > self._scan_cursor
            ]
            tail_events = self._coherent_tail(new_events or snapshot.transcript[-12:])[-24:]
            turns = [
                {
                    "turn_id": item.turn_id or item.event_id,
                    "sequence": item.sequence or index + 1,
                    "speaker": item.speaker.value,
                    "text": item.text,
                }
                for index, item in enumerate(tail_events)
            ]
            if not any(str(turn.get("text") or "").strip() for turn in turns):
                return
            ledger = await self._state.question_ledger()
            outcome = await asyncio.to_thread(
                self._scanner.scan, turns, ledger, self._scanner_client_context(), self._scan_cursor
            )
            digest = self._state.session_policy_digest()
            questions = outcome.questions
            fallback_questions = self._fallback_scan(turns, ledger)
            if outcome.error is not None:
                await self._journal.append(
                    self._state.session_id(), "scanner_error",
                    {"error": outcome.error, "raw": outcome.raw[:500]},
                    policy_digest=digest,
                )
                questions = fallback_questions
                if not questions:
                    return
            elif fallback_questions and not any(q.status in {"complete", "follow_up"} for q in questions):
                await self._journal.append(
                    self._state.session_id(), "scanner_forming_fallback",
                    {"provider_results": [{"status": q.status, "text": q.text[:80]} for q in questions],
                     "fallback_results": [{"status": q.status, "text": q.text[:80]} for q in fallback_questions]},
                    policy_digest=digest,
                )
                questions = fallback_questions
            if turns:
                self._scan_cursor = max(
                    self._scan_cursor,
                    *(int(turn.get("sequence") or 0) for turn in turns),
                )
            await self._journal.append(
                self._state.session_id(), "scan_completed",
                {"window": [int(turn.get("sequence") or 0) for turn in turns[:1] + turns[-1:]],
                 "cursor": self._scan_cursor,
                 "fallback": outcome.error is not None,
                 "results": [{"status": q.status, "id": q.question_id,
                              "text": q.text[:80]} for q in questions]},
                policy_digest=digest,
            )
            answered_ids = {
                str(entry["id"]) for entry in ledger if entry.get("answered")
            }
            for question in questions:
                if self._scanner_skip_text(question.text):
                    continue
                scanned_question_id = (
                    question.question_id
                    or self._matching_progressive_question_id(question.text, ledger)
                    or self._restatement_match(question.text)
                )
                if question.status == "already_answered":
                    await self._journal.append(
                        self._state.session_id(), "question_skipped_already_answered",
                        {"matches_question_id": scanned_question_id, "text": question.text},
                        policy_digest=digest,
                    )
                    continue
                if question.status == "forming":
                    continue
                parent_question_id: str | None = None
                if question.status == "follow_up":
                    parent_question_id = scanned_question_id
                    from uuid import uuid4

                    question_id, revision = await self._state.adopt_question(
                        uuid4().hex, question.text
                    )
                    await self._journal.append(
                        self._state.session_id(), "follow_up_question_opened",
                        {"parent_question_id": parent_question_id,
                         "question_id": question_id, "text": question.text},
                        policy_digest=digest,
                    )
                    self._dispatched_questions.add(question_id)
                    self._dispatched_texts[question_id] = question.text
                    self._follow_up_parents[question_id] = parent_question_id
                    self._question_categories[question_id] = question.category
                    decision = TriggerDecision(
                        event_id=question_id,
                        query=question.text,
                        thread=question.text[:60],
                        reason="scanner_complete",
                        source_event_ids=tuple(item.event_id for item in tail_events[-4:]),
                        candidate_fingerprint=None,
                    )
                    await self._state.set_thread(decision.thread)
                    self._ensure_answer_workers()
                    await self._ready_queue.put((question_id, revision, decision))
                    continue
                if scanned_question_id and scanned_question_id in answered_ids:
                    known_text = self._ledger_text(scanned_question_id, ledger) \
                        or self._dispatched_texts.get(scanned_question_id, "")
                    if self._same_progressive_question(known_text, question.text) \
                            or known_text.strip().casefold() == question.text.strip().casefold():
                        continue
                if scanned_question_id and (
                    scanned_question_id in self._dispatched_questions
                    or await self._state.lease_holder(scanned_question_id) is not None
                ):
                    known_text = self._dispatched_texts.get(scanned_question_id, "") \
                        or self._ledger_text(scanned_question_id, ledger)
                    if (
                        question.text.strip()
                        and question.text.strip() != known_text.strip()
                        and self._same_progressive_question(known_text, question.text)
                    ):
                        if await self._state.refine_question_text(
                            scanned_question_id, question.text
                        ):
                            self._dispatched_texts[scanned_question_id] = question.text
                            await self._journal.append(
                                self._state.session_id(), "question_text_refined",
                                {"question_id": scanned_question_id,
                                 "text": question.text},
                                policy_digest=digest,
                            )
                    continue
                if scanned_question_id:
                    question_id, revision = await self._state.adopt_question(
                        scanned_question_id, question.text
                    )
                else:
                    from uuid import uuid4

                    question_id, revision = await self._state.adopt_question(
                        uuid4().hex, question.text
                    )
                self._dispatched_questions.add(question_id)
                self._dispatched_texts[question_id] = question.text
                self._question_categories[question_id] = question.category
                if question.missing_input:
                    self._missing_input_questions.add(question_id)
                await self._journal.append(
                    self._state.session_id(), "question_classified",
                    {"question_id": question_id, "category": question.category,
                     "skills": list(question.skills)},
                    policy_digest=digest,
                )
                decision = TriggerDecision(
                    event_id=question_id,
                    query=question.text,
                    thread=question.text[:60],
                    reason="scanner_complete",
                    # The question was assembled from the scanned tail; those
                    # events are its provenance (requirement ledger requires
                    # source events for STATED entries).
                    source_event_ids=tuple(item.event_id for item in tail_events[-4:]),
                    candidate_fingerprint=None,
                )
                await self._state.set_thread(decision.thread)
                self._ensure_answer_workers()
                await self._ready_queue.put((question_id, revision, decision))
        finally:
            self._scan_in_flight = False
            if self._scan_requested:
                self._scan_requested = False
                scan_task = asyncio.create_task(self._run_scan())
                self._tasks.add(scan_task)
                scan_task.add_done_callback(self._task_done)
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
            for hit in self.briefing.match(event.event_id, event.text):
                await self._journal.append(
                    self._state.session_id(), "briefing_point_surfaced", hit,
                    policy_digest=self._state.session_policy_digest(),
                )
        if self._scanner_mode():
            # Scanner triggers (decision 4: both + wake word):
            # 1. silence pause - any final interviewer turn;
            # 2. char interval - N new final chars since the last scan, so a
            #    long uninterrupted monologue still gets scanned mid-flow;
            # 3. wake word - the human says e.g. 'let me see' (either speaker),
            #    an explicit on-demand trigger.
            is_final = event.kind.value == "final"
            if is_final:
                self._chars_since_scan += len(event.text)
            text_lower = event.text.lower()
            wake_hit = is_final and any(word in text_lower for word in self._wake_words)
            should_scan = (
                (is_final and event.speaker.value == "interviewer")
                or self._chars_since_scan >= self._scan_char_interval
                or wake_hit
            )
            if should_scan:
                self._chars_since_scan = 0
                if wake_hit:
                    await self._journal.append(
                        self._state.session_id(), "scan_wake_word_triggered",
                        {"event_id": event.event_id, "text": event.text[:120]},
                        policy_digest=self._state.session_policy_digest(),
                    )
                scan_task = asyncio.create_task(self._run_scan())
                self._tasks.add(scan_task)
                scan_task.add_done_callback(self._task_done)
            return
        outcome = self._question_window.ingest(event)
        if outcome.candidate is None or outcome.duplicate:
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
            candidate_fingerprint=candidate.fingerprint,
        )
        question_id, question_revision = await self._state.revise_question(decision.query)
        await self._state.set_thread(decision.thread)
        task = asyncio.create_task(
            self._retrieve(
                decision,
                question_id,
                question_revision,
                session_id=snapshot.session.session_id,
                policy_digest=digest,
            )
        )
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
        self,
        query: str,
        thread: str,
        ranked: list[EvidenceSource],
        *,
        session_id: str,
        policy_digest: str,
    ) -> tuple[list[EvidenceSource], bool]:
        """Return ordered sources and whether the card should surface."""
        if is_code_location_query(query):
            receipt = {"mode": "deterministic_code_location", "applied": True, "surface": True}
            await self._journal.append(session_id, "surface_selection", receipt,
                                       policy_digest=policy_digest)
            return ranked, True
        if not SurfaceSelector.enabled() or not ranked:
            return ranked, True
        reordered, receipt = await asyncio.to_thread(
            self._selector.order, query, thread, ranked
        )
        await self._journal.append(
            session_id, "surface_selection", receipt,
            policy_digest=policy_digest,
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
                session_id,
                "surface_selection",
                override,
                policy_digest=policy_digest,
            )
            return reordered, True
        return reordered, surface
    async def _journal_latest_publication_decision(
        self, session_id: str | None = None, policy_digest: str | None = None
    ) -> None:
        decision = await self._state.latest_card_publication_decision()
        if decision is None:
            return
        await self._journal.append(
            session_id or self._state.session_id(),
            "card_publication_decision",
            decision,
            policy_digest=policy_digest or self._state.session_policy_digest(),
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
            binding = {
                "session_id": self._state.session_id(),
                "policy_digest": self._state.session_policy_digest(),
                "question_id": question_id, "question_revision": revision,
                "query": display_query,
            }
            ask_result = await self._ask.solve(seeded_query, ranked[:4], binding=binding)
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
    async def _resolve_readiness(
        self, query: str, ledger: list[dict[str, object]] | None = None
    ) -> ReadinessVerdict | None:
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
            for event in self._resolver.stream(query, known_questions=ledger):
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
        question_id, revision = await self._state.revise_question(request.query)
        session_id = self._state.session_id()
        policy_digest = self._state.session_policy_digest()
        binding = {"session_id": session_id, "policy_digest": policy_digest,
                   "question_id": question_id, "question_revision": revision,
                   "query": request.query}
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
            local = await self._ripgrep.retrieve(request.query)
            memory = await self._memory.retrieve(request.query)
            seeds = rank_sources([*memory.sources, *local.sources], request.query,
                                 self._profile, repo_scope=self._repo_scope)
            result = await self._ask.solve(request.query, seeds[:4], binding=binding)
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
        card = card.model_copy(update={"policy_digest": policy_digest,
                                       "question_id": question_id, "question_revision": revision})
        snapshot = await self._state.publish_card_fenced(card)
        await self._journal_latest_publication_decision(session_id, policy_digest)
        if snapshot is None:
            await self._journal.append(session_id, "manual_card_held", card,
                                       policy_digest=policy_digest)
            raise CardPublicationHeld("answer_review_required_or_stale_revision")
        await self._journal.append(
            snapshot.session.session_id, "evidence_card", card,
            policy_digest=self._state.session_policy_digest(),
        )
        return card
    _retrieve = retrieve

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

