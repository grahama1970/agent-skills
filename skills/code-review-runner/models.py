"""Pydantic models for /code-review-runner spec validation and result schema.

Declarative guardrails — bad types, missing fields, and invalid values
caught at parse time before any validator or LLM call.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ReviewSpec(BaseModel):
    """Input spec for /code-review-runner. Validated before execution."""
    task_id: str = Field(..., min_length=1)
    files: list[str] = Field(..., min_length=1, description="Files to review (must exist)")
    cwd: str = Field(..., min_length=1, description="Working directory (must exist)")
    context: str = Field("", description="Architectural context for the reviewer")
    dod_command: str = Field("", description="Compatibility metadata; not executed by this reviewer")
    backend: str = Field("codex", description="LLM backend: codex, text, gemini, claude")
    output_dir: str = Field("/tmp/code-review-runner", description="Where to write logs and results")
    max_rounds: int = Field(2, ge=1, le=5)
    focus: str = Field("", description="Review focus areas: security, correctness, performance, etc.")
    base_ref: str = Field("", description="Optional git base ref for authoritative diff review")

    @field_validator("cwd")
    @classmethod
    def cwd_must_exist(cls, v: str) -> str:
        if not Path(v).exists():
            raise ValueError(f"cwd does not exist: {v}")
        return v

    @field_validator("backend")
    @classmethod
    def backend_must_be_known(cls, v: str) -> str:
        known = {
            "codex",
            "text",
            "gemini",
            "claude",
            "text-gemini",
            "text-claude",
            "gpt-5.3-codex",
            "gpt-5.5",
        }
        if v and v not in known:
            raise ValueError(f"Unknown backend '{v}'. Valid: {', '.join(sorted(known))}")
        return v

    @field_validator("files")
    @classmethod
    def files_must_not_be_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("files list cannot be empty")
        return v


class T0Violation(BaseModel):
    """A deterministic rule violation found by T0 validators."""
    rule: str = Field(..., description="Rule ID or name (e.g., 'bp-python-loguru', 'ruff-E501')")
    severity: str = Field("minor", description="critical, major, minor, info")
    file: str = Field("", description="File path where violation was found")
    line: int = Field(0, description="Line number (0 = file-level)")
    message: str = Field(..., description="Human-readable violation description")
    source: str = Field("", description="Which validator found this (ruff, best-practices-python, etc.)")


class Finding(BaseModel):
    """A code review finding from the LLM reviewer."""
    id: str = Field("", description="Finding ID (auto-assigned)")
    severity: str = Field("minor", description="critical, major, minor, info")
    file: str = Field(..., description="File path")
    line: int = Field(0, description="Line number")
    description: str = Field(..., description="What's wrong")
    suggested_fix: str = Field("", description="Code snippet or description of fix")
    validated: bool = Field(False, description="False while the suggested fix remains unapplied")
    validation_error: str = Field("", description="Why validation failed (if it did)")
    score: float = Field(0.0, description="Severity-derived impact contribution")

    @property
    def severity_weight(self) -> float:
        return {"critical": 1.0, "major": 0.7, "minor": 0.3, "info": 0.1}.get(self.severity, 0.1)


class RoundResult(BaseModel):
    """Result of a single review round."""
    round: int
    findings: list[Finding] = Field(default_factory=list)
    t0_violations: list[T0Violation] = Field(default_factory=list)
    backend: str = ""
    raw_response: str = ""
    timestamp: float = 0


class ReviewResult(BaseModel):
    """Final output of /code-review-runner."""
    task_id: str
    status: str = Field("pass", description="pass, fail, or error")
    score: float = Field(0.0, description="0.0-1.0 quality score (higher = cleaner code)")
    findings_total: int = 0
    findings_validated: int = 0
    findings_critical: int = 0
    t0_violation_count: int = 0
    rounds: int = 0
    summary: str = ""
    all_findings: list[Finding] = Field(default_factory=list)
    all_t0_violations: list[T0Violation] = Field(default_factory=list)
    round_details: list[dict[str, Any]] = Field(default_factory=list)
    backend: str = ""
