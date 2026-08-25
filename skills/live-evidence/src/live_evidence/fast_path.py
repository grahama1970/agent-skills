"""Progressive card publication for the fast-path solver (#1473).

Runs the FastSolver stream off the event loop and republishes the SAME
question/revision card as the answer grows. Every publish goes through the
compare-and-swap fence, so a question that moves on mid-stream discards the
remainder (journaled), and a finished answer carries its own receipt: model,
effort, first-content and total latency, and the response digest.
"""

from __future__ import annotations

import asyncio
from time import monotonic
from typing import Any, Awaitable, Callable

from loguru import logger

from .models import EvidenceCard, EvidenceSource, RetrievalLane
from .solver import FastSolver, SolverChunk, SolverOutcome

PUBLISH_INTERVAL_S = 0.4


async def _journal_latest_publication_decision(
    state: Any, journal: Any, session_id: str, policy_digest: str
) -> None:
    decision = await state.latest_card_publication_decision()
    if decision is None:
        return
    await journal.append(
        session_id,
        "card_publication_decision",
        decision,
        policy_digest=policy_digest,
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
) -> SolverOutcome | None:
    """Stream the answer into the already-published card. Returns the final
    outcome, or None when the revision went stale mid-stream."""

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def run() -> None:
        try:
            for item in solver.stream(query, evidence_excerpts):
                loop.call_soon_threadsafe(queue.put_nowait, item)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    producer = loop.run_in_executor(None, run)
    accumulated = ""
    outcome: SolverOutcome | None = None
    last_publish = 0.0
    first_content_journaled = False
    stale = False
    try:
        while True:
            item = await queue.get()
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
                snapshot = await state.publish_card_fenced(
                    card.model_copy(update={"answer": accumulated[:1_200]})
                )
                await _journal_latest_publication_decision(
                    state, journal, session_id, policy_digest
                )
                if snapshot is None:
                    stale = True
                    await journal.append(
                        session_id, "fast_solver_discarded_stale_revision",
                        {"question_id": question_id, "question_revision": question_revision,
                         "chars_discarded": len(accumulated)},
                        policy_digest=policy_digest,
                    )
    finally:
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
        "mode": "scillm_fast_path",
        "model": outcome.model,
        "reasoning_effort": outcome.effort,
        "first_content_s": outcome.first_content_s,
        "total_s": round(outcome.total_s or 0.0, 3),
        "response_sha256": outcome.response_sha256,
        "chunk_count": outcome.chunk_count,
    }
    final = card.model_copy(
        update={
            "answer": outcome.answer[:1_200],
            "sources": [
                *card.sources,
                EvidenceSource(
                    lane=RetrievalLane.ASK,
                    label=f"fast solver {outcome.model} ({outcome.effort})",
                    excerpt=outcome.answer[:4_000],
                    # locator contract: the response digest IS the stable key
                    # for this generated artifact; there is no file path.
                    url=f"scillm://{outcome.model}/{outcome.response_sha256}",
                    metadata=receipt,
                ),
            ][:8],
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
