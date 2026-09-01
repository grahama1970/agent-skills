#!/usr/bin/env python3
"""pi.agent_status.v1 — single JSON status report for agent turns.

Ambiguous blocker labels are unrepresentable: a blocked state requires a
triage code that exists in the triage-error catalog or matches the minted
``*_unclassified_<8hex>`` shape. Validate with:

    python3 status_schema.py validate <file.json>   # exit 0 pass, 1 fail
    echo '{...}' | python3 status_schema.py validate -
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CATALOG_PATH = Path(__file__).resolve().parents[3] / "skills/triage-error/failure_codes.json"
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


def local_proof_path(value: str) -> Path | None:
    if value.startswith(("http://", "https://", "sha256:")):
        return None
    path = Path(value)
    return path if path.is_absolute() else Path.cwd() / path


def read_proof_text(path: Path) -> str:
    if path.is_dir():
        return "\n".join(sorted(p.name for p in path.iterdir()))
    return path.read_text(errors="ignore")[:200_000]


def import_receipt_envelope() -> Any:
    module_path = Path(__file__).resolve().parents[2] / "agent-ecosystem/scripts/receipt_envelope.py"
    spec = importlib.util.spec_from_file_location("receipt_envelope", module_path)
    if spec is None or spec.loader is None:
        raise ValueError("could not load receipt_envelope validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_known_receipt(path: Path, text: str) -> None:
    try:
        data = json.loads(text)
    except Exception:
        return
    if not isinstance(data, dict):
        return
    schema = data.get("schema")
    if schema == "agentic_evals.report.v2":
        counts = data.get("outcome_counts") or {}
        if data.get("readiness") != "READY" or any(counts.get(k, 0) for k in ("FAIL", "BLOCKED", "NOT_TESTED")):
            raise ValueError(f"agentic eval proof {path} is not READY with zero failing outcomes")
    elif schema == "lazy_report_shame.report_check.v2":
        if data.get("decision") != "pass":
            raise ValueError(f"status-check proof {path} decision is not pass")
    elif schema == "pi.receipt_envelope.v1":
        import_receipt_envelope().ReceiptEnvelope.model_validate(data)
    elif schema == "debugger.proof.v1":
        if not any(k in data for k in ("breakpoints", "frames", "locals")):
            raise ValueError(f"debugger proof {path} has no breakpoint/frame/local evidence")


class ParentRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt_id: str = Field(min_length=1)
    expected_schema: str = Field(min_length=1)
    expected_producer: str = Field(min_length=1)
    digest: str | None = None

    @field_validator("digest")
    @classmethod
    def digest_shape(cls, value: str | None) -> str | None:
        if value is None:
            return value
        prefix = "sha256:"
        if not value.startswith(prefix):
            raise ValueError("digest must start with sha256:")
        digest = value[len(prefix):]
        if len(digest) != 64 or not all(c in "0123456789abcdef" for c in digest):
            raise ValueError("digest must be 64 lowercase hex chars")
        return value


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
    parent_refs: list[ParentRef] = Field(min_length=2, description="Typed rung-0/rung-1 evidence refs; no ad hoc receipt paths")


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
        if self.not_done and self.state != "continuing":
            raise ValueError(
                "not_done items mean unfinished agent-executable work; use state=continuing "
                "so not_done[0].next_command is queued deterministically. Use "
                "needs_human.action instead of not_done when a person must act."
            )
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
        if not self.changed:
            raise ValueError(
                "every report requires non-empty changed; state what is now different "
                "(or explicitly 'no change: <reason>')"
            )
        if self.state == "done":
            if not self.verified:
                raise ValueError("state=done requires non-empty verified")
            if not self.proof:
                raise ValueError("state=done requires non-empty proof")
            if self.not_done:
                raise ValueError(
                    "state=done with not_done items parks work without a human gate: "
                    "use state=continuing so not_done[0].next_command is queued "
                    "deterministically, or state=needs_human with the exact action"
                )
            proof_text = ""
            for proof in self.proof:
                path = local_proof_path(proof)
                if path is None:
                    continue
                if not path.exists():
                    raise ValueError(f"proof path does not exist: {proof}")
                text = read_proof_text(path)
                validate_known_receipt(path, text)
                proof_text += "\n" + text
            if proof_text:
                for item in self.verified:
                    if item.command not in proof_text or item.result not in proof_text:
                        raise ValueError(
                            "verified item is not backed by proof text: "
                            f"command={item.command!r} result={item.result!r}"
                        )
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
