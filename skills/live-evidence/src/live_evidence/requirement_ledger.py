"""Requirement-ledger entry construction (#1454), split out of the coordinator."""

from __future__ import annotations

from .models import Requirement, RequirementKind, RequirementStatus


def build_requirement_entries(question_id, question_revision, query, decision, verdict):
    """Requirement ledger entries for one question revision (#1454).

    The objective is transcript-bound; every clarifying question becomes an
    entry (blocking UNRESOLVED, ASSUMED with a labeled default, or non-blocking
    UNRESOLVED so it stays amendable); completeness is judged by the resolver
    and this ledger, never punctuation.
    """

    entries: list[Requirement] = [
        Requirement(
            question_id=question_id,
            question_revision=question_revision,
            kind=RequirementKind.OBJECTIVE,
            text=query[:1_000],
            source_event_ids=list(decision.source_event_ids)[:16],
            status=RequirementStatus.STATED,
        )
    ]
    if verdict is not None:
        for item in verdict.clarifying_questions:
            if item.blocking:
                entries.append(
                    Requirement(
                        question_id=question_id,
                        question_revision=question_revision,
                        kind=RequirementKind.CONSTRAINT,
                        text=item.question[:1_000],
                        source_event_ids=list(decision.source_event_ids)[:16],
                        status=RequirementStatus.UNRESOLVED,
                        blocking=True,
                        clarification_id=item.id,
                    )
                )
            elif item.default_assumption:
                entries.append(
                    Requirement(
                        question_id=question_id,
                        question_revision=question_revision,
                        kind=RequirementKind.CONSTRAINT,
                        text=item.default_assumption[:1_000],
                        status=RequirementStatus.ASSUMED,
                        blocking=False,
                        clarification_id=item.id,
                        assumption_source=f"default assumption for unanswered clarification {item.id}: {item.question[:200]}",
                    )
                )
            else:
                # Non-blocking, no default: still a live question about the
                # task, and it must be AMENDABLE -- without a ledger entry a
                # later human answer 404s as unknown_clarification (observed
                # live on the G2I-02 benchmark case).
                entries.append(
                    Requirement(
                        question_id=question_id,
                        question_revision=question_revision,
                        kind=RequirementKind.CONSTRAINT,
                        text=item.question[:1_000],
                        source_event_ids=list(decision.source_event_ids)[:16],
                        status=RequirementStatus.UNRESOLVED,
                        blocking=False,
                        clarification_id=item.id,
                    )
                )
    return entries
