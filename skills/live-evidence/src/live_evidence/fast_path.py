"""Progressive card publication for the fast-path solver (#1473).

Runs the solver stream off the event loop and republishes the SAME
question/revision card as the answer grows. Every publish goes through the
compare-and-swap fence, so a question that moves on mid-stream discards the
remainder (journaled), and a finished answer carries its own receipt: model,
effort, first-content and total latency, and the response digest.
"""

from __future__ import annotations

import asyncio
import os
from time import monotonic
from typing import Any, Awaitable, Callable

from loguru import logger

from .models import CardStatus, EvidenceCard, EvidenceSource, PublicationStatus, RetrievalLane, SolutionDeckPoint
from .solver import FastSolver, SolverChunk, SolverOutcome, extract_solution_deck

PUBLISH_INTERVAL_S = 0.4
DEFAULT_FIRST_CONTENT_TIMEOUT_S = 8.0
ANSWER_CHAR_BUDGET = 2_400
TALKING_POINT_CHAR_BUDGET = 1_000


def _first_content_timeout_s() -> float:
    raw = os.getenv("LIVE_EVIDENCE_SOLVER_FIRST_CONTENT_TIMEOUT", "")
    if not raw:
        return DEFAULT_FIRST_CONTENT_TIMEOUT_S
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_FIRST_CONTENT_TIMEOUT_S
    return max(0.1, value)


async def _journal_latest_publication_decision(
    state: Any, journal: Any, session_id: str, policy_digest: str
) -> Any | None:
    decision = await state.latest_card_publication_decision()
    if decision is None:
        return None
    await journal.append(
        session_id,
        "card_publication_decision",
        decision,
        policy_digest=policy_digest,
    )
    return decision


def _is_hidden_draft_decision(decision: Any | None) -> bool:
    if decision is None:
        return False
    return (
        decision.status is PublicationStatus.HELD
        and "insufficient_card_not_publishable" in decision.reason_codes
    )


async def stream_fast_answer(
    *,
    state: Any,
    journal: Any,
    solver: FastSolver,
    card: EvidenceCard,
    query: str,
    evidence_excerpts: list[str],
    question_id: str,
    question_revision: int,
    session_id: str,
    policy_digest: str,
    answer_mode: str | None = None,
) -> SolverOutcome | None:
    """Stream the answer into the already-published card. Returns the final
    outcome, or None when the revision went stale mid-stream."""

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def run() -> None:
        try:
            for item in solver.stream(query, evidence_excerpts, answer_mode=answer_mode):
                loop.call_soon_threadsafe(queue.put_nowait, item)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    producer = loop.run_in_executor(None, run)
    accumulated = ""
    outcome: SolverOutcome | None = None
    last_publish = 0.0
    first_content_journaled = False
    stale = False
    started = monotonic()
    first_content_timeout = _first_content_timeout_s()
    await_producer = True
    try:
        while True:
            try:
                if first_content_journaled:
                    item = await queue.get()
                else:
                    remaining = first_content_timeout - (monotonic() - started)
                    item = await asyncio.wait_for(queue.get(), timeout=max(0.01, remaining))
            except asyncio.TimeoutError:
                await_producer = False
                producer.cancel()
                outcome = SolverOutcome(
                    ok=False,
                    error=f"first_content_timeout_after_{first_content_timeout:.1f}s",
                    model=getattr(solver, "_model", ""),
                    effort=getattr(solver, "_effort", ""),
                    first_content_s=None,
                    total_s=monotonic() - started,
                    chunk_count=0,
                )
                await journal.append(
                    session_id, "fast_solver_first_content_timeout",
                    {"question_id": question_id, "question_revision": question_revision,
                     "timeout_s": first_content_timeout},
                    policy_digest=policy_digest,
                )
                await journal.append(
                    session_id, "fast_solver_failed",
                    {"question_id": question_id, "question_revision": question_revision,
                     "error": outcome.error},
                    policy_digest=policy_digest,
                )
                return outcome
            if item is None:
                break
            if isinstance(item, SolverOutcome):
                outcome = item
                continue
            if stale or not isinstance(item, SolverChunk):
                continue
            accumulated += item.text
            if not first_content_journaled:
                first_content_journaled = True
                await journal.append(
                    session_id, "fast_solver_first_content",
                    {"question_id": question_id, "question_revision": question_revision,
                     "elapsed_s": round(item.elapsed_s, 3)},
                    policy_digest=policy_digest,
                )
            now = monotonic()
            if now - last_publish >= PUBLISH_INTERVAL_S:
                last_publish = now
                display_answer, deck_points = extract_solution_deck(accumulated)
                snapshot = await state.publish_card_fenced(
                    card.model_copy(update={
                        "answer": (display_answer or accumulated)[:ANSWER_CHAR_BUDGET],
                        "solution_deck": [SolutionDeckPoint(**point) for point in deck_points],
                    })
                )
                decision = await _journal_latest_publication_decision(
                    state, journal, session_id, policy_digest
                )
                if snapshot is None:
                    if _is_hidden_draft_decision(decision):
                        continue
                    stale = True
                    await journal.append(
                        session_id, "fast_solver_discarded_stale_revision",
                        {"question_id": question_id, "question_revision": question_revision,
                         "chars_discarded": len(accumulated)},
                        policy_digest=policy_digest,
                    )
    finally:
        if await_producer:
            await producer

    if stale:
        return None
    if outcome is None or not outcome.ok:
        await journal.append(
            session_id, "fast_solver_failed",
            {"question_id": question_id, "question_revision": question_revision,
             "error": outcome.error if outcome else "no_outcome"},
            policy_digest=policy_digest,
        )
        return outcome
    receipt = {
        "question_id": question_id,
        "question_revision": question_revision,
        "mode": "tau_fast_path",
        "model": outcome.model,
        "reasoning_effort": outcome.effort,
        "first_content_s": outcome.first_content_s,
        "total_s": round(outcome.total_s or 0.0, 3),
        "response_sha256": outcome.response_sha256,
        "chunk_count": outcome.chunk_count,
    }
    clean_answer, deck_points = extract_solution_deck(outcome.answer)
    answer_excerpt = (clean_answer or outcome.answer)[:ANSWER_CHAR_BUDGET]
    final_sources = [
        *card.sources,
        EvidenceSource(
            lane=RetrievalLane.ASK,
            label=f"fast solver {outcome.model} ({outcome.effort})",
            excerpt=(clean_answer or outcome.answer)[:4_000],
            # locator contract: the response digest IS the stable key
            # for this generated artifact; there is no file path.
            url=f"tau://{outcome.model}/{outcome.response_sha256}",
            metadata=receipt,
        ),
    ][:8]
    final_lanes = list(dict.fromkeys([*card.lanes, RetrievalLane.ASK]))
    final = card.model_copy(
        update={
            "answer": answer_excerpt,
            "talking_point": answer_excerpt[:TALKING_POINT_CHAR_BUDGET] or card.talking_point,
            "evidence": (
                f"Fast solver response digest {outcome.response_sha256[:16]} "
                f"from {outcome.model}."
            ),
            "proof": (
                f"Generated by fast solver {outcome.model} ({outcome.effort}); "
                f"response sha256 {outcome.response_sha256}."
            )[:1_200],
            "qualifier": (
                "Generated from the heard question; verify source-specific "
                "claims against attached evidence."
            ),
            "confidence": max(card.confidence, 0.7),
            "status": CardStatus.SUPPORTED,
            "sources": final_sources,
            "solution_deck": [SolutionDeckPoint(**point) for point in deck_points],
            "lanes": final_lanes,
        }
    )
    snapshot = await state.publish_card_fenced(final)
    await _journal_latest_publication_decision(state, journal, session_id, policy_digest)
    if snapshot is None:
        await journal.append(
            session_id, "fast_solver_discarded_stale_revision",
            {**receipt, "at": "final_publish"}, policy_digest=policy_digest,
        )
        return None
    # The journal must hold the ANSWERED card, not only the pre-answer
    # placeholder publish -- reviewers and evals read answers from the
    # journal after cards rotate out of live state.
    await journal.append(
        session_id, "evidence_card", final, policy_digest=policy_digest
    )
    await journal.append(
        session_id, "fast_solver_receipt", receipt, policy_digest=policy_digest
    )
    logger.info(
        "fast solver answered rev={} first_content={}s total={}s chunks={}",
        question_revision, outcome.first_content_s, receipt["total_s"], outcome.chunk_count,
    )
    return outcome
