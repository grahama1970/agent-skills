"""Typed cross-layer contracts for Live Evidence.

Inputs arrive from audio callbacks, HTTP clients, subprocesses, YAML, and the
React UI. Pydantic validates those external boundaries before runtime state or
retrieval logic uses the values. The models intentionally keep evidence and
human-facing summaries separate so relevance cannot silently become authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


class Speaker(StrEnum):
    """Known speaker channels."""

    GRAHAM = "graham"
    INTERVIEWER = "interviewer"
    UNKNOWN = "unknown"


class TranscriptKind(StrEnum):
    """Transcription stability states."""

    INTERIM = "interim"
    STABILIZED = "stabilized"
    FINAL = "final"


class SessionPurpose(StrEnum):
    """What this session is FOR. Frozen at start; changing it is a new session."""

    MEETING = "meeting"
    REHEARSAL = "rehearsal"
    FORMAL_ASSESSMENT = "formal_assessment"
    INTERVIEWER_ASSIST = "interviewer_assist"
    POST_INTERVIEW_REVIEW = "post_interview_review"


class ActorRole(StrEnum):
    """Who the operator is acting as in this session."""

    PARTICIPANT = "participant"
    CANDIDATE = "candidate"
    INTERVIEWER = "interviewer"
    REVIEWER = "reviewer"


class CapabilityPolicy(BaseModel):
    """Frozen per-session capability grants, enforced in the backend.

    UI toggles are presentation; these fields are the authority (#1449). A
    disabled capability fails closed on BOTH automatic and manual routes: a
    formal-assessment session must reject a hand-typed manual Ask exactly as it
    suppresses the automatic one.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    capture_audio: bool = True
    retain_transcript: bool = True
    retrieve_local_evidence: bool = True
    external_search: bool = False
    candidate_answer_generation: bool = True
    interviewer_followup_suggestions: bool = False
    debugger_invocation: bool = False
    repository_mutation: bool = False
    voice_output: bool = False


POLICY_VERSION = 1

# Purpose defaults (#1449). formal_assessment fails closed on every assistance
# and effect capability; enabling one requires an explicit policy override at
# session start, which changes the digest that every artifact binds.
DEFAULT_POLICIES: dict[SessionPurpose, CapabilityPolicy] = {
    SessionPurpose.MEETING: CapabilityPolicy(external_search=True),
    SessionPurpose.REHEARSAL: CapabilityPolicy(voice_output=True),
    SessionPurpose.FORMAL_ASSESSMENT: CapabilityPolicy(
        external_search=False,
        candidate_answer_generation=False,
        interviewer_followup_suggestions=False,
        debugger_invocation=False,
        repository_mutation=False,
        voice_output=False,
    ),
    SessionPurpose.INTERVIEWER_ASSIST: CapabilityPolicy(
        candidate_answer_generation=False,
        interviewer_followup_suggestions=True,
    ),
    SessionPurpose.POST_INTERVIEW_REVIEW: CapabilityPolicy(
        capture_audio=False,
        candidate_answer_generation=False,
    ),
}


def policy_digest(purpose: SessionPurpose, actor_role: ActorRole, policy: CapabilityPolicy) -> str:
    """Canonical digest binding purpose, role, version, and capabilities."""

    canonical = json.dumps(
        {
            "purpose": purpose.value,
            "actor_role": actor_role.value,
            "policy_version": POLICY_VERSION,
            "capabilities": policy.model_dump(),
        },
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class TranscriptSource(StrEnum):
    """Audio or fixture origin."""

    MICROPHONE = "microphone"
    PIPEWIRE = "pipewire"
    DEMO = "demo"
    API = "api"


class SessionStatus(StrEnum):
    """Operator-controlled session states."""

    IDLE = "idle"
    # Session exists but consent was never confirmed, so no audio capture is
    # authorized. Distinct from LISTENING so the HUD cannot show "listening"
    # over a session that is not permitted to capture anything.
    ARMED = "armed"
    LISTENING = "listening"
    PAUSED = "paused"
    STOPPED = "stopped"


class RetrievalLane(StrEnum):
    """Evidence-producing lanes."""

    MEMORY = "memory"
    CODE = "code"
    RIPGREP = "ripgrep"
    ASK = "ask"
    BRAVE = "brave"
    DOGPILE = "dogpile"
    DEBUGGER = "debugger"


class LaneState(StrEnum):
    """Runtime health state for one retrieval lane."""

    IDLE = "idle"
    RUNNING = "running"
    OK = "ok"
    DEGRADED = "degraded"
    DISABLED = "disabled"
    ERROR = "error"


class Freshness(StrEnum):
    """Source freshness signals."""

    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"
    EXTERNAL = "external"


class CardStatus(StrEnum):
    """Whether a card has sufficient source-bound support."""

    SUPPORTED = "supported"
    INSUFFICIENT = "insufficient"


class TranscriptEvent(BaseModel):
    """Validated transcript update from one speaker channel."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    schema_id: Literal["live_evidence.transcript_event.v1"] = Field(
        default="live_evidence.transcript_event.v1",
        validation_alias="schema",
        serialization_alias="schema",
    )
    event_id: str = Field(default_factory=lambda: uuid4().hex, min_length=8)
    created_at: datetime = Field(default_factory=utc_now)
    speaker: Speaker
    kind: TranscriptKind
    source: TranscriptSource = TranscriptSource.API
    text: str = Field(min_length=1, max_length=8_000)
    sequence: int | None = Field(default=None, ge=0)
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)

    @field_validator("created_at")
    @classmethod
    def validate_aware_time(cls, value: datetime) -> datetime:
        """Reject naive timestamps because session ordering is provenance."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """Collapse whitespace without changing lexical content."""

        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("text must contain non-whitespace characters")
        return normalized

    @model_validator(mode="after")
    def validate_offsets(self) -> "TranscriptEvent":
        """Keep replay/live transcript offsets ordered when present."""

        if self.start_ms is not None and self.end_ms is not None and self.end_ms < self.start_ms:
            raise ValueError("end_ms must be greater than or equal to start_ms")
        return self


class EventSpan(BaseModel):
    """One transcript event's character span inside a question candidate."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=8)
    sequence: int = Field(ge=0)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_span_order(self) -> "EventSpan":
        """Keep span offsets ordered inside the assembled question."""

        if self.end_offset < self.start_offset:
            raise ValueError("end_offset must be greater than or equal to start_offset")
        return self


class QuestionCandidate(BaseModel):
    """Bounded interviewer question assembled from one or more transcript events."""

    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["live_evidence.question_candidate.v1"] = Field(
        default="live_evidence.question_candidate.v1",
        validation_alias="schema",
        serialization_alias="schema",
    )
    question_id: str = Field(min_length=12, max_length=80)
    normalized_question: str = Field(min_length=1, max_length=1_200)
    speaker: Speaker = Speaker.INTERVIEWER
    source_event_ids: list[str] = Field(min_length=1, max_length=8)
    source_spans: list[EventSpan] = Field(min_length=1, max_length=8)
    start_sequence: int = Field(ge=0)
    end_sequence: int = Field(ge=0)
    trigger_reason: str = Field(min_length=1, max_length=120)
    fingerprint: str = Field(min_length=12, max_length=96)

    @model_validator(mode="after")
    def validate_candidate_bounds(self) -> "QuestionCandidate":
        """Require interviewer-only ordered question provenance."""

        if self.speaker is not Speaker.INTERVIEWER:
            raise ValueError("question candidates must be interviewer turns")
        if self.end_sequence < self.start_sequence:
            raise ValueError("end_sequence must be greater than or equal to start_sequence")
        span_event_ids = [span.event_id for span in self.source_spans]
        if span_event_ids != self.source_event_ids:
            raise ValueError("source_spans must match source_event_ids order")
        return self


class EvidenceSource(BaseModel):
    """One retrievable source candidate with a concrete locator."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, serialize_by_alias=True)

    schema_id: Literal["live_evidence.evidence_source.v1"] = Field(
        default="live_evidence.evidence_source.v1",
        validation_alias="schema",
        serialization_alias="schema",
    )
    source_id: str = Field(default_factory=lambda: uuid4().hex, min_length=8)
    lane: RetrievalLane
    label: str = Field(min_length=1, max_length=240)
    excerpt: str = Field(min_length=1, max_length=4_000)
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    freshness: Freshness = Freshness.UNKNOWN
    repository: str | None = Field(default=None, max_length=300)
    branch: str | None = Field(default=None, max_length=200)
    commit: str | None = Field(default=None, max_length=100)
    path: str | None = Field(default=None, max_length=2_000)
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    url: str | None = Field(default=None, max_length=4_000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_locator(self) -> "EvidenceSource":
        """Require at least one inspectable locator."""

        if not any((self.path, self.url, self.repository, self.metadata.get("_key"))):
            raise ValueError("evidence source requires path, url, repository, or _key")
        if self.line_start and self.line_end and self.line_end < self.line_start:
            raise ValueError("line_end must be greater than or equal to line_start")
        return self


class RequirementKind(StrEnum):
    """What a requirement constrains (#1454). Task-agnostic, not LeetCode-specific."""

    OBJECTIVE = "objective"
    INPUT = "input"
    OUTPUT = "output"
    CONSTRAINT = "constraint"
    EDGE_CASE = "edge_case"
    EVIDENCE = "evidence"
    PROCESS = "process"


class RequirementStatus(StrEnum):
    STATED = "stated"
    CLARIFIED = "clarified"
    ASSUMED = "assumed"
    UNRESOLVED = "unresolved"
    SUPERSEDED = "superseded"


class AnswerSource(StrEnum):
    """Where a clarification answer came from."""

    SPEECH = "speech"
    OPERATOR = "operator"
    DEFAULT_ASSUMPTION = "default_assumption"


class Requirement(BaseModel):
    """One append-only ledger entry bound to transcript evidence (#1454).

    Only transcript-bound or explicit human-entered text may create a
    requirement. A model may normalize wording but cannot invent one: an entry
    with no source events must carry ASSUMED status and a visible
    assumption_source explaining where the assumption came from -- enforced
    here, not by convention.
    """

    model_config = ConfigDict(extra="forbid")

    requirement_id: str = Field(default_factory=lambda: uuid4().hex, min_length=8)
    question_id: str = Field(min_length=8, max_length=64)
    question_revision: int = Field(ge=1)
    kind: RequirementKind
    text: str = Field(min_length=1, max_length=1_000)
    source_event_ids: list[str] = Field(default_factory=list, max_length=16)
    source_spans: list[EventSpan] = Field(default_factory=list, max_length=16)
    status: RequirementStatus = RequirementStatus.STATED
    blocking: bool = False
    clarification_id: str | None = Field(default=None, max_length=80)
    clarification_answer: str | None = Field(default=None, max_length=1_000)
    answer_source: AnswerSource | None = None
    clarification_answer_event_ids: list[str] = Field(default_factory=list, max_length=8)
    assumption_source: str | None = Field(default=None, max_length=400)
    created_at: datetime = Field(default_factory=utc_now)
    supersedes_requirement_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_provenance(self) -> "Requirement":
        """A requirement without transcript evidence must be a labeled assumption."""

        if not self.source_event_ids and self.status is not RequirementStatus.ASSUMED:
            raise ValueError(
                "requirement without source_event_ids must carry ASSUMED status"
            )
        if self.status is RequirementStatus.ASSUMED and not self.assumption_source:
            raise ValueError("ASSUMED requirement must state its assumption_source")
        return self


def ledger_digest(entries: list["Requirement"]) -> str:
    """Canonical digest over the append-only ledger for card binding."""

    canonical = json.dumps(
        [entry.model_dump(mode="json", exclude={"created_at"}) for entry in entries],
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ClarificationItem(BaseModel):
    """One clarifying question the backend decided is worth asking.

    These must be produced by the question resolver, never invented by the
    browser. Before this existed the HUD hard-coded four parentheses prompts
    and showed them whenever a regex matched the card text, which made every
    clarification screenshot unfalsifiable.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=400)
    why_it_matters: str | None = Field(default=None, max_length=400)
    default_assumption: str | None = Field(default=None, max_length=400)
    blocking: bool = False
    answer: str | None = Field(default=None, max_length=400)
    answer_source_event_ids: list[str] = Field(default_factory=list, max_length=8)


class EvidenceCard(BaseModel):
    """Compact human-facing evidence prompt derived only from selected sources."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    schema_id: Literal["live_evidence.evidence_card.v1"] = Field(
        default="live_evidence.evidence_card.v1",
        validation_alias="schema",
        serialization_alias="schema",
    )
    card_id: str = Field(default_factory=lambda: uuid4().hex, min_length=8)
    created_at: datetime = Field(default_factory=utc_now)
    query: str = Field(min_length=1, max_length=8_000)
    thread: str = Field(min_length=1, max_length=180)
    question: str | None = Field(default=None, max_length=8_000)
    answer: str | None = Field(default=None, max_length=1_200)
    evidence: str | None = Field(default=None, max_length=1_500)
    talking_point: str = Field(min_length=1, max_length=800)
    proof: str = Field(min_length=1, max_length=1_200)
    qualifier: str = Field(min_length=1, max_length=800)
    confidence: float = Field(ge=0.0, le=1.0)
    status: CardStatus
    sources: list[EvidenceSource] = Field(default_factory=list, max_length=8)
    lanes: list[RetrievalLane] = Field(default_factory=list)
    clarifications: list[ClarificationItem] = Field(default_factory=list, max_length=6)
    # Question identity, so an answer can be fenced against the question that
    # asked for it. Retrieval plus a solver call runs for tens of seconds, which
    # is long enough for ordinary speech to change the question underneath it;
    # without these a slow result publishes over a newer question.
    question_id: str | None = Field(default=None, min_length=8, max_length=64)
    question_revision: int = Field(default=0, ge=0)
    # Digest of the frozen session policy this card was produced under (#1449).
    policy_digest: str | None = Field(default=None, min_length=64, max_length=64)
    # Digest of the requirement ledger revision this card answers (#1454), plus
    # any assumptions in force, so a reviewer sees what was assumed vs stated.
    ledger_digest: str | None = Field(default=None, min_length=64, max_length=64)
    assumptions: list[str] = Field(default_factory=list, max_length=8)
    pinned: bool = False
    dismissed: bool = False

    @field_validator("created_at")
    @classmethod
    def validate_card_time(cls, value: datetime) -> datetime:
        """Keep card ordering deterministic across clients."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_support_truth(self) -> "EvidenceCard":
        """Supported cards must actually carry sources."""

        if self.status is CardStatus.SUPPORTED and not self.sources:
            raise ValueError("supported card requires at least one evidence source")
        return self


class LaneActivity(BaseModel):
    """Current state and last result for one retrieval lane."""

    model_config = ConfigDict(extra="forbid")

    lane: RetrievalLane
    state: LaneState = LaneState.IDLE
    detail: str = "Waiting"
    latency_ms: int | None = Field(default=None, ge=0)
    result_count: int = Field(default=0, ge=0)
    updated_at: datetime = Field(default_factory=utc_now)


class SessionInfo(BaseModel):
    """Session-level operator state."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(default_factory=lambda: uuid4().hex, min_length=8)
    status: SessionStatus = SessionStatus.IDLE
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    consent_confirmed: bool = False
    profile_name: str = "default"
    purpose: SessionPurpose = SessionPurpose.MEETING
    actor_role: ActorRole = ActorRole.PARTICIPANT
    policy: CapabilityPolicy = Field(default_factory=CapabilityPolicy)
    policy_version: int = POLICY_VERSION
    policy_digest: str = ""
    practice_only: bool = False


class AppSnapshot(BaseModel):
    """Complete state projected to the React client over REST and SSE."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    schema_id: Literal["live_evidence.app_snapshot.v1"] = Field(
        default="live_evidence.app_snapshot.v1",
        validation_alias="schema",
        serialization_alias="schema",
    )
    session: SessionInfo
    current_thread: str = "Waiting for the conversation"
    transcript: list[TranscriptEvent] = Field(default_factory=list, max_length=300)
    cards: list[EvidenceCard] = Field(default_factory=list, max_length=100)
    lanes: list[LaneActivity] = Field(default_factory=list)
    external_search_enabled: bool = False
    updated_at: datetime = Field(default_factory=utc_now)


class SessionStartRequest(BaseModel):
    """Start-session command from the UI."""

    model_config = ConfigDict(extra="forbid")

    consent_confirmed: bool = False
    purpose: SessionPurpose = SessionPurpose.MEETING
    actor_role: ActorRole = ActorRole.PARTICIPANT
    # Explicit capability override; omitted fields take the purpose default.
    policy: CapabilityPolicy | None = None


class ClarificationAnswerRequest(BaseModel):
    """Answer/amendment for one clarification, bound to an exact revision (#1454)."""

    model_config = ConfigDict(extra="forbid")

    question_revision: int = Field(ge=1)
    answer: str = Field(min_length=1, max_length=1_000)
    source: AnswerSource = AnswerSource.OPERATOR
    answer_event_ids: list[str] = Field(default_factory=list, max_length=8)


class VoiceUtteranceRequest(BaseModel):
    """Text the assistant is about to speak aloud (#1453 echo suppression)."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2_000)
    turn_id: str | None = Field(default=None, max_length=120)


class ManualSearchRequest(BaseModel):
    """Explicit bounded retrieval request."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=2, max_length=1_000)
    lane: RetrievalLane = RetrievalLane.MEMORY

    @field_validator("lane")
    @classmethod
    def validate_manual_lane(cls, value: RetrievalLane) -> RetrievalLane:
        """Prevent the code-only lane from being treated as broad search."""

        return value


class ActionDefinition(BaseModel):
    """One QuerySpec-compatible UI action registration."""

    model_config = ConfigDict(extra="forbid")

    element_id: str = Field(min_length=3, max_length=240)
    app: str = Field(min_length=2, max_length=120)
    action: str = Field(pattern=r"^[A-Z][A-Z0-9_]+$", max_length=160)
    label: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=500)
    params: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list, max_length=30)


class ActionRegistrationBatch(BaseModel):
    """Batched UI action definitions."""

    model_config = ConfigDict(extra="forbid")

    actions: list[ActionDefinition] = Field(min_length=1, max_length=200)


class HealthResponse(BaseModel):
    """Service health payload."""

    status: str = "ok"
    version: str
    ui_built: bool
    memory_configured: bool
    repo_count: int


class DoctorCheck(BaseModel):
    """One local readiness check."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["PASS", "DEGRADED", "NOT_CONFIGURED"]
    detail: str = Field(min_length=1, max_length=500)


class DoctorReport(BaseModel):
    """Machine-readable prepared-host readiness report."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
    )

    schema_id: Literal["live_evidence.doctor_report.v1"] = Field(
        default="live_evidence.doctor_report.v1",
        validation_alias="schema",
        serialization_alias="schema",
    )
    status: Literal["READY_FOR_LIVE", "READY_FOR_REPLAY", "NEEDS_SETUP"]
    checks: dict[str, DoctorCheck]


# --- Post-interview review dossier (#1451) -------------------------------


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


# --- Read-only debugger proof lane (#1450) --------------------------------


class DebugBreakpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str = Field(min_length=1, max_length=1_000)
    line: int | None = Field(default=None, ge=1)
    symbol: str | None = Field(default=None, min_length=1, max_length=300)

    @model_validator(mode="after")
    def validate_target(self) -> "DebugBreakpoint":
        if self.line is None and self.symbol is None:
            raise ValueError("breakpoint requires line or symbol")
        return self


class DebugRequest(BaseModel):
    """live_evidence.debug_request.v1 -- bounded, read-only, revision-fenced.

    Binds exact repository identity, the question revision it answers, and the
    frozen session policy (#1449). allowed_effects is a literal: this lane can
    never carry a mutation request.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    schema_id: Literal["live_evidence.debug_request.v1"] = Field(
        default="live_evidence.debug_request.v1",
        validation_alias="schema",
        serialization_alias="schema",
    )
    session_id: str = Field(min_length=8, max_length=64)
    session_policy_digest: str = Field(min_length=64, max_length=64)
    question_id: str = Field(min_length=8, max_length=64)
    question_revision: int = Field(ge=0)
    repository_root: str = Field(min_length=1, max_length=1_000)
    repository_commit_or_tree_digest: str = Field(min_length=8, max_length=128)
    technical_question: str = Field(min_length=1, max_length=8_000)
    reproduction_command: list[str] = Field(min_length=1, max_length=64)
    requested_breakpoints: list[DebugBreakpoint] = Field(min_length=1, max_length=16)
    requested_locals: list[str] = Field(default_factory=list, max_length=32)
    requested_watches: list[str] = Field(default_factory=list, max_length=16)
    debugger_mode: Literal["python_bdb", "vscode_bridge"] = "python_bdb"
    allowed_effects: Literal["read_only"] = "read_only"
    patch_requires_explicit_approval: Literal[True] = True

    def request_digest(self) -> str:
        payload = self.model_dump(mode="json", by_alias=True)
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
