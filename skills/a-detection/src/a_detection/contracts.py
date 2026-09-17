"""Strict external schemas for consent, Unicode edits, model scores, and evidence."""
from typing import Annotated, Literal

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Identifier = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False, frozen=True)

class Policy(Strict):
    schema_version: Literal["a_detection.policy.v1"] = "a_detection.policy.v1"
    max_source_chars: int = Field(default=64000, ge=100, le=128000)
    max_events: int = Field(default=4000, ge=1, le=20000)
    max_sessions: int = Field(default=256, ge=1, le=10000)
    duration_seconds: int = Field(default=900, ge=1, le=7200)
    retention_seconds: int = Field(default=86400, ge=60, le=604800)
    min_code_chars: int = Field(default=80, ge=1, le=1000)
    target_fpr: float = Field(default=0.01, gt=0, lt=0.1)
    confidence: float = Field(default=0.95, gt=0.5, lt=1)
    automatic_penalties: Literal[False] = False
    external_provider_uploads: Literal[False] = False
    behavioral_authorship_scoring: Literal[False] = False

    @field_validator("automatic_penalties", "external_provider_uploads",
                     "behavioral_authorship_scoring", mode="before")
    @classmethod
    def strictly_false(cls, value):
        if type(value) is not bool or value is not False:
            raise ValueError("This safety policy accepts only the JSON boolean false.")
        return value

class SessionRequest(Strict):
    consent: bool
    language: Literal["python", "javascript", "java", "go"] = "python"

    @field_validator("consent")
    @classmethod
    def require_consent(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("Explicit informed consent is required.")
        return value

class Edit(Strict):
    event_id: Identifier
    seq: int = Field(ge=1, le=20000)
    base_revision: int = Field(ge=0, le=20000)
    start: int = Field(ge=0, le=128000)
    delete_count: int = Field(ge=0, le=128000)
    insert_text: str = Field(max_length=128000)
    after_sha256: Sha256
    kind: Literal["input", "paste", "undo", "redo", "composition", "unknown"] = "unknown"
    client_elapsed_ms: float = Field(ge=0, le=86400000)

    @field_validator("insert_text")
    @classmethod
    def unicode_scalar_text(cls, value: str) -> str:
        try:
            value.encode("utf-8")
        except UnicodeError as exc:
            logger.error("classified_failure module=contracts")
            raise ValueError("Text must contain valid Unicode scalar values.") from exc
        return value

class Submit(Strict):
    revision: int = Field(ge=0, le=20000)
    source_sha256: Sha256

class EventReceipt(Strict):
    schema_version: Literal["a_detection.event_receipt.v1"] = "a_detection.event_receipt.v1"
    session_id: Identifier
    revision: int = Field(ge=1)
    event: Edit
    received_at: float = Field(ge=0)
    previous_sha256: Sha256
    receipt_sha256: Sha256

class Analysis(Strict):
    schema_version: Literal["a_detection.analysis.v1"] = "a_detection.analysis.v1"
    disposition: Literal["INSUFFICIENT_EVIDENCE", "REVIEW_SUGGESTED", "NO_ELEVATED_SIGNAL"]
    source_sha256: Sha256
    authorship_established: Literal[False] = False
    automatic_penalty: Literal[False] = False
    raw_classifier_score: float | None = Field(default=None, ge=0, le=1)
    model_sha256: Sha256 | None = None
    calibration_qualified: bool = False
    reasons: list[str]
    observations: dict[str, int | float | str | bool]
    limitations: list[str]

    @field_validator("authorship_established", "automatic_penalty", mode="before")
    @classmethod
    def no_authorship_or_penalty(cls, value):
        if type(value) is not bool or value is not False:
            raise ValueError("Only the JSON boolean false is admitted.")
        return value

    @model_validator(mode="after")
    def evidence_matches_disposition(self):
        if (self.raw_classifier_score is None) != (self.model_sha256 is None):
            raise ValueError("A model score and its identity must appear together.")
        if self.disposition != "INSUFFICIENT_EVIDENCE" and (
                not self.calibration_qualified or self.raw_classifier_score is None):
            raise ValueError("A non-abstaining result requires a qualified, identified model score.")
        if self.calibration_qualified and self.raw_classifier_score is None:
            raise ValueError("Calibration cannot qualify absent model evidence.")
        return self

class EvidenceExport(Strict):
    schema_version: Literal["a_detection.session_export.v1"] = "a_detection.session_export.v1"
    session_id: Identifier
    language: str
    created_at: float
    expires_at: float
    submitted_at: float | None
    policy_sha256: Sha256
    initial_source: Literal[""] = ""
    events: list[EventReceipt]
    source: str
    revision: int
    source_sha256: Sha256
    head_sha256: Sha256
    analysis: Analysis | None
    client_evidence_trust: Literal["UNTRUSTED_CLIENT_REPORT"] = "UNTRUSTED_CLIENT_REPORT"

class Health(Strict):
    schema_version: Literal["a_detection.health.v1"] = "a_detection.health.v1"
    status: Literal["ok"] = "ok"
    evidence_mode: Literal["local_research"] = "local_research"
    efficacy: Literal["NOT_ESTABLISHED"] = "NOT_ESTABLISHED"


class SessionCreated(Strict):
    schema_version: Literal["a_detection.session_created.v1"] = "a_detection.session_created.v1"
    session_id: Identifier
    token: str = Field(min_length=20, max_length=200)
    created_at: float
    expires_at: float
    server_now: float
    revision: Literal[0] = 0
    source_sha256: Sha256
    policy_sha256: Sha256

    @model_validator(mode="after")
    def valid_time_window(self):
        if self.expires_at <= self.created_at or self.server_now != self.created_at:
            raise ValueError("Session creation time window is inconsistent.")
        return self


class Deletion(Strict):
    schema_version: Literal["a_detection.deletion.v1"] = "a_detection.deletion.v1"
    deleted: Literal[True] = True
    scope: Literal["active_database_rows"] = "active_database_rows"
    secure_erasure_guaranteed: Literal[False] = False


class ReplayVerification(Strict):
    schema_version: Literal["a_detection.replay_verification.v1"] = "a_detection.replay_verification.v1"
    status: Literal["PASS"] = "PASS"
    session_id: Identifier
    event_count: int = Field(ge=0)
    source_sha256: Sha256
    head_sha256: Sha256
    proves: str
    does_not_prove: str
