#!/usr/bin/env python3
"""Validate bounded lazy_report_shame.retry_request.v1 packets."""
from __future__ import annotations

import json
import sys
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

MAX_BYTES = 8192


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proof: str = Field(min_length=1)
    digest: str | None = None
    schema_name: str | None = Field(default=None, alias="schema")
    validation: Literal["admitted", "rejected", "unreadable"]
    reason_codes: list[str] = Field(default_factory=list)


class RecoveryDecision(BaseModel):
    model_config = ConfigDict(extra="allow")
    schema: Literal["lazy_report_shame.recovery_decision.v1"]
    action: str = Field(min_length=1)
    format_only: bool
    allowed_tools: list[str]
    reason: str = Field(min_length=1)


class RetryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema: Literal["lazy_report_shame.retry_request.v1"]
    format_only: bool
    allowed_tools: list[str]
    max_corrections: int = Field(ge=1, le=1)
    candidate_hash: str = Field(min_length=1)
    checker: str = Field(min_length=1)
    reason_codes: list[str] = Field(min_length=1)
    diagnostics_sha256: str | None = None
    review_packet: str = Field(min_length=1)
    validation_result: dict[str, Any]
    recovery_decision: RecoveryDecision
    evidence_snapshot: list[EvidenceRef] = Field(default_factory=list)
    next: dict[str, Any]

    @model_validator(mode="after")
    def bounded_and_tool_safe(self) -> "RetryRequest":
        if self.format_only and self.allowed_tools:
            raise ValueError("format-only retry cannot allow tools")
        size = len(self.model_dump_json(by_alias=True).encode())
        if size > MAX_BYTES:
            raise ValueError("retry_request_too_large")
        return self


def invalid(errors: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "lazy_report_shame.retry_request.validation_result.v1",
        "valid": False,
        "errors": [
            {
                "type": str(error.get("type") or "invalid_retry_request"),
                "loc": [str(part) for part in error.get("loc", ())],
                "msg": str(error.get("msg") or "invalid retry request"),
                "ctx": {k: str(v) for k, v in (error.get("ctx") or {}).items()} if isinstance(error.get("ctx"), dict) else {},
            }
            for error in errors
        ],
    }


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] != "validate":
        print(__doc__, file=sys.stderr)
        return 2
    try:
        RetryRequest.model_validate_json(sys.stdin.read())
        print(json.dumps({"schema": "lazy_report_shame.retry_request.validation_result.v1", "valid": True}))
        return 0
    except ValidationError as exc:
        print(json.dumps(invalid(exc.errors(include_url=False))))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
