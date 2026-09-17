"""Closed error codes and typed, source-redacted error envelopes for all entrypoints."""
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Code(StrEnum):
    INVALID_INPUT = "invalid_input"
    UNAUTHORIZED = "unauthorized"
    CONSENT_REQUIRED = "consent_required"
    NOT_FOUND = "not_found"
    CONFLICT = "revision_conflict"
    EXPIRED = "assessment_expired"
    LIMIT = "resource_limit"
    INTEGRITY = "evidence_integrity"
    MODEL = "model_unavailable"
    LEAKAGE = "dataset_leakage"
    BLOCKED = "external_evidence_missing"
    INTERNAL = "internal_error"

class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: str
    loc: list[str | int]
    msg: str
    ctx: dict[str, str | int | float | bool] = Field(default_factory=dict)

class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["ai_detection.error.v1"] = "ai_detection.error.v1"
    code: Code
    cause: str
    next_command: str
    validation_errors: list[ValidationIssue] = Field(default_factory=list)

class DetectionError(Exception):
    """A classified failure containing no submitted source or authentication tokens."""
    def __init__(self, code: Code, cause: str, status: int = 400):
        super().__init__(cause)
        self.code, self.cause, self.status = code, cause, status


def envelope(error: DetectionError) -> ErrorEnvelope:
    return ErrorEnvelope(code=error.code, cause=error.cause,
                         next_command="ai-detection doctor")
