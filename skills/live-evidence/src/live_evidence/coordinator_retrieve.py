"""Retrieval helper for EvidenceCoordinator."""
from __future__ import annotations

import asyncio
import json
from time import monotonic

from loguru import logger

from .code_context import current_source_query_from_memory
from .fast_path import stream_fast_answer
from .models import (
    ClarificationItem,
    EvidenceSource,
    LaneState,
    RetrievalLane,
    RequirementStatus,
    ledger_digest,
)
from .query_bounds import bounded_query
from .requirement_ledger import build_requirement_entries
from .retrieval import (
    has_reviewed_oracle_answer,
    prefer_reviewed_oracle_answers,
    rank_sources,
)
from .solver import FastSolver
from .trigger import TriggerDecision

async def retrieve(
    self,
    decision: TriggerDecision,
    question_id: str,
    question_revision: int,
    *,
    session_id: str,
    policy_digest: str,
) -> None:
    await self._state.set_lane(RetrievalLane.MEMORY, LaneState.RUNNING, decision.reason)
    await self._state.set_lane(RetrievalLane.CODE, LaneState.RUNNING, "Indexed code")
    await self._state.set_lane(RetrievalLane.RIPGREP, LaneState.RUNNING, "Current source")
    started = monotonic()
    if decision.reason == "scanner_complete":
        # Scanner verdicts are terminal: a question judged complete in the
        # scanner's strict JSON is NEVER re-evaluated by a second model
        # call. verdict=None flows through the existing None-safe paths
        # (heuristic may_ask, no clarification hold, unbounded query).
        verdict = None
    else:
        ledger = await self._state.question_ledger()
        # Deterministic junk gate + restatement dedupe BEFORE any model call
        # (2026-09-03 live: 12-item timeline for ~3 questions; garbled STT
        # fragment 'chair to show 4 loop of 5 easier' carded). Reuses the
        # proven scanner_fallback machinery on the resolver path.
        from . import scanner_fallback as sf

        query_lowered = decision.query.casefold()
        if (
            len(sf.question_words(decision.query)) < 4
            or sf.scanner_skip_text(decision.query)
            or not any(term in query_lowered for term in sf.ASK_TERMS)
        ):
            try:
                await self._journal.append(
                    session_id,
                    "question_skipped_junk_fragment",
                    {"question_id": question_id, "query": decision.query},
                    policy_digest=policy_digest,
                )
            finally:
                for lane in (RetrievalLane.MEMORY, RetrievalLane.CODE, RetrievalLane.RIPGREP):
                    await self._state.set_lane(lane, LaneState.IDLE, "Not a question")
                if decision.candidate_fingerprint:
                    self._question_window.forget(decision.candidate_fingerprint)
            return
        restated_id = sf.matching_progressive_question_id(decision.query, ledger)
        if restated_id and restated_id != question_id:
            entry = next((e for e in ledger if str(e.get("id")) == restated_id), None)
            if entry is not None and entry.get("answered"):
                try:
                    await self._journal.append(
                        session_id,
                        "question_skipped_already_answered",
                        {"question_id": question_id, "matches_question_id": restated_id,
                         "query": decision.query, "dedupe": "deterministic_restatement"},
                        policy_digest=policy_digest,
                    )
                finally:
                    for lane in (RetrievalLane.MEMORY, RetrievalLane.CODE, RetrievalLane.RIPGREP):
                        await self._state.set_lane(lane, LaneState.IDLE, "Already answered")
                    if decision.candidate_fingerprint:
                        self._question_window.forget(decision.candidate_fingerprint)
                return
            if entry is not None:
                # Restatement of a pending question: revise that card in place.
                question_id, question_revision = await self._state.adopt_question(
                    restated_id, decision.query
                )
        verdict = await self._resolve_readiness(decision.query, ledger)
    if verdict is not None and verdict.already_answered:
        # Ledger-aware dedupe by construction: a KNOWN answered question
        # covers this ask, so no new card and no retrieval fan-out.
        # try/finally matches the deterministic skip paths above: a journal
        # failure must never leave lanes RUNNING or the fingerprint retained.
        try:
            await self._journal.append(
                session_id,
                "question_skipped_already_answered",
                {
                    "question_id": question_id,
                    "matches_question_id": verdict.matches_question_id,
                    "query": decision.query,
                },
                policy_digest=policy_digest,
            )
        finally:
            for lane in (RetrievalLane.MEMORY, RetrievalLane.CODE, RetrievalLane.RIPGREP):
                await self._state.set_lane(lane, LaneState.IDLE, "Already answered")
            if decision.candidate_fingerprint:
                self._question_window.forget(decision.candidate_fingerprint)
        return
    if (
        verdict is not None
        and verdict.matches_question_id
        and verdict.matches_question_id != question_id
        and any(entry["id"] == verdict.matches_question_id for entry in ledger)
    ):
        # Refinement of a KNOWN question: revise that id in place instead
        # of minting a new timeline entry.
        question_id, question_revision = await self._state.adopt_question(
            verdict.matches_question_id, decision.query
        )
    display_query = decision.query
    query = bounded_query(display_query, verdict)
    # Threader runs concurrently with retrieval. Scanner-complete dispatches
    # skip it entirely: the scanner owns grouping on that path, and a fake
    # deterministic new_topic journal there would be wrong. A hard 10s budget
    # (wait_for) guarantees the card can never wait on grouping - on timeout
    # the verdict is simply absent, degrading to ungrouped presentation.
    async def _classify_with_budget() -> object:
        if decision.reason == "scanner_complete":
            return None
        thread_ledger = [
            entry for entry in (await self._state.question_ledger())
            if str(entry.get("id")) != str(question_id)
        ]
        return await asyncio.wait_for(
            asyncio.to_thread(self._threader.classify, decision.query, thread_ledger),
            timeout=10.0,
        )

    memory_result, ripgrep_result, thread_outcome = await asyncio.gather(
        self._memory.retrieve(query),
        self._ripgrep.retrieve(query),
        _classify_with_budget(),
        return_exceptions=True,
    )
    if (
        thread_outcome is not None
        and not isinstance(thread_outcome, Exception)
        and thread_outcome.verdict is not None
        and question_id not in self._follow_up_parents
    ):
        verdict_payload = {
            "question_id": question_id,
            "relation": thread_outcome.verdict.relation,
            "parent_id": thread_outcome.verdict.parent_id,
            "topic_title": thread_outcome.verdict.topic_title,
            "elapsed_s": thread_outcome.elapsed_s,
        }
        if thread_outcome.verdict.relation == "follow_up" and thread_outcome.verdict.parent_id:
            self._follow_up_parents[question_id] = thread_outcome.verdict.parent_id
        await self._journal.append(
            session_id, "thread_verdict", verdict_payload, policy_digest=policy_digest
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
                session_id,
                "current_source_query_expanded",
                {"query": expanded_query, "result_count": len(expanded.sources)},
                policy_digest=policy_digest,
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
    policy = self._state.session_policy()
    await self._propose_actions(verdict, decision, question_id, question_revision, policy)
    ranked, surface = await self._surface_order(
        query,
        decision.thread,
        ranked,
        session_id=session_id,
        policy_digest=policy_digest,
    )
    ranked = prefer_reviewed_oracle_answers(ranked, query)
    if not surface:
        if decision.candidate_fingerprint:
            self._question_window.forget(decision.candidate_fingerprint)
        await self._state.set_lane(RetrievalLane.ASK, LaneState.IDLE,
                                   "Suppressed: not card-worthy")
        return
    await self._journal.append(
        session_id,
        "answer_needed_moment",
        {
            "schema": "live_evidence.answer_needed_moment.v1",
            "question_id": question_id,
            "question_revision": question_revision,
            "query": query,
            "display_query": display_query,
            "source_event_ids": list(decision.source_event_ids),
            "trigger_reason": decision.reason,
            "surface_gate": "accepted",
        },
        policy_digest=policy_digest,
    )
    reviewed_oracle_answer = has_reviewed_oracle_answer(ranked)
    may_ask = (
        verdict.may_invoke_ask
        if verdict is not None
        else _should_solve_with_ask(query, ranked)
    )
    if reviewed_oracle_answer:
        may_ask = False
    if not policy.candidate_answer_generation:
        may_ask = False
        await self._state.set_lane(
            RetrievalLane.ASK, LaneState.DISABLED, "Disabled by session policy"
        )
    entries = build_requirement_entries(
        question_id, question_revision, display_query, decision, verdict
    )
    digest = await self._state.open_ledger(question_id, question_revision, entries)
    await self._journal.append(
        session_id,
        "requirement_ledger_opened",
        {"question_id": question_id, "question_revision": question_revision,
         "ledger_digest": digest,
         "entries": [e.model_dump(mode="json") for e in entries]},
        policy_digest=policy_digest,
    )
    blocking = await self._state.blocking_unresolved(question_id, question_revision)
    if blocking:
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
        may_ask = False
    fast_pending = False
    if may_ask:
        self._solved_revisions.add((question_id, question_revision))
        if FastSolver.available():
            fast_pending = True
            await self._state.set_lane(
                RetrievalLane.ASK, LaneState.RUNNING, "Fast solver streaming"
            )
        else:
            await self._state.set_lane(RetrievalLane.ASK, LaneState.RUNNING, "Solving code question")
            ask_result = await self._ask.solve(query, ranked[:4], binding={
                "session_id": session_id, "policy_digest": policy_digest,
                "question_id": question_id, "question_revision": question_revision,
                "query": query,
            })
            await self._state.set_lane(
                RetrievalLane.ASK,
                LaneState.OK if ask_result.ok else LaneState.DEGRADED,
                ask_result.detail,
                latency_ms=ask_result.latency_ms,
                result_count=len(ask_result.sources),
            )
            ranked = rank_sources([*sources, *ask_result.sources], query, self._profile, repo_scope=self._repo_scope)
            ranked = prefer_reviewed_oracle_answers(ranked, query)
    elif reviewed_oracle_answer:
        await self._state.set_lane(
            RetrievalLane.ASK,
            LaneState.IDLE,
            "Using reviewed oracle answer",
        )
    elif verdict is not None:
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
            "parent_question_id": self._follow_up_parents.get(question_id),
            "policy_digest": policy_digest,
            "ledger_digest": ledger_digest(ledger_entries) if ledger_entries else None,
            "assumptions": [
                entry.text
                for entry in ledger_entries
                if entry.status is RequirementStatus.ASSUMED
            ][:8],
        }
    )
    snapshot = await self._state.publish_card_fenced(card)
    await self._journal_latest_publication_decision(session_id, policy_digest)
    if snapshot is None:
        publication_decision = await self._state.latest_card_publication_decision()
        hidden_fast_draft = (
            fast_pending
            and publication_decision is not None
            and publication_decision.status.value == "held"
            and "insufficient_card_not_publishable"
            in publication_decision.reason_codes
        )
        if not hidden_fast_draft:
            await self._journal.append(
                session_id,
                "evidence_card_discarded_stale_revision",
                card,
                policy_digest=policy_digest,
            )
            logger.info(
                "discarded stale result question_id={} revision={} latency_ms={}",
                question_id,
                question_revision,
                int((monotonic() - started) * 1000),
            )
            return
    else:
        await self._journal.append(
            session_id,
            "evidence_card",
            card,
            policy_digest=policy_digest,
        )
        if (card.answer or "").strip() and card.answer_review is None:
            # Oracle/summarizer-answered publication: the answer arrived
            # WITH the card (no fast-solver stream), so this is the
            # first-answer moment that triggers the background reviewer.
            review_task = asyncio.create_task(
                self._review_published_answer(
                    card_id=card.card_id,
                    question=display_query,
                    answer=card.answer or "",
                    question_id=question_id,
                    question_revision=question_revision,
                    evidence_excerpts=[_excerpt_with_authority(source) for source in ranked[:4]],
                    published_at_index=len(snapshot.transcript),
                )
            )
            self._tasks.add(review_task)
            review_task.add_done_callback(self._task_done)
        from .actions import propose_research, research_warranted
        if policy.external_search and research_warranted(card, verdict, ranked):
            await propose_research(
                self, self._state, self._journal, query=query,
                trigger_event_ids=list(decision.source_event_ids),
                question_id=question_id, question_revision=question_revision,
                policy=policy,
            )
    if fast_pending:
        category = self._question_categories.get(question_id)
        answer_mode = "CODE" if category in {"code", "debugging"} else (
            "NON_CODE" if category else None
        )
        outcome = await stream_fast_answer(
            state=self._state, journal=self._journal, solver=FastSolver(),
            card=card, query=query,
            evidence_excerpts=[_excerpt_with_authority(source) for source in ranked[:4]],
            question_id=question_id, question_revision=question_revision,
            session_id=session_id,
            policy_digest=policy_digest,
            answer_mode=answer_mode,
        )
        if outcome is not None and outcome.ok and outcome.answer.strip():
            # First published answer -> the question is answered; that
            # triggers the background reviewer (fourth agent), off the
            # critical path. The answer is already on screen.
            boundary_snapshot = await self._state.snapshot()
            review_task = asyncio.create_task(
                self._review_published_answer(
                    card_id=card.card_id,
                    question=display_query,
                    answer=outcome.answer,
                    question_id=question_id,
                    question_revision=question_revision,
                    evidence_excerpts=[_excerpt_with_authority(source) for source in ranked[:4]],
                    published_at_index=len(boundary_snapshot.transcript),
                )
            )
            self._tasks.add(review_task)
            review_task.add_done_callback(self._task_done)
        lane_state = (
            LaneState.OK if outcome is not None and outcome.ok else LaneState.DEGRADED
        )
        detail = (
            f"Fast answer in {outcome.total_s:.1f}s" if outcome is not None and outcome.ok
            else "Fast solver unavailable or superseded"
        )
        await self._state.set_lane(RetrievalLane.ASK, lane_state, detail)
        if outcome is not None and not outcome.ok:
            await self._journal.append(
                session_id,
                "fast_solver_fallback_ask_skipped",
                {
                    "question_id": question_id,
                    "question_revision": question_revision,
                    "error": outcome.error,
                    "reason": "live_fast_path_must_fail_closed_not_block_on_slow_ask",
                },
                policy_digest=policy_digest,
            )
    logger.info(
        "evidence card status={} sources={} revision={} latency_ms={}",
        card.status.value,
        len(card.sources),
        question_revision,
        int((monotonic() - started) * 1000),
    )

def _excerpt_with_authority(source: EvidenceSource) -> str:
    """Return a structured evidence envelope with runtime-owned authority.

    Content remains untrusted text: a literal ``[authority=...]`` line inside
    ``content`` never changes the trusted metadata fields in this JSON object.
    """

    source_id = source.source_id or ""
    path = source.path or ""
    trusted = source_id.startswith("client_interview_qa/") or "/answer-key/" in path
    envelope = {
        "excerpt_id": source_id,
        "authority": "reviewed_solution" if trusted else "supporting",
        "freshness": str(source.freshness),
        "lane": str(source.lane),
        "label": source.label,
        "content": source.excerpt[:1_200],
    }
    return json.dumps(envelope, ensure_ascii=False)

def _should_solve_with_ask(query: str, sources: list[EvidenceSource]) -> bool:
    if has_reviewed_oracle_answer(sources):
        return False
    return any(source.lane in {RetrievalLane.CODE, RetrievalLane.RIPGREP} for source in sources)
