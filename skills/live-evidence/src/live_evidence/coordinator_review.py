"""Answer-review helper for EvidenceCoordinator."""
from __future__ import annotations

import asyncio

from loguru import logger

from .solver import FastSolver
from .reviewer import AnswerReviewer
from .retrieval import rank_sources

async def review_published_answer(
    self,
    *,
    card_id: str,
    question: str,
    answer: str,
    question_id: str,
    question_revision: int,
    evidence_excerpts: list[str],
    published_at_index: int = 0,
) -> None:
    """Background review of a first published answer; weak -> streamed amendment.

    The original answer is never replaced mid-read: the amendment streams
    into amendment_text on the SAME card and is promoted by the UI only
    when amendment_complete flips true.
    """

    snapshot = await self._state.snapshot()
    # Publication boundary: judge staleness ONLY on speech after the
    # answer published (WebGPT review). The boundary is captured by the
    # caller at publication time.
    after_events = snapshot.transcript[published_at_index:]
    transcript_after = "\n".join(
        f"{item.speaker.value.upper()}: {item.text}" for item in after_events
    )
    reviewer = AnswerReviewer()
    outcome = await asyncio.to_thread(
        lambda: reviewer.review(
            question, answer, transcript_after, evidence_excerpts=evidence_excerpts
        )
    )
    digest = self._state.session_policy_digest()
    await self._journal.append(
        self._state.session_id(), "answer_review",
        {"card_id": card_id, "question_id": question_id,
         "question_revision": question_revision,
         "verdict": outcome.verdict, "reasons": list(outcome.reasons),
         "deterministic": outcome.deterministic,
         "course_corrected": outcome.course_corrected,
         "error": outcome.error},
        policy_digest=digest,
    )
    if outcome.error is not None or outcome.verdict is None:
        return
    await self._state.update_card_fields(
        card_id,
        review_verdict=outcome.verdict,
        review_reasons=list(outcome.reasons),
    )
    if outcome.verdict != "weak":
        return
    # Amendment lane: re-ground against Memory FIRST. The curated
    # client KB (client_interview_qa) and similar answered questions are
    # the authoritative content; amending from only the original ranked
    # excerpts produces thin generic rewrites (operator, 2026-08-31).
    amendment_excerpts = list(evidence_excerpts)
    try:
        refreshed = await self._memory.retrieve(question)
        if refreshed.ok and refreshed.sources:
            ranked_fresh = rank_sources(
                refreshed.sources, question, self._profile, repo_scope=self._repo_scope
            )
            fresh_excerpts = [source.excerpt[:1_200] for source in ranked_fresh[:4]]
            amendment_excerpts = (fresh_excerpts + amendment_excerpts)[:6]
            await self._journal.append(
                self._state.session_id(), "amendment_regrounded",
                {"card_id": card_id, "fresh_sources": len(ranked_fresh),
                 "lanes": sorted({s.lane.value for s in ranked_fresh[:4]})},
                policy_digest=digest,
            )
    except Exception as exc:  # noqa: BLE001 - degraded grounding, not a dead amendment
        logger.warning("amendment memory re-grounding failed: {}", exc)
    amendment_query = (
        question
        + "\n\nAMEND THE PREVIOUS ANSWER. Reviewer instruction: "
        + (outcome.amendment_instruction or "fix the named defects")
        + "\nDefects: " + "; ".join(outcome.reasons)
    )
    solver = FastSolver()

    category = self._question_categories.get(question_id)
    amendment_mode = "CODE" if category in {"code", "debugging"} else (
        "NON_CODE" if category else None
    )

    def run_amendment() -> str:
        accumulated = ""
        for chunk in solver.stream(amendment_query, amendment_excerpts, answer_mode=amendment_mode):
            text = getattr(chunk, "text", None)
            if text:
                accumulated += text
            answer_text = getattr(chunk, "answer", None)
            if answer_text:
                accumulated = answer_text
        return accumulated

    amended = await asyncio.to_thread(run_amendment)
    if not amended.strip():
        return
    # Same envelope discipline as the primary answer path: the deck JSON
    # block is a UI contract, not display text.
    from .solver import extract_solution_deck

    amended_clean, amended_points = extract_solution_deck(amended)
    update_fields: dict[str, object] = {
        "amendment_text": amended_clean or amended,
        "amendment_complete": True,
    }
    if amended_points:
        update_fields["solution_deck"] = amended_points
    await self._state.update_card_fields(card_id, **update_fields)
    await self._journal.append(
        self._state.session_id(), "answer_amended",
        {"card_id": card_id, "question_id": question_id,
         "amendment_chars": len(amended)},
        policy_digest=digest,
    )
