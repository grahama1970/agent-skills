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
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from pydantic_core import PydanticCustomError

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


def file_sha256_uri(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def import_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"could not load {name} validator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def import_receipt_envelope() -> Any:
    module_path = Path(__file__).resolve().parents[2] / "agent-ecosystem/scripts/receipt_envelope.py"
    return import_module(module_path, "receipt_envelope")


def import_collab_acceptance() -> Any:
    return import_module(Path(__file__).with_name("collab_acceptance_schema.py"), "collab_acceptance_schema")


def parse_proof_json(path: Path, text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        data = json.loads(stripped)
    except Exception:
        if stripped[:1] in "[{":
            raise PydanticCustomError(
                "proof_json_malformed",
                "JSON-looking proof is malformed and cannot authorize done",
                {"proof": str(path)},
            )
        return None
    if not isinstance(data, dict):
        raise PydanticCustomError("proof_json_not_object", "JSON proof must be an object", {"proof": str(path)})
    return data


def validate_known_receipt(path: Path, text: str) -> dict[str, Any] | None:
    data = parse_proof_json(path, text)
    if data is None:
        return None
    schema = data.get("schema")
    if not schema:
        raise PydanticCustomError("proof_json_schema_missing", "JSON proof must declare a known schema", {"proof": str(path)})
    if schema == "agentic_evals.report.v2":
        counts = data.get("outcome_counts") or {}
        if data.get("readiness") != "READY" or any(counts.get(k, 0) for k in ("FAIL", "BLOCKED", "NOT_TESTED")):
            raise PydanticCustomError(
                "agentic_eval_proof_not_ready",
                "agentic eval proof is not READY with zero failing outcomes",
                {"proof": str(path)},
            )
    elif schema == "lazy_report_shame.report_check.v2":
        if data.get("decision") != "pass":
            raise PydanticCustomError(
                "status_check_proof_not_pass",
                "status-check proof decision is not pass",
                {"proof": str(path)},
            )
    elif schema == "lazy_report_shame.collab_acceptance.v1":
        import_collab_acceptance().CollabAcceptance.model_validate(data)
    elif schema == "pi.receipt_envelope.v1":
        import_receipt_envelope().ReceiptEnvelope.model_validate(data)
    elif schema == "debugger.proof.v1":
        if not any(data.get(k) for k in ("breakpoints", "frames", "locals")):
            raise PydanticCustomError(
                "debugger_proof_missing_runtime_evidence",
                "debugger proof has no breakpoint/frame/local evidence",
                {"proof": str(path)},
            )
    elif schema == "ticket.closure_receipt.v1":
        if data.get("action") not in {"close", "close-duplicate"} or data.get("state") != "CLOSED":
            raise PydanticCustomError(
                "ticket_closure_receipt_not_closed",
                "ticket closure receipt must record a CLOSED issue",
                {"proof": str(path)},
            )
        if not data.get("issue") or not data.get("repo") or not data.get("proof_sha256"):
            raise PydanticCustomError(
                "ticket_closure_receipt_incomplete",
                "ticket closure receipt must bind issue, repo, and proof_sha256",
                {"proof": str(path)},
            )
    else:
        raise PydanticCustomError(
            "proof_schema_unsupported",
            "JSON proof schema is not an accepted completion authority",
            {"proof": str(path), "schema": str(schema)},
        )
    return data


def receipt_supports_verified(data: dict[str, Any], item: "VerifiedItem") -> bool:
    schema = data.get("schema")
    if schema == "agentic_evals.report.v2":
        if item.result not in {str(data.get("readiness")), "PASS"}:
            return False
        for case in data.get("cases") or []:
            if not isinstance(case, dict):
                continue
            argv = " ".join(str(part) for part in case.get("argv") or [])
            if item.command in argv and case.get("outcome") == "PASS":
                return True
        return False
    if schema == "lazy_report_shame.report_check.v2":
        return item.command in {"status-json-check", "lazy_report_shame.report_check.v2"} and item.result == "pass"
    if schema == "lazy_report_shame.collab_acceptance.v1":
        return data.get("verified_command") == item.command and data.get("verified_result") == item.result
    if schema == "ticket.closure_receipt.v1":
        command_text = f"{data.get('action')} {data.get('repo')}#{data.get('issue')} {data.get('proof_path', '')}"
        return item.command in command_text and item.result == data.get("state")
    if schema in {"pi.receipt_envelope.v1", "debugger.proof.v1"}:
        text = json.dumps(data, sort_keys=True)
        return item.command in text and item.result in text
    return False


def artifact_supports_verified(text: str, item: "VerifiedItem") -> bool:
    return item.command.startswith(("read ", "inspect ")) and item.result in text


class ParentRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt_id: str = Field(min_length=1)
    receipt_path: str = Field(min_length=1)
    expected_schema: str = Field(min_length=1)
    expected_producer: str = Field(min_length=1)
    digest: str = Field(min_length=71, max_length=71)

    @field_validator("digest")
    @classmethod
    def digest_shape(cls, value: str) -> str:
        prefix = "sha256:"
        if not value.startswith(prefix):
            raise PydanticCustomError("invalid_digest", "digest must start with sha256:")
        digest = value[len(prefix):]
        if len(digest) != 64 or not all(c in "0123456789abcdef" for c in digest):
            raise PydanticCustomError("invalid_digest", "digest must be 64 lowercase hex chars")
        return value


@dataclass(frozen=True, slots=True)
class ResolvedParent:
    ref: ParentRef
    producer: str
    payload_schema: str
    goal_hash: str | None
    parent_refs: tuple[Any, ...]


BRAVE_SEARCH_RESULTS_SCHEMA = "brave_search.web_results.v1"
ASK_AGENT_HANDOFF_SCHEMA = "tau.agent_handoff.v1"
FIRST_ASK_HANDLER_BY_PROJECT_AGENT_FAMILY = {
    "openai": "claude-fable-low",
    "claude": "gpt-5.5-high",
}
PROJECT_AGENT_FAMILY_ENV_VARS = ("LRSSS_PROJECT_AGENT_FAMILY", "LAZY_REPORT_SHAME_PROJECT_AGENT_FAMILY", "PI_PROJECT_AGENT_FAMILY")
ASK_HANDLER_AVAILABILITY_ENV_VARS = ("LRSSS_AVAILABLE_ASK_HANDLERS", "LAZY_REPORT_SHAME_AVAILABLE_ASK_HANDLERS", "ASK_AVAILABLE_HANDLERS")


def receipt_parent_ref(ref: ParentRef) -> dict[str, str]:
    return {
        "receipt_id": ref.receipt_id,
        "expected_schema": ref.expected_schema,
        "expected_producer": ref.expected_producer,
        "digest": ref.digest,
    }


def same_receipt_ref(left: dict[str, str], right: Any) -> bool:
    return (
        left["receipt_id"] == getattr(right, "receipt_id", None)
        and left["expected_schema"] == getattr(right, "expected_schema", None)
        and left["expected_producer"] == getattr(right, "expected_producer", None)
        and left["digest"] == getattr(right, "digest", None)
    )


def normalize_project_agent_family(value: str) -> str:
    family = value.strip().lower()
    if family in FIRST_ASK_HANDLER_BY_PROJECT_AGENT_FAMILY:
        return family
    if "codex" in family or family.startswith(("openai", "gpt-")):
        return "openai"
    if "anthropic" in family or family.startswith("claude"):
        return "claude"
    return family


def runtime_project_agent_family() -> tuple[str, str | None]:
    for name in PROJECT_AGENT_FAMILY_ENV_VARS:
        raw = os.environ.get(name, "").strip()
        if raw:
            return normalize_project_agent_family(raw), name
    provider = os.environ.get("PI_PROVIDER", "").strip()
    if provider:
        return normalize_project_agent_family(provider), "PI_PROVIDER"
    return "", None


def runtime_configured_ask_handlers() -> tuple[frozenset[str], str | None]:
    for name in ASK_HANDLER_AVAILABILITY_ENV_VARS:
        raw = os.environ.get(name, "").strip()
        if raw:
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = None
            if isinstance(parsed, list):
                return frozenset(str(item).strip() for item in parsed if str(item).strip()), name
            return frozenset(part for part in raw.replace(",", " ").split() if part), name
    return frozenset(), None


def resolve_parent_ref(ref: ParentRef, goal_hash: str | None, state: str) -> ResolvedParent:
    if goal_hash is None:
        raise PydanticCustomError(
            f"{state}_requires_goal_hash",
            f"state={state} with parent_refs requires goal_hash",
            {"field": "goal_hash"},
        )
    path = local_proof_path(ref.receipt_path)
    if path is None:
        raise PydanticCustomError(
            "parent_ref_receipt_unresolved",
            "parent_ref receipt_path must be a local receipt file",
            {"receipt_id": ref.receipt_id, "receipt_path": ref.receipt_path},
        )
    if not path.exists():
        raise PydanticCustomError(
            "parent_ref_receipt_missing",
            "parent_ref receipt_path does not exist",
            {"receipt_id": ref.receipt_id, "receipt_path": str(path)},
        )
    if not path.is_file():
        raise PydanticCustomError(
            "parent_ref_receipt_not_file",
            "parent_ref receipt_path must be a file",
            {"receipt_id": ref.receipt_id, "receipt_path": str(path)},
        )
    actual_digest = file_sha256_uri(path)
    if actual_digest != ref.digest:
        raise PydanticCustomError(
            "parent_ref_digest_mismatch",
            "parent_ref digest must match the resolved receipt bytes",
            {"receipt_id": ref.receipt_id, "expected_digest": ref.digest, "actual_digest": actual_digest},
        )
    text = read_proof_text(path)
    data = parse_proof_json(path, text)
    if data is None or data.get("schema") != "pi.receipt_envelope.v1":
        raise PydanticCustomError(
            "parent_ref_receipt_not_envelope",
            "parent_ref receipt must resolve to pi.receipt_envelope.v1",
            {"receipt_id": ref.receipt_id, "receipt_path": str(path)},
        )
    try:
        envelope = import_receipt_envelope().ReceiptEnvelope.model_validate(data)
    except Exception as exc:
        raise PydanticCustomError(
            "parent_ref_receipt_invalid",
            "parent_ref receipt envelope failed validation",
            {"receipt_id": ref.receipt_id, "error": str(exc)},
        ) from exc
    if envelope.receipt_id != ref.receipt_id:
        raise PydanticCustomError(
            "parent_ref_receipt_id_mismatch",
            "parent_ref receipt_id must match the resolved receipt",
            {"expected_receipt_id": ref.receipt_id, "actual_receipt_id": envelope.receipt_id},
        )
    if envelope.payload_schema != ref.expected_schema:
        raise PydanticCustomError(
            "parent_ref_schema_mismatch",
            "parent_ref expected_schema must match the resolved receipt payload_schema",
            {"receipt_id": ref.receipt_id, "expected_schema": ref.expected_schema, "actual_schema": envelope.payload_schema},
        )
    if envelope.producer != ref.expected_producer:
        raise PydanticCustomError(
            "parent_ref_producer_mismatch",
            "parent_ref expected_producer must match the resolved receipt producer",
            {"receipt_id": ref.receipt_id, "expected_producer": ref.expected_producer, "actual_producer": envelope.producer},
        )
    if envelope.goal_hash != goal_hash:
        raise PydanticCustomError(
            "parent_ref_goal_hash_mismatch",
            "parent_ref receipt goal_hash must match the active status goal_hash",
            {"receipt_id": ref.receipt_id, "expected_goal_hash": goal_hash, "actual_goal_hash": envelope.goal_hash},
        )
    return ResolvedParent(
        ref=ref,
        producer=envelope.producer,
        payload_schema=envelope.payload_schema,
        goal_hash=envelope.goal_hash,
        parent_refs=tuple(envelope.parent_refs),
    )


class VerifiedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: str = Field(min_length=1)
    result: str = Field(min_length=1)


class StatusNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    artifact: str | None = None
    receipt: str | None = None


class BlockedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    next_command: str | None = None


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
        raise PydanticCustomError(
            "ambiguous_failure_code",
            "failure.triage.code must come from triage-error or match *_unclassified_<8hex>",
            {"next_command": "skills/triage-error/run.sh classify"},
        )


class NeedsHuman(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(min_length=1, description="Exact human action required, e.g. 'run /reload'")
    reason: str = Field(min_length=1)


class NeedsBraveSearch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    queries: list[str] = Field(min_length=1)


def has_parent_receipt(refs: list[ResolvedParent], producer: str, payload_schema: str) -> bool:
    return any(ref.producer == producer and ref.payload_schema == payload_schema for ref in refs)


class NeedsAgent(BaseModel):
    """Cross-provider-family fast single-call after brave-search evidence exists."""
    model_config = ConfigDict(extra="forbid")
    project_agent_family: Literal["openai", "claude"]
    handler: str = Field(min_length=1, description="Cross-family handler, e.g. claude-fable-low or gpt-5.5-high")
    question: str = Field(min_length=1)
    parent_refs: list[ParentRef] = Field(min_length=1, description="Must include the brave-search receipt that failed to unblock")

    @model_validator(mode="after")
    def enforce_cross_family_after_brave(self) -> "NeedsAgent":
        runtime_family, family_source = runtime_project_agent_family()
        if family_source is None:
            raise PydanticCustomError(
                "needs_agent_runtime_family_missing",
                "state=needs_agent requires a trusted runtime project-agent family",
                {
                    "required_env": list(PROJECT_AGENT_FAMILY_ENV_VARS),
                    "fallback_env": "PI_PROVIDER",
                },
            )
        required_handler = FIRST_ASK_HANDLER_BY_PROJECT_AGENT_FAMILY.get(runtime_family)
        if required_handler is None:
            raise PydanticCustomError(
                "needs_agent_unsupported_runtime_family",
                "state=needs_agent requires a supported runtime project-agent family",
                {
                    "runtime_family": runtime_family,
                    "family_source": family_source,
                    "supported_families": sorted(FIRST_ASK_HANDLER_BY_PROJECT_AGENT_FAMILY),
                },
            )
        payload_family = normalize_project_agent_family(self.project_agent_family)
        if payload_family != runtime_family:
            raise PydanticCustomError(
                "needs_agent_project_family_not_runtime_bound",
                "needs_agent.project_agent_family must match the trusted runtime project-agent family",
                {
                    "payload_family": payload_family,
                    "runtime_family": runtime_family,
                    "family_source": family_source,
                },
            )
        if self.handler != required_handler:
            raise PydanticCustomError(
                "needs_agent_requires_cross_family_handler",
                "state=needs_agent must use the exact first Ask handler for the trusted runtime family",
                {
                    "runtime_family": runtime_family,
                    "family_source": family_source,
                    "allowed_handler": required_handler,
                },
            )
        available_handlers, handler_source = runtime_configured_ask_handlers()
        if handler_source is None:
            raise PydanticCustomError(
                "needs_agent_ask_handlers_missing",
                "state=needs_agent requires runtime-configured Ask handler availability",
                {"required_env": list(ASK_HANDLER_AVAILABILITY_ENV_VARS)},
            )
        if required_handler not in available_handlers:
            raise PydanticCustomError(
                "needs_agent_first_handler_unavailable",
                "configured Ask handlers do not include the required first-rung handler",
                {
                    "runtime_family": runtime_family,
                    "family_source": family_source,
                    "required_handler": required_handler,
                    "handler_source": handler_source,
                    "configured_handlers": sorted(available_handlers),
                },
            )
        return self


class NeedsWebgpt(BaseModel):
    """Only legal after brave-search and cross-family agent rungs failed to unblock."""
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1)
    parent_refs: list[ParentRef] = Field(min_length=2, description="Must include typed brave-search and ask receipt refs")


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
    answer: str | None = Field(default=None, min_length=1, max_length=300)
    plain_answer: str | None = Field(
        default=None,
        min_length=1,
        max_length=4000,
        description=(
            "Optional plain-spoken verdict for the human-visible Status Report "
            "lead line; `answer` stays the <=300-char machine headline. "
            "Anti-fabrication validation still binds to verified[]/proof[]; "
            "plain_answer is display text, not new evidence."
        ),
    )
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
    changed: list[str] = Field(default_factory=list)
    verified: list[VerifiedItem] = Field(default_factory=list)
    proof: list[str] = Field(default_factory=list)
    run_dir: str | None = Field(default=None, min_length=1)
    artifacts: list[str] = Field(default_factory=list)
    receipts: list[str] = Field(default_factory=list)
    nodes: list[StatusNode] = Field(default_factory=list)
    blocked: list[BlockedItem] = Field(default_factory=list)
    missing_artifacts: list[str] = Field(default_factory=list)
    not_done: list[NotDoneItem] = Field(default_factory=list)
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
            raise PydanticCustomError("invalid_goal_hash", "goal_hash must start with sha256:")
        digest = value[len(prefix):]
        if len(digest) != 64 or not all(c in "0123456789abcdef" for c in digest):
            raise PydanticCustomError("invalid_goal_hash", "goal_hash digest must be 64 lowercase hex chars")
        return value

    @model_validator(mode="after")
    def state_legality(self) -> "AgentStatus":
        if self.state == "failed" and self.failure is None:
            raise PydanticCustomError("failed_requires_triage", "state=failed requires failure.triage with a canonical code")
        if self.state != "failed" and self.failure is not None:
            raise PydanticCustomError("failure_only_with_failed", "failure is only legal with state=failed")
        if self.state == "continuing" and not self.not_done:
            raise PydanticCustomError("continuing_requires_not_done", "state=continuing requires not_done[].next_command")
        if self.not_done and self.state != "continuing":
            raise PydanticCustomError(
                "not_done_requires_continuing",
                "not_done is only legal with state=continuing",
                {"next_field": "not_done[0].next_command"},
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
                raise PydanticCustomError("state_payload_missing", f"state={state_name} requires the {field_name} payload", {"field": field_name})
            if self.state != state_name and value is not None:
                raise PydanticCustomError("state_payload_forbidden", f"{field_name} is only legal with state={state_name}", {"field": field_name})
        if self.state in {"needs_brave_search", "needs_agent", "needs_webgpt"} and self.goal_hash is None:
            raise PydanticCustomError(
                "escalation_requires_goal_hash",
                f"state={self.state} requires goal_hash before compiling an escalation command",
                {"field": "goal_hash"},
            )
        if self.state == "needs_agent" and self.needs_agent is not None:
            resolved = [
                resolve_parent_ref(ref, self.goal_hash, self.state)
                for ref in self.needs_agent.parent_refs
            ]
            if not has_parent_receipt(resolved, "brave-search", BRAVE_SEARCH_RESULTS_SCHEMA):
                raise PydanticCustomError(
                    "needs_agent_requires_brave_parent",
                    "state=needs_agent requires a resolved brave-search web-results parent_ref",
                    {"expected_producer": "brave-search", "expected_schema": BRAVE_SEARCH_RESULTS_SCHEMA},
                )
        if self.state == "needs_webgpt" and self.needs_webgpt is not None:
            resolved = [
                resolve_parent_ref(ref, self.goal_hash, self.state)
                for ref in self.needs_webgpt.parent_refs
            ]
            brave_refs = [
                parent
                for parent in resolved
                if parent.producer == "brave-search" and parent.payload_schema == BRAVE_SEARCH_RESULTS_SCHEMA
            ]
            ask_refs = [
                parent
                for parent in resolved
                if parent.producer == "ask" and parent.payload_schema == ASK_AGENT_HANDOFF_SCHEMA
            ]
            if not brave_refs:
                raise PydanticCustomError(
                    "needs_webgpt_requires_brave_parent",
                    "state=needs_webgpt requires a resolved brave-search web-results parent_ref",
                    {"expected_producer": "brave-search", "expected_schema": BRAVE_SEARCH_RESULTS_SCHEMA},
                )
            if not ask_refs:
                raise PydanticCustomError(
                    "needs_webgpt_requires_ask_parent",
                    "state=needs_webgpt requires a resolved Ask handoff parent_ref",
                    {"expected_producer": "ask", "expected_schema": ASK_AGENT_HANDOFF_SCHEMA},
                )
            brave_receipts = [receipt_parent_ref(parent.ref) for parent in brave_refs]
            if not any(
                same_receipt_ref(brave_ref, ask_parent_ref)
                for ask_parent in ask_refs
                for ask_parent_ref in ask_parent.parent_refs
                for brave_ref in brave_receipts
            ):
                raise PydanticCustomError(
                    "needs_webgpt_requires_ask_descended_from_brave",
                    "state=needs_webgpt requires an ask parent receipt descended from the brave-search evidence",
                    {"expected_lineage": "ask.parent_refs[] must include the brave-search parent_ref"},
                )
        if not self.changed:
            raise PydanticCustomError(
                "changed_required",
                "every report requires non-empty changed",
                {"field": "changed"},
            )
        if self.state == "done":
            if not self.verified:
                raise PydanticCustomError("done_requires_verified", "state=done requires non-empty verified", {"field": "verified"})
            if not self.proof:
                raise PydanticCustomError("done_requires_proof", "state=done requires non-empty proof", {"field": "proof"})
            if self.not_done:
                raise PydanticCustomError(
                    "done_forbids_not_done",
                    "state=done forbids not_done; use state=continuing or state=needs_human",
                    {"next_field": "not_done[0].next_command"},
                )
            proof_records: list[tuple[dict[str, Any] | None, str]] = []
            for proof in self.proof:
                path = local_proof_path(proof)
                if path is None:
                    raise PydanticCustomError(
                        "proof_reference_unresolved",
                        "proof references must be materialized as local evidence before done",
                        {"proof": proof},
                    )
                if not path.exists():
                    raise PydanticCustomError("proof_path_missing", "proof path does not exist", {"proof": proof})
                if not path.is_file():
                    raise PydanticCustomError("proof_not_file", "proof must be a readable file, not a directory", {"proof": proof})
                text = read_proof_text(path)
                if not text.strip():
                    raise PydanticCustomError("proof_empty", "proof file has no evidence text", {"proof": proof})
                proof_records.append((validate_known_receipt(path, text), text))
            for item in self.verified:
                backed = any(
                    receipt_supports_verified(record, item) if record is not None else artifact_supports_verified(text, item)
                    for record, text in proof_records
                )
                if not backed:
                    raise PydanticCustomError(
                        "verified_not_backed_by_proof",
                        "verified item is not backed by one proof record",
                        {"command": item.command, "result": item.result},
                    )
        return self


def steering_from_error(error: dict[str, Any]) -> dict[str, Any]:
    """Return the machine steering payload from one Pydantic error."""
    code = str(error.get("type") or "invalid_agent_status_json")
    loc = [str(part) for part in error.get("loc", ())]
    ctx = error.get("ctx") if isinstance(error.get("ctx"), dict) else {}
    field = ctx.get("field") or (loc[0] if loc else None)
    steering: dict[str, Any] = {"code": code, "loc": loc}
    if field:
        steering["field"] = field
    if code == "missing":
        steering["action"] = "add_required_field"
    elif code.endswith("_required") or code.startswith("done_requires_") or code == "state_payload_missing":
        steering["action"] = "add_required_field"
    elif code.endswith("_forbidden") or code.endswith("_only_with_failed") or code == "done_forbids_not_done":
        steering["action"] = "remove_or_change_state"
    elif code == "not_done_requires_continuing":
        steering.update({"action": "set_state", "state": "continuing", "field": "not_done"})
    elif code == "ambiguous_failure_code":
        steering.update({"action": "classify_with_triage_error", "next_command": ctx.get("next_command")})
    elif code in {"proof_path_missing", "proof_reference_unresolved", "proof_not_file", "proof_empty"}:
        steering.update({"action": "cite_existing_proof_path", "proof": ctx.get("proof")})
    elif code == "verified_not_backed_by_proof":
        steering.update({"action": "make_verified_match_proof", "command": ctx.get("command"), "result": ctx.get("result")})
    else:
        steering["action"] = "fix_field"
    return steering


def minimal_example(state: str) -> dict[str, Any]:
    """Return a minimal schema-valid pi.agent_status.v1 example for a state."""
    base: dict[str, Any] = {"schema": "pi.agent_status.v1", "goal": "<one-line goal>", "changed": ["no change: <reason>"]}
    payloads: dict[str, dict[str, Any]] = {
        "done": {
            "verified": [{"command": "read /path/proof.txt", "result": "<exact substring of that file>"}],
            "proof": ["/path/proof.txt"],
        },
        "continuing": {"not_done": [{"item": "<remaining item>", "next_command": "<runnable command>"}]},
        "needs_human": {"needs_human": {"action": "<exact human action>", "reason": "<why>"}},
        "failed": {"failure": {"triage": {"code": "<triage-error catalog code>"}}},
        "needs_brave_search": {"needs_brave_search": {"queries": ["<query>"]}},
    }
    example_state = state if state in payloads else "done"
    return {**base, "state": example_state, **payloads[example_state]}


def invalid_payload(errors: list[dict[str, Any]], state_hint: str = "done") -> dict[str, Any]:
    normalized = [
        {
            "type": str(error.get("type") or "invalid_agent_status_json"),
            "loc": [str(part) for part in error.get("loc", ())],
            "msg": str(error.get("msg") or "invalid agent status"),
            "ctx": error.get("ctx") if isinstance(error.get("ctx"), dict) else {},
        }
        for error in errors
    ]
    return {
        "valid": False,
        "schema": "pi.agent_status.validation_result.v1",
        "errors": normalized,
        "steering": [steering_from_error(error) for error in normalized],
        "example": minimal_example(state_hint),
    }


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "example":
        print(json.dumps(minimal_example(sys.argv[2]), indent=2))
        return 0
    if len(sys.argv) != 3 or sys.argv[1] != "validate":
        print(__doc__, file=sys.stderr)
        return 2
    raw = sys.stdin.read() if sys.argv[2] == "-" else Path(sys.argv[2]).read_text()
    state_hint = "done"
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and isinstance(parsed.get("state"), str):
            state_hint = parsed["state"]
    except Exception:
        pass
    try:
        status = AgentStatus.model_validate_json(raw)
    except ValidationError as exc:
        print(json.dumps(invalid_payload(exc.errors(include_url=False), state_hint)))
        return 1
    except Exception as exc:
        print(json.dumps(invalid_payload([{"type": "invalid_json", "loc": [], "msg": str(exc), "ctx": {}}], state_hint)))
        return 1
    print(json.dumps({"valid": True, "schema": "pi.agent_status.validation_result.v1", "state": status.state}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
