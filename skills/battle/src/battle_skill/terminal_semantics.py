"""Judge-backed terminal acceptance for receipt consumers; no target execution.

A candidate names the exact Judge bytes, not a claimed authority label alone.
This validates retained evidence, not a new replay or cryptographic authorship.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

TerminalState = Literal["BLUE_SUCCESS", "RED_SUCCESS", "INSUFFICIENT_EVIDENCE", "BLOCKED", "UNAVAILABLE"]
SUPPORTED_TERMINAL_STATES = ("BLUE_SUCCESS", "RED_SUCCESS", "INSUFFICIENT_EVIDENCE", "BLOCKED", "UNAVAILABLE")
UNSUPPORTED_TERMINAL_ALIASES = {"kill", "promotion", "fastest_crash"}
JUDGE_SCHEMA = "battle.arena_tau_public_only_judge_receipt.v1"


class JudgeAttempt(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    schema_: Literal["battle.arena_tau_public_only_pair_attempt_receipt.v1"] = Field(alias="schema")
    status: Literal["PASS", "INSUFFICIENT_EVIDENCE"]
    verdict: TerminalState
    exploit_confirmed_before_patch: bool
    exploit_blocked_after_patch: bool
    exploit_still_succeeds_after_patch: bool
    functionality_preserved: bool
    judge_input_byte_binding_pass: bool
    container_input_hash_pass: bool
    commands_run: list[dict[str, Any]] = Field(min_length=2)

    @model_validator(mode="after")
    def outcome_matches_observations(self) -> "JudgeAttempt":
        confirmed = self.exploit_confirmed_before_patch and self.judge_input_byte_binding_pass and self.container_input_hash_pass
        expected = ("BLUE_SUCCESS" if self.exploit_blocked_after_patch and self.functionality_preserved else "RED_SUCCESS") if confirmed else "INSUFFICIENT_EVIDENCE"
        if self.exploit_blocked_after_patch == self.exploit_still_succeeds_after_patch:
            raise ValueError("contradictory_exploit_observations")
        if self.verdict != expected or self.status != ("PASS" if confirmed else "INSUFFICIENT_EVIDENCE"):
            raise ValueError("judge_attempt_outcome_mismatch")
        return self


class JudgeReceipt(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    schema_: Literal["battle.arena_tau_public_only_judge_receipt.v1"] = Field(alias="schema")
    status: Literal["PASS", "INSUFFICIENT_EVIDENCE", "BLOCKED", "UNAVAILABLE"]
    verdict: TerminalState
    attempts: list[JudgeAttempt]

    @model_validator(mode="after")
    def verdict_matches_attempts(self) -> "JudgeReceipt":
        if self.verdict in {"BLOCKED", "UNAVAILABLE"}:
            if self.status != self.verdict or self.attempts:
                raise ValueError("nonexecuted_judge_state_mismatch")
            return self
        verdicts = {a.verdict for a in self.attempts}
        expected = "BLUE_SUCCESS" if "BLUE_SUCCESS" in verdicts else "RED_SUCCESS" if "RED_SUCCESS" in verdicts else "INSUFFICIENT_EVIDENCE"
        expected_status = "PASS" if expected != "INSUFFICIENT_EVIDENCE" else expected
        if self.verdict != expected or self.status != expected_status:
            raise ValueError("judge_verdict_not_backed_by_attempts")
        return self


class TerminalCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    terminal_state: TerminalState
    source_schema: Literal["battle.arena_tau_public_only_judge_receipt.v1"]
    source_authority: Literal["judge"]
    source_status: str
    judge_receipt: str = Field(min_length=1)
    judge_receipt_sha256: str = Field(pattern=r"^(sha256:)?[a-f0-9]{64}$")
    judge_verdict: TerminalState | None = None
    crash_observation_only: Literal[False] = False


def judge_candidate(path: Path, *, terminal_state: str | None = None) -> dict[str, Any]:
    """Derive a candidate from one read of a real Judge receipt."""
    data = path.read_bytes()
    raw = json.loads(data)
    if not isinstance(raw, dict):
        raise ValueError("judge_receipt_not_object")
    return {
        "terminal_state": terminal_state if terminal_state is not None else raw.get("verdict"),
        "source_schema": raw.get("schema"), "source_authority": "judge",
        "source_status": raw.get("status"), "judge_verdict": raw.get("verdict"),
        "judge_receipt": str(path.resolve()),
        "judge_receipt_sha256": hashlib.sha256(data).hexdigest(),
    }


def evaluate_terminal_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        return {"decision": "REJECT", "reason": "terminal_candidate_not_object"}
    state = candidate.get("terminal_state")
    if isinstance(state, str) and state in UNSUPPORTED_TERMINAL_ALIASES:
        return {"decision": "REJECT", "reason": "unsupported_terminal_alias", "terminal_state": state}
    try:
        c = TerminalCandidate.model_validate(candidate)
        path = Path(c.judge_receipt)
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != c.judge_receipt_sha256.removeprefix("sha256:"):
            raise ValueError("judge_receipt_sha256_mismatch")
        judge = JudgeReceipt.model_validate_json(data)
        if c.terminal_state != judge.verdict or c.source_status != judge.status:
            raise ValueError("terminal_state_not_judge_verdict")
        if c.judge_verdict is not None and c.judge_verdict != judge.verdict:
            raise ValueError("claimed_judge_verdict_mismatch")
    except (OSError, ValueError) as exc:
        return {"decision": "REJECT", "reason": "typed_terminal_evidence_rejected", "terminal_state": state, "error": str(exc)}
    return {
        "decision": "ACCEPT", "reason": "typed_terminal_evidence_accepted",
        "terminal_state": judge.verdict, "source_schema": JUDGE_SCHEMA,
        "source_authority": "judge", "judge_receipt": str(path.resolve()),
        "judge_receipt_sha256": digest, "judged_pair_count": len(judge.attempts),
    }


def require_judge_terminal(path: Path, *, expected_state: str | None = None) -> str:
    result = evaluate_terminal_candidate(judge_candidate(path, terminal_state=expected_state))
    if result["decision"] != "ACCEPT":
        raise ValueError(f"terminal_evidence_rejected: {result}")
    return result["terminal_state"]
