#!/usr/bin/env python3
"""lazy_report_shame.continuation_guard.v1 validator/writer."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

class Ticket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str = Field(min_length=1)
    state: str = Field(min_length=1)
    labels: list[str] = []
    next_command: str | None = None

class Gate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    proof: str | None = None
    next_command: str | None = None

class ContinuationGuard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_: Literal["lazy_report_shame.continuation_guard.v1"] = Field(alias="schema")
    active: bool
    target: str = Field(min_length=1)
    tickets: list[Ticket] = []
    gates: list[Gate] = []
    obvious_next_steps: list[str] = []

    @model_validator(mode="after")
    def active_requires_machine_work(self) -> "ContinuationGuard":
        if self.active and not (self.tickets or self.gates or self.obvious_next_steps):
            raise ValueError("active continuation guard requires tickets, gates, or obvious_next_steps")
        return self

def load(path: str) -> ContinuationGuard:
    raw = sys.stdin.read() if path == "-" else Path(path).read_text()
    return ContinuationGuard.model_validate_json(raw)

def main() -> int:
    if len(sys.argv) < 3 or sys.argv[1] not in {"validate", "write"}:
        print("usage: continuation_guard_schema.py validate <file|-> | write <out> <target> <next_command>", file=sys.stderr)
        return 2
    if sys.argv[1] == "validate":
        try:
            guard = load(sys.argv[2])
        except Exception as exc:
            print(json.dumps({"valid": False, "error": str(exc)}))
            return 1
        print(json.dumps({"valid": True, "active": guard.active, "target": guard.target}))
        return 0
    if len(sys.argv) != 5:
        print("usage: continuation_guard_schema.py write <out> <target> <next_command>", file=sys.stderr)
        return 2
    data = {
        "schema": "lazy_report_shame.continuation_guard.v1",
        "active": True,
        "target": sys.argv[3],
        "tickets": [],
        "gates": [],
        "obvious_next_steps": [sys.argv[4]],
    }
    guard = ContinuationGuard.model_validate(data)
    Path(sys.argv[2]).parent.mkdir(parents=True, exist_ok=True)
    Path(sys.argv[2]).write_text(json.dumps(guard.model_dump(by_alias=True), indent=2) + "\n")
    print(json.dumps({"valid": True, "path": sys.argv[2], "target": guard.target}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
