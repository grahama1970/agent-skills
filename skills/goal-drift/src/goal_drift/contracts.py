"""Typed seam contracts for goal-drift.

best-practices-skills, Typed Seam Contracts: any artifact crossing a boundary is
validated with a typed model at the PRODUCER, and the validation is unignorable —
exactly three outcomes: pass, self-heal-with-record, or raise. No advisory
warnings; a drifting agent will ignore them. A validated artifact carries a
`seam_validation` receipt so downstream readers can distinguish "validated" from
"never checked".

Copy-safe: stdlib only, @dataclass + validate(). No pydantic import, so these
models survive being copied into a run directory.

Boundaries guarded here:
  1. goal registration        human text -> GoalRecord (refuses agent_inferred)
  2. ticket evidence ingest   gh JSON    -> TicketContract
  3. audit emission           Audit      -> AuditContract  (stamped)
  4. tau handoff              Audit      -> tau.generic_dag_spec.v1 + work order

The tau seam is why goal identity is a canonical hash rather than a name: tau
already hashes a goal object canonically, so any edit to the goal text or its
criteria yields a different `goal_hash`. "Immutable" stops being a promise in
prose and becomes something a receipt can prove.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

SEAM_GOAL = "goal_drift.goal.v1"
SEAM_TICKET = "goal_drift.ticket_evidence.v1"
SEAM_AUDIT = "goal_drift.audit.v1"
TAU_DAG_SCHEMA = "tau.generic_dag_spec.v1"
TAU_WORK_ORDER_SCHEMA = "tau.skill_work_order.v1"
TAU_SKILL_NODE_SCHEMA = "tau.skill_dag_node.v1"


class SeamViolation(Exception):
    """A boundary artifact failed validation. Fail closed; never warn-and-continue."""


def canonical_json(value: Any) -> str:
    """Deterministic rendering. Same shape as tau's canonical_json."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_sha256(payload: Any) -> str:
    """`sha256:<hex>` over canonical JSON — tau's convention, matched deliberately."""
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def goal_hash(goal_payload: dict[str, Any]) -> str:
    """Canonical hash over the goal object, excluding volatile bookkeeping.

    `registered_at` and any prior hash are excluded so the hash identifies the
    goal's CONTENT. Re-registering identical text and criteria reproduces the
    hash; changing one word does not.
    """
    stripped = {
        k: v for k, v in goal_payload.items()
        if k not in {"registered_at", "goal_hash", "seam_validation", "parent_goal_hash"}
    }
    return canonical_sha256(stripped)


def stamp(kind: str, repairs: list[str] | None = None) -> dict[str, str]:
    return {
        "kind": kind,
        "status": "SELF_HEALED" if repairs else "PASS",
        **({"repairs": ",".join(repairs)} if repairs else {}),
    }


@dataclass
class TicketContract:
    """gh issue JSON crossing into the audit. Producer-side validated."""

    number: int
    title: str
    state: str
    repairs: list[str] = field(default_factory=list)
    seam_validation: dict[str, str] = field(default_factory=dict)

    VALID_STATES = ("OPEN", "CLOSED")

    def validate(self) -> TicketContract:
        if not isinstance(self.number, int) or self.number <= 0:
            raise SeamViolation(f"ticket number must be a positive int, got {self.number!r}")
        if not self.title.strip():
            raise SeamViolation(f"ticket #{self.number} has no title")
        # Self-heal: gh returns lowercase state; normalise and record it.
        if self.state.upper() in self.VALID_STATES and self.state != self.state.upper():
            self.repairs.append(f"normalised_state:{self.state}")
            self.state = self.state.upper()
        if self.state not in self.VALID_STATES:
            raise SeamViolation(
                f"ticket #{self.number} state {self.state!r} not in {self.VALID_STATES}"
            )
        self.seam_validation = stamp(SEAM_TICKET, self.repairs)
        return self


@dataclass
class AuditContract:
    """The audit result crossing out of this skill. Cross-field truth checks."""

    payload: dict[str, Any]
    seam_validation: dict[str, str] = field(default_factory=dict)

    REQUIRED = ("schema", "project", "window", "verdict", "findings", "read_only")
    VERDICTS = ("ON_GOAL", "DRIFTED", "NOT_ESTABLISHED", "DEGRADED")

    def validate(self) -> AuditContract:
        missing = [k for k in self.REQUIRED if k not in self.payload]
        if missing:
            raise SeamViolation(f"audit payload missing {missing}")
        if self.payload["schema"] != SEAM_AUDIT:
            raise SeamViolation(f"schema must be {SEAM_AUDIT}, got {self.payload['schema']!r}")
        verdict = self.payload["verdict"]
        if verdict not in self.VERDICTS:
            raise SeamViolation(f"verdict {verdict!r} not in {self.VERDICTS}")
        if self.payload.get("read_only") is not True:
            raise SeamViolation("read_only must be true; this skill never mutates")

        # Cross-field truth: field presence alone does not catch a lying summary.
        verdicts = {f.get("verdict") for f in self.payload["findings"]}
        drift_markers = {"MISSING_EXPECTED", "SCOPE_DRIFT", "DECLARED_DRIFT", "UNTICKETED_WORK"}
        if verdict == "ON_GOAL" and (verdicts & drift_markers):
            raise SeamViolation(
                f"ON_GOAL contradicts findings {sorted(verdicts & drift_markers)}"
            )
        if verdict == "NOT_ESTABLISHED" and "GOAL_UNREGISTERED" not in verdicts:
            raise SeamViolation("NOT_ESTABLISHED requires a GOAL_UNREGISTERED finding")
        cap = self.payload.get("indirect_cap")
        share = self.payload.get("indirect_share")
        if isinstance(cap, (int, float)) and isinstance(share, (int, float)):
            if share > cap and verdict == "ON_GOAL":
                raise SeamViolation(
                    f"indirect_share {share} exceeds cap {cap} but verdict is ON_GOAL"
                )
        self.seam_validation = stamp(SEAM_AUDIT)
        self.payload["seam_validation"] = self.seam_validation
        return self


def tau_dag_spec(
    *,
    run_id: str,
    run_dir: str,
    goal_payload: dict[str, Any],
    receipt_path: str,
    work_order_path: str,
    output_dir: str,
    parent_goal_hash: str | None = None,
) -> dict[str, Any]:
    """Emit a `tau.generic_dag_spec.v1` skill node for the audit.

    Deliberately generic_dag_spec.v1, not dag_contract.v1: tau skill nodes require
    the generic spec. The goal_hash is canonical over the goal object, and the
    prior goal is carried as `goal.parent_goal_hash` so a goal revision is a
    traceable lineage rather than a silent overwrite.
    """
    gh_ = goal_hash(goal_payload)
    goal_block: dict[str, Any] = {"goal_hash": gh_, "statement": goal_payload.get("goal_text", "")}
    if parent_goal_hash:
        goal_block["parent_goal_hash"] = parent_goal_hash
    return {
        "schema": TAU_DAG_SCHEMA,
        "run_id": run_id,
        "run_dir": run_dir,
        "goal_hash": gh_,
        "goal": goal_block,
        "nodes": [
            {
                "node_id": "goal-drift-audit",
                "receipt_path": receipt_path,
                "work_order_path": work_order_path,
                "skill": {
                    "schema": TAU_SKILL_NODE_SCHEMA,
                    "capability": "goal_drift_audit",
                    "provider": "goal-drift",
                    "output_dir": output_dir,
                    "configuration": {"timeout_seconds": 300, "read_only": True},
                },
            }
        ],
    }


def tau_work_order(goal_payload: dict[str, Any], window: str) -> dict[str, Any]:
    return {
        "schema": TAU_WORK_ORDER_SCHEMA,
        "goal_hash": goal_hash(goal_payload),
        "task": (
            f"Audit {goal_payload.get('project','?')} over {window} against its immutable "
            "goal. Read-only: report SERVES_GOAL / SUPPORTS_INDIRECTLY / DECLARED_DRIFT / "
            "UNTICKETED_WORK / MISSING_EXPECTED. Never edit, commit, or reprioritise."
        ),
    }


def enforce(contract: TicketContract | AuditContract) -> TicketContract | AuditContract:
    """Validate or raise. The only sanctioned way to cross a boundary."""
    return contract.validate()
