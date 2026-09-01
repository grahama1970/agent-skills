#!/usr/bin/env python3
"""Validate/render agent_ecosystem.membership.v1."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

REQUIRED = {
    "project agents", "triage-error", "shame", "lazy-report-shame-shame-shame extension",
    "status-json-check.mjs", "agent_status_schema.py", "compile-status-command.mjs",
    "agentic-evals", "ask", "tau", "project-watchdog", "ops-herdr", "ponytail",
    "Memory", "agent-ecosystem", "goal-helper",
}

class Member(BaseModel):
    model_config = ConfigDict(extra="forbid")
    component: str = Field(min_length=1)
    owns: str = Field(min_length=1)
    emits: list[str]
    consumes: list[str]
    must: str = Field(min_length=1)

class Membership(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_: str = Field(alias="schema", pattern=r"^agent_ecosystem\.membership\.v1$")
    goal_id: str = Field(pattern=r"^shame-deterministic-instruction-obedience-v1$")
    members: list[Member] = Field(min_length=len(REQUIRED), max_length=len(REQUIRED))

    @model_validator(mode="after")
    def exact_members(self) -> "Membership":
        seen = [m.component for m in self.members]
        if len(seen) != len(set(seen)):
            raise ValueError("duplicate ecosystem member")
        missing = REQUIRED - set(seen)
        extra = set(seen) - REQUIRED
        if missing or extra:
            raise ValueError(f"membership mismatch missing={sorted(missing)} extra={sorted(extra)}")
        return self

def load(path: str) -> Membership:
    raw = sys.stdin.read() if path == "-" else Path(path).read_text()
    return Membership.model_validate_json(raw)

def render_table(m: Membership) -> str:
    lines = ["| Component | Owns | Emits | Consumes | MUST |", "| --- | --- | --- | --- | --- |"]
    for item in m.members:
        lines.append("| " + " | ".join([
            item.component,
            item.owns,
            ", ".join(item.emits) or "none",
            ", ".join(item.consumes) or "none",
            item.must,
        ]) + " |")
    return "\n".join(lines)

def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in {"validate", "table"}:
        print("usage: membership.py validate|table <members.json|->", file=sys.stderr)
        return 2
    try:
        m = load(sys.argv[2])
    except Exception as exc:
        print(json.dumps({"valid": False, "error": str(exc)}))
        return 1
    if sys.argv[1] == "table":
        print(render_table(m))
    else:
        print(json.dumps({"valid": True, "schema": m.schema_, "member_count": len(m.members)}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
