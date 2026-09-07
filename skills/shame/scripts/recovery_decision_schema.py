#!/usr/bin/env python3
"""Typed recovery routing for shame report rejections."""
from __future__ import annotations

import json
import sys
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

FORMAT_CODES = {"missing_agent_status_json", "duplicate_agent_status_key", "missing_answer_to_question", "missing_immutable_goal_headline"}
EXISTING_PROOF_CODES = {"proof_json_schema_missing", "proof_schema_unsupported", "ticket_closure_receipt_not_closed"}
MISSING_EVIDENCE_CODES = {"proof_reference_unresolved", "proof_path_missing", "proof_empty", "done_requires_proof", "done_requires_verified", "verified_not_backed_by_proof"}
VALIDATOR_CODES = {"validator_script_missing", "validator_invocation_failed", "validator_crashed", "duplicate_detector_failed"}
UNRESOLVED_CODES = {"continuation_guard_unresolved_work", "task_acceptance_checks_incomplete", "task_budget_exhausted"}
ACCEPTED_TASK_CODES = {"task_already_accepted"}


class RecoveryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema: Literal["lazy_report_shame.recovery_input.v1"]
    reason_codes: list[str] = Field(min_length=1)
    retried: bool = False
    task_phase: str | None = None
    next_command: str | None = None


class RecoveryDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema: Literal["lazy_report_shame.recovery_decision.v1"] = "lazy_report_shame.recovery_decision.v1"
    action: Literal["output_only_repair", "existing_proof_substitution", "continue_execution", "validator_failure", "stop_retry"]
    format_only: bool
    allowed_tools: list[str]
    reason: str = Field(min_length=1)
    next_command: str | None = None

    @model_validator(mode="after")
    def tools_match_action(self) -> "RecoveryDecision":
        if self.format_only and self.allowed_tools:
            raise ValueError("format-only recovery cannot allow tools")
        return self


def decide(payload: RecoveryInput) -> RecoveryDecision:
    codes = set(payload.reason_codes)
    if payload.retried:
        return RecoveryDecision(action="stop_retry", format_only=True, allowed_tools=[], reason="status_contract_retry_exhausted")
    if codes & VALIDATOR_CODES:
        return RecoveryDecision(action="validator_failure", format_only=False, allowed_tools=[], reason="status_validator_failed")
    if codes & UNRESOLVED_CODES:
        return RecoveryDecision(action="continue_execution", format_only=False, allowed_tools=[], reason="unresolved_work", next_command=payload.next_command)
    if payload.task_phase == "accepted" or codes & ACCEPTED_TASK_CODES:
        return RecoveryDecision(action="output_only_repair", format_only=True, allowed_tools=[], reason="accepted_task_report_repair")
    if codes <= FORMAT_CODES:
        return RecoveryDecision(action="output_only_repair", format_only=True, allowed_tools=[], reason="format_repair")
    if codes & EXISTING_PROOF_CODES:
        return RecoveryDecision(action="existing_proof_substitution", format_only=True, allowed_tools=[], reason="cite_existing_typed_receipt")
    if codes & MISSING_EVIDENCE_CODES:
        return RecoveryDecision(action="continue_execution", format_only=False, allowed_tools=[], reason="missing_executable_evidence", next_command=payload.next_command)
    return RecoveryDecision(action="output_only_repair", format_only=True, allowed_tools=[], reason="status_field_repair")


def invalid(errors: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema": "lazy_report_shame.recovery_decision.validation_result.v1", "valid": False, "errors": errors}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] != "decide":
        print(__doc__, file=sys.stderr)
        return 2
    try:
        payload = RecoveryInput.model_validate_json(sys.stdin.read())
        print(decide(payload).model_dump_json(indent=2))
        return 0
    except ValidationError as exc:
        print(json.dumps(invalid(exc.errors(include_url=False))))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
