"""Typed contracts for qra-grade-advice.

Inputs are QRA pool items or local fixtures. Outputs are advisory grade packets
for Graham review. Failures are Pydantic validation errors; this module does no
network or filesystem IO.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceQuote(BaseModel):
    """Source text available for QRA evidence checks."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    source_id: str | None = None
    title: str | None = None
    quote: str
    locator: str | None = None


class QraItem(BaseModel):
    """Inbound leased QRA item."""

    model_config = ConfigDict(extra="forbid")

    schema: Literal["qra_pool.item.v1"]
    id: str
    question: str = Field(min_length=1)
    reasoning: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    sources: list[SourceQuote] = Field(default_factory=list)
    source_context: list[SourceQuote] = Field(default_factory=list)
    rubric: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    provider_restrictions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    enable_browser_advisor_panel: bool = False
    browser_advisor_panel_receipt: dict[str, Any] | None = None
    enable_graham_style_draft: bool = False


class Finding(BaseModel):
    """One concrete finding or objection."""

    model_config = ConfigDict(extra="forbid")

    severity: Literal["blocker", "high", "medium", "low", "info"]
    category: str
    location: str
    evidence: str
    smallest_fix: str | None = None


class LaneReceipt(BaseModel):
    """One lane execution/value receipt."""

    model_config = ConfigDict(extra="forbid")

    lane: str
    status: Literal["pass", "warn", "fail", "skipped"]
    latency_seconds: float = Field(ge=0)
    findings_count: int = Field(ge=0)
    notes: list[str] = Field(default_factory=list)


class QraAdvice(BaseModel):
    """Outbound advisory packet."""

    model_config = ConfigDict(extra="forbid")

    schema: Literal["qra_grade_advice.v1"]
    qra_id: str
    grade: Literal["pass", "weak_pass", "revise", "reject", "abstain"]
    confidence: Literal["low", "medium", "high"]
    grade_rationale: dict[str, str]
    evidence_findings: list[Finding] = Field(default_factory=list)
    code_smell_findings: list[Finding] = Field(default_factory=list)
    security_findings: list[Finding] = Field(default_factory=list)
    research_findings: list[Finding] = Field(default_factory=list)
    humanization_findings: list[Finding] = Field(default_factory=list)
    best_practice_violations: list[dict[str, Any]] = Field(default_factory=list)
    rewrite_advice_for_graham: dict[str, list[str]]
    optional_graham_style_draft: dict[str, Any]
    browser_advisor_decision: Literal["skip", "escalate", "calibration"]
    do_not_submit: list[str]
    lane_receipts: list[LaneReceipt]
