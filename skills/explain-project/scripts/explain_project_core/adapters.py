"""Pure adapter normalization and intent construction for explain-project.

These functions construct typed intents only. They never invoke debugger
commands, reveal VS Code, capture audio, or mutate Excalidraw boards.
"""

from __future__ import annotations

from .models import (
    DebuggerStop,
    DebuggerTargetIntent,
    Diagram,
    DiagramHighlightIntent,
    FailureCode,
    LiveEvidenceQuestionPayload,
    QuestionInput,
    SourceRange,
    SourceRevealIntent,
)


class AdapterBoundaryError(ValueError):
    """Typed adapter-boundary failure with a stable code."""

    def __init__(
        self,
        code: FailureCode,
        message: str,
    ) -> None:
        super().__init__(message)
        self.code = code


def normalize_manual_question(
    event_id: str,
    text: str,
) -> QuestionInput:
    """Normalize a hand-entered question."""

    return QuestionInput(
        input_id=event_id,
        source="manual",
        text=" ".join(text.split()),
        provenance="manual",
    )


def normalize_live_evidence_question(
    event_id: str,
    payload: LiveEvidenceQuestionPayload,
) -> QuestionInput:
    """Normalize replay/live candidates without claiming capture."""

    candidate = payload.candidate

    if payload.source == "live_evidence_replay":
        return QuestionInput(
            input_id=event_id,
            source="live_evidence_replay",
            text=candidate.normalized_question,
            source_ref=candidate.question_id,
            source_fingerprint=candidate.fingerprint,
            provenance="replay",
        )

    if payload.live_receipt is not None:
        receipt = payload.live_receipt

        if (
            receipt.candidate_id != candidate.question_id
            or receipt.candidate_fingerprint != candidate.fingerprint
        ):
            raise AdapterBoundaryError(
                FailureCode.LIVE_RECEIPT_MISMATCH,
                "live receipt does not bind to the supplied "
                "question candidate",
            )

        return QuestionInput(
            input_id=event_id,
            source="live_evidence_live",
            text=candidate.normalized_question,
            source_ref=receipt.source_ref or receipt.receipt_id,
            source_fingerprint=receipt.source_fingerprint,
            provenance="live_receipt",
        )

    if payload.source_fingerprint:
        return QuestionInput(
            input_id=event_id,
            source="live_evidence_live",
            text=candidate.normalized_question,
            source_ref=candidate.question_id,
            source_fingerprint=payload.source_fingerprint,
            provenance="live_fingerprint",
        )

    raise AdapterBoundaryError(
        FailureCode.LIVE_PROVENANCE_REQUIRED,
        "live_evidence_live requires a live receipt "
        "or source_fingerprint",
    )


def source_reveal_intent(
    revision: int,
    source_range: SourceRange,
) -> SourceRevealIntent:
    """Build a debugger-owned VS Code reveal request without executing it."""

    return SourceRevealIntent(
        revision=revision,
        target=source_range,
    )


def debugger_target_intent(
    revision: int,
    target: DebuggerStop,
) -> DebuggerTargetIntent:
    """Build a breakpoint preparation request with execution disabled."""

    return DebuggerTargetIntent(
        revision=revision,
        target=target,
    )


def diagram_highlight_intent(
    revision: int,
    diagram: Diagram,
    active_node_ids: list[str],
) -> DiagramHighlightIntent:
    """Build a display-only diagram highlight request."""

    return DiagramHighlightIntent(
        revision=revision,
        source_kind=diagram.source_kind,
        source_path=diagram.source_path,
        rendered_svg_path=diagram.rendered_svg_path,
        active_node_ids=active_node_ids,
    )
