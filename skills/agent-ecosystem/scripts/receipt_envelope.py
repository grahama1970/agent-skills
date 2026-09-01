#!/usr/bin/env python3
"""pi.receipt_envelope.v1 - boundary envelope for cross-component receipts.

Wraps a payload at authority-changing boundaries (dispatch, handoff,
acceptance, escalation, closure, durable failure). parent_refs are the typed
escalation-evidence edge that replaces ad hoc file paths.

    python3 receipt_envelope.py validate <file.json>   # exit 0 pass, 1 fail
    echo '{...}' | python3 receipt_envelope.py validate -
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CATALOG_PATH = Path(__file__).resolve().parents[3] / "skills/triage-error/failure_codes.json"


def catalog_codes() -> frozenset[str]:
    data = json.loads(CATALOG_PATH.read_text())
    return frozenset(entry["code"] for entry in data["codes"])


def is_minted_code(value: str) -> bool:
    marker = "_unclassified_"
    idx = value.rfind(marker)
    if idx <= 0:
        return False
    prefix, suffix = value[:idx], value[idx + len(marker):]
    if len(suffix) != 8 or not all(c in "0123456789abcdef" for c in suffix):
        return False
    return all(c.islower() or c.isdigit() or c == "_" for c in prefix)


def valid_sha256(value: str) -> bool:
    prefix = "sha256:"
    if not value.startswith(prefix):
        return False
    digest = value[len(prefix):]
    return len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)


class ParentRef(BaseModel):
    """Typed escalation evidence: verify, do not trust a bare path."""
    model_config = ConfigDict(extra="forbid")
    receipt_id: str = Field(min_length=1)
    expected_schema: str = Field(min_length=1)
    expected_producer: str = Field(min_length=1)
    digest: str | None = None

    @field_validator("digest")
    @classmethod
    def digest_shape(cls, value: str | None) -> str | None:
        if value is not None and not valid_sha256(value):
            raise ValueError("digest must be sha256: plus 64 lowercase hex chars")
        return value


class ReceiptEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_: str = Field(alias="schema", pattern=r"^pi\.receipt_envelope\.v1$")
    receipt_id: str = Field(min_length=1)
    payload_schema: str = Field(min_length=1)
    producer: str = Field(min_length=1)
    emitted_at: str = Field(min_length=1)
    goal_hash: str | None = None
    parent_refs: list[ParentRef] = []
    triage_code: str | None = None
    payload: dict

    @field_validator("goal_hash")
    @classmethod
    def goal_hash_shape(cls, value: str | None) -> str | None:
        if value is not None and not valid_sha256(value):
            raise ValueError("goal_hash must be sha256: plus 64 lowercase hex chars")
        return value

    @model_validator(mode="after")
    def payload_schema_congruence(self) -> "ReceiptEnvelope":
        # Reviewer must-land (F1/R1): when the payload declares its own schema,
        # the envelope's payload_schema must equal it. A mismatch is a wrapped
        # lie and fails at parse time.
        declared = self.payload.get("schema")
        if declared is None:
            raise ValueError("payload must declare its own schema field; an anonymous payload cannot be verified against payload_schema")
        if declared != self.payload_schema:
            raise ValueError(
                f"payload_schema {self.payload_schema!r} != payload.schema {declared!r}; the envelope may not misdescribe its payload"
            )
        return self

    @model_validator(mode="after")
    def parent_refs_require_goal_hash(self) -> "ReceiptEnvelope":
        # Reviewer ruling (R3): an escalation-evidence edge without a shared
        # goal is untrusted. Require goal_hash whenever parent_refs is nonempty.
        if self.parent_refs and self.goal_hash is None:
            raise ValueError("parent_refs require goal_hash; an evidence edge without a shared goal is untrusted")
        return self

    @field_validator("triage_code")
    @classmethod
    def triage_code_unambiguous(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value in catalog_codes() or is_minted_code(value):
            return value
        raise ValueError(
            f"ambiguous triage_code {value!r}: not in the triage-error catalog and not a "
            "minted *_unclassified_<8hex> code; run skills/triage-error/run.sh classify first"
        )


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] != "validate":
        print(__doc__, file=sys.stderr)
        return 2
    raw = sys.stdin.read() if sys.argv[2] == "-" else Path(sys.argv[2]).read_text()
    try:
        envelope = ReceiptEnvelope.model_validate_json(raw)
    except Exception as exc:
        print(json.dumps({"valid": False, "error": str(exc)}))
        return 1
    print(json.dumps({"valid": True, "producer": envelope.producer, "payload_schema": envelope.payload_schema}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
