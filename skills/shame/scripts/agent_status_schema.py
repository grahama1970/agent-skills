#!/usr/bin/env python3
"""pi.agent_status.v1 — single JSON status report for agent turns.

Ambiguous blocker labels are unrepresentable: a blocked state requires a
triage code that exists in the triage-error catalog or matches the minted
``*_unclassified_<8hex>`` shape. Validate with:

    python3 status_schema.py validate <file.json>   # exit 0 pass, 1 fail
    echo '{...}' | python3 status_schema.py validate -
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CATALOG_PATH = Path(__file__).resolve().parents[3] / "skills/triage-error/failure_codes.json"
MINTED_CODE_RE = re.compile(r"^[a-z0-9_]+_unclassified_[0-9a-f]{8}$")


def catalog_codes() -> frozenset[str]:
    data = json.loads(CATALOG_PATH.read_text())
    return frozenset(entry["code"] for entry in data["codes"])


class VerifiedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: str = Field(min_length=1)
    result: str = Field(min_length=1)


class NotDoneItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item: str = Field(min_length=1)
    next_command: str = Field(min_length=1)


class Triage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    cause: str = Field(min_length=1)
    next_command: str | None = None

    @field_validator("code")
    @classmethod
    def code_must_be_unambiguous(cls, value: str) -> str:
        if value in catalog_codes() or MINTED_CODE_RE.fullmatch(value):
            return value
        raise ValueError(
            f"ambiguous blocker label {value!r}: not in triage-error catalog and "
            "not a minted *_unclassified_<8hex> code; run "
            "skills/triage-error/run.sh classify first"
        )


class Blocker(BaseModel):
    model_config = ConfigDict(extra="forbid")
    triage: Triage
    escalation_rung: int = Field(ge=0, le=2, default=0)


class AgentStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_: Literal["pi.agent_status.v1"] = Field(alias="schema")
    goal: str = Field(min_length=1)
    state: Literal["done", "continuing", "blocked"]
    changed: list[str] = []
    verified: list[VerifiedItem] = []
    proof: list[str] = []
    not_done: list[NotDoneItem] = []
    blocker: Blocker | None = None

    @model_validator(mode="after")
    def state_legality(self) -> "AgentStatus":
        if self.state == "blocked" and self.blocker is None:
            raise ValueError("state=blocked requires blocker.triage with a canonical code")
        if self.state != "blocked" and self.blocker is not None:
            raise ValueError("blocker is only legal with state=blocked")
        if self.state == "continuing" and not self.not_done:
            raise ValueError("state=continuing requires not_done[].next_command")
        if self.state == "done":
            if not self.verified:
                raise ValueError("state=done requires non-empty verified")
            if not self.proof:
                raise ValueError("state=done requires non-empty proof")
        return self


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] != "validate":
        print(__doc__, file=sys.stderr)
        return 2
    raw = sys.stdin.read() if sys.argv[2] == "-" else Path(sys.argv[2]).read_text()
    try:
        status = AgentStatus.model_validate_json(raw)
    except Exception as exc:  # pydantic ValidationError or JSON error
        print(json.dumps({"valid": False, "error": str(exc)}))
        return 1
    print(json.dumps({"valid": True, "state": status.state}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
