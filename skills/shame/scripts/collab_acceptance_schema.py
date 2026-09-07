#!/usr/bin/env python3
"""Validate lazy_report_shame.collab_acceptance.v1 receipts."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_core import PydanticCustomError


class CollabAcceptance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_: Literal["lazy_report_shame.collab_acceptance.v1"] = Field(alias="schema")
    implementer: str = Field(min_length=1)
    acceptor: str = Field(min_length=1)
    task_msg_id: str = Field(min_length=1)
    peer_rejection_msg_id: str = Field(min_length=1)
    changed_action: str = Field(min_length=1)
    acceptance_msg_id: str = Field(min_length=1)
    verified_command: str | None = Field(default=None, min_length=1)
    verified_result: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def peer_must_accept(self) -> "CollabAcceptance":
        if self.acceptor == self.implementer:
            raise PydanticCustomError(
                "collab_acceptor_must_differ",
                "acceptor must differ from implementer",
                {"field": "acceptor"},
            )
        return self


def invalid(errors: list[dict]) -> dict:
    return {
        "schema": "lazy_report_shame.collab_acceptance.validation_result.v1",
        "valid": False,
        "errors": [
            {
                "type": str(e.get("type") or "invalid_collab_acceptance"),
                "loc": [str(p) for p in e.get("loc", ())],
                "msg": str(e.get("msg") or "invalid collab acceptance"),
                "ctx": e.get("ctx") if isinstance(e.get("ctx"), dict) else {},
            }
            for e in errors
        ],
    }


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] != "validate":
        print(__doc__, file=sys.stderr)
        return 2
    raw = sys.stdin.read() if sys.argv[2] == "-" else Path(sys.argv[2]).read_text()
    try:
        CollabAcceptance.model_validate_json(raw)
    except ValidationError as exc:
        print(json.dumps(invalid(exc.errors(include_url=False))))
        return 1
    except Exception as exc:
        print(json.dumps(invalid([{"type": "invalid_json", "loc": [], "msg": str(exc), "ctx": {}}])))
        return 1
    print(json.dumps({"schema": "lazy_report_shame.collab_acceptance.validation_result.v1", "valid": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
