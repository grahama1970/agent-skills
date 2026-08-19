"""Post-interview review dossier builder (#1451).

Turns one session's append-only journal into a versioned ReviewBundle a
reviewer can inspect claim-by-claim. The builder never invents evidence: every
question and answer span binds exact transcript event ids, sequences, and
media timestamps read back from the journal, and mutation of any bound digest
is detectable through bundle_digest() / verify_bundle().

This module produces NO hiring verdict and NO model-scored recommendation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .models import (
    AnswerSpan,
    MediaRetention,
    ReviewBundle,
    ReviewClaim,
    ReviewQuestion,
    ReviewerAnnotation,
)


def transcript_digest(events: list[dict[str, Any]]) -> str:
    """Deterministic digest over the exact journaled transcript payloads."""

    canonical = json.dumps(
        [
            {
                "event_id": event.get("event_id"),
                "sequence": event.get("sequence"),
                "text": event.get("text"),
                "start_ms": event.get("start_ms"),
                "end_ms": event.get("end_ms"),
            }
            for event in events
        ],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_journal(journal_path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in journal_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def _transcript_events(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r.get("payload") or {} for r in records if r.get("kind") == "transcript"]


def _event_window(
    events: list[dict[str, Any]], event_ids: list[str]
) -> tuple[list[str], int, int, float, float]:
    """Resolve exact sequence range and media timestamps for the given events.

    Fails loudly on an unknown event id: a span that cannot be tied back to a
    journaled event is not evidence.
    """

    by_id = {event.get("event_id"): event for event in events}
    missing = [event_id for event_id in event_ids if event_id not in by_id]
    if missing:
        raise ValueError(f"unknown transcript event id(s): {missing}")
    chosen = [by_id[event_id] for event_id in event_ids]
    sequences = [int(event.get("sequence") or 0) for event in chosen]
    starts = [int(event.get("start_ms") or 0) for event in chosen]
    ends = [int(event.get("end_ms") or event.get("start_ms") or 0) for event in chosen]
    return (
        list(event_ids),
        min(sequences),
        max(sequences),
        min(starts) / 1000.0,
        max(ends) / 1000.0,
    )


def build_review_bundle(
    journal_path: Path,
    *,
    session_id: str,
    session_policy_digest: str,
    media_id: str,
    media_locator: str,
    media_retention: MediaRetention,
    media_sha256: str | None = None,
    question_specs: list[dict[str, Any]],
    span_specs: list[dict[str, Any]],
    claims: list[ReviewClaim] | None = None,
    created_at: Any | None = None,
    review_id: str | None = None,
) -> ReviewBundle:
    """Assemble a ReviewBundle whose every binding is read back from the journal.

    question_specs: [{question_id, question_revision, text, event_ids}]
    span_specs:     [{span_id?, question_id, question_revision, event_ids}]
    """

    records = load_journal(journal_path)
    events = _transcript_events(records)
    if not events:
        raise ValueError(f"journal has no transcript events: {journal_path}")

    questions: list[ReviewQuestion] = []
    for spec in question_specs:
        event_ids, seq_start, seq_end, start_s, end_s = _event_window(
            events, list(spec["event_ids"])
        )
        questions.append(
            ReviewQuestion(
                question_id=spec["question_id"],
                question_revision=int(spec["question_revision"]),
                text=spec["text"],
                event_ids=event_ids,
                sequence_start=seq_start,
                sequence_end=seq_end,
                start_s=start_s,
                end_s=end_s,
            )
        )

    spans: list[AnswerSpan] = []
    for spec in span_specs:
        event_ids, seq_start, seq_end, start_s, end_s = _event_window(
            events, list(spec["event_ids"])
        )
        kwargs: dict[str, Any] = {}
        if spec.get("span_id"):
            kwargs["span_id"] = spec["span_id"]
        spans.append(
            AnswerSpan(
                question_id=spec["question_id"],
                question_revision=int(spec["question_revision"]),
                event_ids=event_ids,
                sequence_start=seq_start,
                sequence_end=seq_end,
                start_s=start_s,
                end_s=end_s,
                **kwargs,
            )
        )

    extra: dict[str, Any] = {}
    if created_at is not None:
        extra["created_at"] = created_at
    if review_id is not None:
        extra["review_id"] = review_id
    return ReviewBundle(
        session_id=session_id,
        session_policy_digest=session_policy_digest,
        media_id=media_id,
        media_locator=media_locator,
        media_sha256=media_sha256,
        media_retention=media_retention,
        transcript_digest=transcript_digest(events),
        questions=questions,
        answer_spans=spans,
        review_claims=list(claims or []),
        **extra,
    )


def verify_bundle(bundle: ReviewBundle, journal_path: Path) -> dict[str, Any]:
    """Fail-closed readback: prove the bundle still matches its journal.

    Returns {ok, transcript_digest_ok, bundle_digest} and raises nothing --
    a reviewer surface must be able to SHOW a mutation, not crash on it.
    """

    events = _transcript_events(load_journal(journal_path))
    digest_ok = transcript_digest(events) == bundle.transcript_digest
    known = {event.get("event_id") for event in events}
    dangling = [
        event_id
        for item in (*bundle.questions, *bundle.answer_spans)
        for event_id in item.event_ids
        if event_id not in known
    ]
    return {
        "ok": digest_ok and not dangling,
        "transcript_digest_ok": digest_ok,
        "dangling_event_ids": dangling,
        "bundle_digest": bundle.bundle_digest(),
    }


def append_annotation(bundle: ReviewBundle, annotation: ReviewerAnnotation) -> ReviewBundle:
    """Append-only, attributable; never mutates evidence or its digest."""

    if annotation.claim_id is not None and annotation.claim_id not in {
        claim.claim_id for claim in bundle.review_claims
    }:
        raise ValueError(f"annotation targets unknown claim {annotation.claim_id}")
    return bundle.model_copy(
        update={"reviewer_annotations": [*bundle.reviewer_annotations, annotation]}
    )
