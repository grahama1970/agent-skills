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
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CATALOG_PATH = Path(__file__).resolve().parents[2] / "skills/triage-error/failure_codes.json"
def is_minted_code(value: str) -> bool:
    """Exact-shape check for minted ``<prefix>_unclassified_<8hex>`` codes. No regex."""
    marker = "_unclassified_"
    idx = value.rfind(marker)
    if idx <= 0:
        return False
    prefix, suffix = value[:idx], value[idx + len(marker):]
    if len(suffix) != 8 or not all(c in "0123456789abcdef" for c in suffix):
        return False
    return all(c.islower() or c.isdigit() or c == "_" for c in prefix)


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
        if value in catalog_codes() or is_minted_code(value):
            return value
        raise ValueError(
            f"ambiguous failure label {value!r}: not in triage-error catalog and "
            "not a minted *_unclassified_<8hex> code; run "
            "skills/triage-error/run.sh classify first"
        )


class NeedsHuman(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(min_length=1, description="Exact human action required, e.g. 'run /reload'")
    reason: str = Field(min_length=1)


class NeedsBraveSearch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    queries: list[str] = Field(min_length=1)


class NeedsAgent(BaseModel):
    """Cross-provider-family fast single-call when the project agent is spiraling."""
    model_config = ConfigDict(extra="forbid")
    handler: str = Field(min_length=1, description="Cross-family handler, e.g. claude-fable-low")
    question: str = Field(min_length=1)


class NeedsWebgpt(BaseModel):
    """Only legal after brave-search and cross-family agent rungs failed to unblock."""
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1)
    brave_search_receipt: str = Field(min_length=1, description="Path to the rung-0 receipt")
    agent_receipt: str = Field(min_length=1, description="Path to the rung-1 receipt")


class NeedsRoundtable(BaseModel):
    """Between-milestone deliberation via $ask tau-dag roundtable."""
    model_config = ConfigDict(extra="forbid")
    immutable_goal: str = Field(min_length=1)
    question: str = Field(min_length=1)
    handlers: list[str] = Field(min_length=3, description="Roundtable quorum floor is 3 answering seats")


class NeedsCompetition(BaseModel):
    """Isolated candidates via $ask compete."""
    model_config = ConfigDict(extra="forbid")
    immutable_goal: str = Field(min_length=1)
    task: str = Field(min_length=1)
    handlers: list[str] = Field(min_length=2)
    criteria: list[str] = Field(min_length=1)


class Failure(BaseModel):
    model_config = ConfigDict(extra="forbid")
    triage: Triage
    escalation_rung: int = Field(ge=0, le=2, default=0)


class AgentStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_: Literal["pi.agent_status.v1"] = Field(alias="schema")
    goal: str = Field(min_length=1)
    goal_id: str | None = None
    goal_hash: str | None = Field(
        default=None,
        description="Immutable goal hash from the Tau goal packet (sha256:<64hex>); enables turn-level drift detection",
    )
    state: Literal[
        "done", "continuing", "needs_human", "failed",
        "needs_brave_search", "needs_agent", "needs_webgpt",
        "needs_roundtable", "needs_competition",
    ]
    changed: list[str] = []
    verified: list[VerifiedItem] = []
    proof: list[str] = []
    not_done: list[NotDoneItem] = []
    failure: Failure | None = None
    needs_human: NeedsHuman | None = None
    needs_brave_search: NeedsBraveSearch | None = None
    needs_agent: NeedsAgent | None = None
    needs_webgpt: NeedsWebgpt | None = None
    needs_roundtable: NeedsRoundtable | None = None
    needs_competition: NeedsCompetition | None = None

    @field_validator("goal_hash")
    @classmethod
    def goal_hash_shape(cls, value: str | None) -> str | None:
        if value is None:
            return value
        prefix = "sha256:"
        if not value.startswith(prefix):
            raise ValueError("goal_hash must start with sha256:")
        digest = value[len(prefix):]
        if len(digest) != 64 or not all(c in "0123456789abcdef" for c in digest):
            raise ValueError("goal_hash digest must be 64 lowercase hex chars")
        return value

    @model_validator(mode="after")
    def state_legality(self) -> "AgentStatus":
        if self.state == "failed" and self.failure is None:
            raise ValueError("state=failed requires failure.triage with a canonical code")
        if self.state != "failed" and self.failure is not None:
            raise ValueError("failure is only legal with state=failed")
        if self.state == "continuing" and not self.not_done:
            raise ValueError("state=continuing requires not_done[].next_command")
        payload_states = {
            "needs_human": "needs_human",
            "needs_brave_search": "needs_brave_search",
            "needs_agent": "needs_agent",
            "needs_webgpt": "needs_webgpt",
            "needs_roundtable": "needs_roundtable",
            "needs_competition": "needs_competition",
        }
        for state_name, field_name in payload_states.items():
            value = getattr(self, field_name)
            if self.state == state_name and value is None:
                raise ValueError(f"state={state_name} requires the {field_name} payload")
            if self.state != state_name and value is not None:
                raise ValueError(f"{field_name} is only legal with state={state_name}")
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
