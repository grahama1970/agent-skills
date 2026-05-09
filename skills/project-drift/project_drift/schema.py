"""Pydantic schema for project-drift reports."""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, ConfigDict


class Verdict(str, Enum):
    no_action = "no_action"
    info = "info"
    warn = "warn"
    block = "block"


class Severity(str, Enum):
    none = "none"
    low = "low"
    medium = "medium"
    high = "high"


class DriftKind(str, Enum):
    contradiction = "contradiction"
    stale_status = "stale_status"
    workflow_drift = "workflow_drift"
    contract_drift = "contract_drift"
    resolved_open_question = "resolved_open_question"
    new_blocking_question = "new_blocking_question"
    missing_high_impact_knowledge = "missing_high_impact_knowledge"


class RecommendedAction(str, Enum):
    no_action = "no_action"
    review_update = "review_update"
    review_decision = "review_decision"
    review_open_question = "review_open_question"
    block_until_reviewed = "block_until_reviewed"


class Confidence(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class EvidenceType(str, Enum):
    transcript_excerpt = "transcript_excerpt"
    tool_call = "tool_call"
    command = "command"
    artifact = "artifact"
    file = "file"
    verifier = "verifier"
    commit = "commit"
    human_statement = "human_statement"


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: EvidenceType
    value: str = Field(..., min_length=1)


class DriftCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    kind: DriftKind
    affected_section: str = Field(..., min_length=1)
    current_project_knowledge_claim: str = Field(..., min_length=1)
    new_evidence: str = Field(..., min_length=1)
    why_it_matters: str = Field(..., min_length=1)
    recommended_action: RecommendedAction
    suggested_project_knowledge_update: str = Field(..., min_length=0)
    confidence: Confidence
    evidence: list[EvidenceRef]


class IgnoredSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    routine_successful_tool_calls: int = Field(..., ge=0)
    reason: str = Field(..., min_length=1)


class ProjectDriftReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Verdict
    severity: Severity
    summary: str = Field(..., min_length=1)
    candidates: list[DriftCandidate]
    ignored: IgnoredSummary


def report_json_schema() -> dict[str, Any]:
    """Return the strict JSON schema used by prompt payloads."""
    return ProjectDriftReport.model_json_schema()


def openai_response_format() -> dict[str, Any]:
    """OpenAI-compatible response_format envelope."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "project_drift_report",
            "strict": True,
            "schema": report_json_schema(),
        },
    }
