"""Typed cross-layer contracts for Live Evidence.

Inputs arrive from audio callbacks, HTTP clients, subprocesses, YAML, and the
React UI. Pydantic validates those external boundaries before runtime state or
retrieval logic uses the values. The models intentionally keep evidence and
human-facing summaries separate so relevance cannot silently become authority.
"""

from __future__ import annotations

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


class TranscriptSource(StrEnum):
    """Audio or fixture origin."""

    MICROPHONE = "microphone"
    PIPEWIRE = "pipewire"
    DEMO = "demo"
    API = "api"


class SessionStatus(StrEnum):
    """Operator-controlled session states."""

    IDLE = "idle"
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


class LaneState(StrEnum):
    """Runtime health state for one retrieval lane."""

    IDLE = "idle"
    RUNNING = "running"
    OK = "ok"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
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


class ClarificationAnswerRequest(BaseModel):
    """Clarification answers for a blocked automatic coding question."""

    model_config = ConfigDict(extra="forbid")

    answers: dict[str, str] = Field(min_length=1, max_length=20)

    @field_validator("answers")
    @classmethod
    def normalize_answers(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, answer in value.items():
            clean_key = " ".join(str(key).split())[:120]
            clean_answer = " ".join(str(answer).split())[:2_000]
            if clean_key and clean_answer:
                normalized[clean_key] = clean_answer
        if not normalized:
            raise ValueError("answers must contain at least one non-empty answer")
        return normalized


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
