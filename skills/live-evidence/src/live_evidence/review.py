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

from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import utc_now



class ReviewDisposition(StrEnum):
    """Closed vocabulary for review-claim evidence status (#1451)."""

    SUPPORTED_BY_INTERVIEW = "supported_by_interview"
    SUPPORTED_BY_AUTHORIZED_ARTIFACT = "supported_by_authorized_artifact"
    CANDIDATE_ASSERTION_UNVERIFIED = "candidate_assertion_unverified"
    CONTRADICTED = "contradicted"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class MediaRetention(StrEnum):
    RETAINED_LOCAL = "retained_local"
    EXTERNAL_REFERENCE = "external_reference"
    ABSENT = "absent"


class ReviewQuestion(BaseModel):
    """One question as asked, at one exact revision."""

    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=8, max_length=64)
    question_revision: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=8_000)
    event_ids: list[str] = Field(min_length=1, max_length=64)
    sequence_start: int = Field(ge=0)
    sequence_end: int = Field(ge=0)
    start_s: float = Field(ge=0.0)
    end_s: float = Field(ge=0.0)


class AnswerSpan(BaseModel):
    """An answer segment bound to exact transcript events and timestamps."""

    model_config = ConfigDict(extra="forbid")

    span_id: str = Field(default_factory=lambda: uuid4().hex, min_length=8)
    question_id: str = Field(min_length=8, max_length=64)
    question_revision: int = Field(ge=0)
    event_ids: list[str] = Field(min_length=1, max_length=256)
    sequence_start: int = Field(ge=0)
    sequence_end: int = Field(ge=0)
    start_s: float = Field(ge=0.0)
    end_s: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_range(self) -> "AnswerSpan":
        if self.sequence_end < self.sequence_start or self.end_s < self.start_s:
            raise ValueError("answer span range must not be inverted")
        return self


class ArtifactRef(BaseModel):
    """Authorized independent artifact supporting a claim (repo/ask/memory/debugger)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["repository", "ask", "memory", "debugger"]
    locator: str = Field(min_length=1, max_length=1_000)
    digest: str | None = Field(default=None, min_length=8, max_length=128)


class ReviewClaim(BaseModel):
    """A statement about the interview, honest about what backs it.

    Fail-closed vocabulary enforcement (#1451): a claim cannot be LABELED
    supported without the evidence that would make it supported, and a
    candidate assertion cannot be silently promoted -- the promotion requires
    an artifact, at which point the disposition changes explicitly.
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(default_factory=lambda: uuid4().hex, min_length=8)
    text: str = Field(min_length=1, max_length=2_000)
    disposition: ReviewDisposition
    span_ids: list[str] = Field(default_factory=list, max_length=32)
    artifact_refs: list[ArtifactRef] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def validate_evidence(self) -> "ReviewClaim":
        if self.disposition is ReviewDisposition.SUPPORTED_BY_INTERVIEW and not self.span_ids:
            raise ValueError("supported_by_interview requires at least one answer span")
        if (
            self.disposition is ReviewDisposition.SUPPORTED_BY_AUTHORIZED_ARTIFACT
            and not self.artifact_refs
        ):
            raise ValueError("supported_by_authorized_artifact requires an artifact reference")
        if self.disposition is ReviewDisposition.CONTRADICTED and not self.span_ids:
            raise ValueError("contradicted requires the contradicting span(s)")
        return self


class ReviewerAnnotation(BaseModel):
    """Append-only reviewer note, attributable to an actor; never mutates evidence."""

    model_config = ConfigDict(extra="forbid")

    annotation_id: str = Field(default_factory=lambda: uuid4().hex, min_length=8)
    actor: str = Field(min_length=1, max_length=200)
    created_at: datetime = Field(default_factory=utc_now)
    claim_id: str | None = Field(default=None, min_length=8, max_length=64)
    note: str = Field(min_length=1, max_length=4_000)


class ReviewBundle(BaseModel):
    """Versioned post-interview review dossier (#1451).

    bundle_digest() covers the evidence core (everything except reviewer
    annotations), so appending a note never invalidates the evidence identity,
    while mutating any transcript/media/claim binding does.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    schema_id: Literal["live_evidence.review_bundle.v1"] = Field(
        default="live_evidence.review_bundle.v1",
        validation_alias="schema",
        serialization_alias="schema",
    )
    review_id: str = Field(default_factory=lambda: uuid4().hex, min_length=8)
    session_id: str = Field(min_length=8, max_length=64)
    session_policy_digest: str = Field(min_length=64, max_length=64)
    media_id: str = Field(min_length=1, max_length=200)
    media_locator: str = Field(min_length=1, max_length=1_000)
    media_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    media_retention: MediaRetention
    transcript_digest: str = Field(min_length=64, max_length=64)
    questions: list[ReviewQuestion] = Field(default_factory=list, max_length=256)
    answer_spans: list[AnswerSpan] = Field(default_factory=list, max_length=1_024)
    review_claims: list[ReviewClaim] = Field(default_factory=list, max_length=512)
    reviewer_annotations: list[ReviewerAnnotation] = Field(default_factory=list, max_length=1_024)
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_bindings(self) -> "ReviewBundle":
        """No dangling or cross-revision attribution (#1451).

        An answer span must bind a question at its exact revision as present in
        this bundle; a claim must bind spans that exist. An answer can never be
        attributed to an obsolete wording of a question.
        """

        revisions = {(q.question_id, q.question_revision) for q in self.questions}
        for span in self.answer_spans:
            if (span.question_id, span.question_revision) not in revisions:
                raise ValueError(
                    f"answer span {span.span_id} binds question {span.question_id} "
                    f"rev {span.question_revision} which is not in this bundle"
                )
        span_ids = {span.span_id for span in self.answer_spans}
        for claim in self.review_claims:
            missing = [sid for sid in claim.span_ids if sid not in span_ids]
            if missing:
                raise ValueError(f"claim {claim.claim_id} binds unknown span(s) {missing}")
        if self.media_retention is MediaRetention.RETAINED_LOCAL and not self.media_sha256:
            raise ValueError("locally retained media requires media_sha256")
        return self

    def bundle_digest(self) -> str:
        payload = self.model_dump(mode="json", by_alias=True)
        payload.pop("reviewer_annotations", None)
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def tldr(self) -> list[dict[str, Any]]:
        """Summary bullets generated ONLY from evidence-bearing claims."""

        bullets: list[dict[str, Any]] = []
        for claim in self.review_claims:
            if claim.disposition in {
                ReviewDisposition.SUPPORTED_BY_INTERVIEW,
                ReviewDisposition.SUPPORTED_BY_AUTHORIZED_ARTIFACT,
            }:
                bullets.append(
                    {
                        "text": claim.text,
                        "disposition": claim.disposition.value,
                        "span_ids": list(claim.span_ids),
                        "artifact_refs": [ref.model_dump() for ref in claim.artifact_refs],
                    }
                )
        return bullets





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
