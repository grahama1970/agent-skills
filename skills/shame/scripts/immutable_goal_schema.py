#!/usr/bin/env python3
"""Validate shame.immutable_goal.v1 with pydantic."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


REQUIRED_COMPONENTS = {
    "project agents",
    "shame skill",
    "lazy-report-shame-shame-shame extension",
    "status-json-check.mjs",
    "agent_status_schema.py",
    "compile-status-command.mjs",
    "agentic-evals",
    "agent-ecosystem",
    "triage-error",
    "ask",
    "tau",
    "project-watchdog",
    "ops-herdr",
    "Memory",
    "ponytail",
    "goal-helper",
}

REQUIRED_OUTCOME_PHRASES = [
    "impossible for project agents to ignore explicit instructions",
    "typed pydantic-validated contracts",
    "prose is display only",
]

REQUIRED_PROOF_PHRASES = [
    "immutable_goal_schema.py validate skills/shame/immutable_goal.json",
    "skills/agentic-evals/run.sh run skills/shame/fixtures/agentic_eval.json",
    "READY with zero FAIL/BLOCKED cases",
]


class PrimaryProof(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: str = Field(min_length=1)
    expected: str = Field(min_length=1)


class RetryStopRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempts_per_blocker: int = Field(ge=1, le=2)
    stop_condition: str = Field(min_length=1)


class EcosystemMust(BaseModel):
    model_config = ConfigDict(extra="forbid")
    component: str = Field(min_length=1)
    must: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def must_language_is_normative(self) -> "EcosystemMust":
        for item in self.must:
            if "MUST" not in item:
                raise ValueError(f"{self.component} item lacks MUST language: {item}")
        return self


class ImmutableGoal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_: Literal["shame.immutable_goal.v1"] = Field(alias="schema")
    goal_id: str = Field(min_length=1)
    goal_hash: str = Field(min_length=71, max_length=71)
    outcome: str = Field(min_length=1)
    primary_proof: PrimaryProof
    completion_criteria: list[str] = Field(min_length=1)
    allowed_scope: list[str] = Field(min_length=1)
    forbidden_drift: list[str] = Field(min_length=1)
    retry_stop_rule: RetryStopRule
    ecosystem_must: list[EcosystemMust] = Field(min_length=len(REQUIRED_COMPONENTS))
    final_report_rule: str = Field(min_length=1)

    @model_validator(mode="after")
    def enforce_immutable_goal_contract(self) -> "ImmutableGoal":
        if not self.goal_hash.startswith("sha256:"):
            raise ValueError("goal_hash must start with sha256:")
        digest = self.goal_hash[len("sha256:"):]
        if len(digest) != 64 or not all(ch in "0123456789abcdef" for ch in digest):
            raise ValueError("goal_hash must be sha256: plus 64 lowercase hex chars")
        missing_outcome = [phrase for phrase in REQUIRED_OUTCOME_PHRASES if phrase not in self.outcome]
        if missing_outcome:
            raise ValueError(f"outcome missing required phrases: {missing_outcome}")
        proof_text = self.primary_proof.command + "\n" + self.primary_proof.expected
        missing_proof = [phrase for phrase in REQUIRED_PROOF_PHRASES if phrase not in proof_text]
        if missing_proof:
            raise ValueError(f"primary proof missing required phrases: {missing_proof}")
        components = {item.component for item in self.ecosystem_must}
        missing_components = sorted(REQUIRED_COMPONENTS - components)
        if missing_components:
            raise ValueError(f"ecosystem_must missing components: {missing_components}")
        all_must = "\n".join(line for item in self.ecosystem_must for line in item.must)
        for phrase in ["pydantic", "agentic-evals", "pi.agent_status.v1", "triage-error"]:
            if phrase not in all_must:
                raise ValueError(f"ecosystem_must missing phrase: {phrase}")
        return self


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] != "validate":
        print(__doc__, file=sys.stderr)
        return 2
    raw = sys.stdin.read() if sys.argv[2] == "-" else Path(sys.argv[2]).read_text()
    try:
        goal = ImmutableGoal.model_validate_json(raw)
    except Exception as exc:
        print(json.dumps({"valid": False, "error": str(exc)}))
        return 1
    print(json.dumps({
        "valid": True,
        "schema": goal.schema_,
        "goal_id": goal.goal_id,
        "goal_hash": goal.goal_hash,
        "component_count": len(goal.ecosystem_must),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
