"""Tau child exploit DAG contract authoring and validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


TAU_DAG_SCHEMA = "tau.dag_contract.v1"
CHILD_DAG_SUMMARY_SCHEMA = "battle.child_exploit_tau_dag_summary.v1"

FORBIDDEN_INPUTS = [
    "arena/private/**",
    "hidden-ground-truth.json",
    "hidden-vulnerability-ledger.json",
    "judge/oracle/**",
]

TAU_FAIL_CLOSED_ON = [
    "goal_hash_mismatch",
    "target_changed",
    "unexpected_node",
    "unexpected_edge",
    "missing_required_evidence",
    "malformed_handoff",
    "max_attempts_exceeded",
    "brave_search_required_after_two_attempts",
]
BATTLE_FAIL_CLOSED_ON = [
    "private_arena_artifact_reference",
    "hidden_ground_truth_reference",
    "missing_compile_receipt",
    "exploit_success_claim_without_judge_receipt",
    "child_spawn_without_spawn_policy_receipt",
    "third_compile_attempt_without_research_refresh",
]
REQUIRED_ROUTE = [
    "lineage-summarizer",
    "research-scout",
    "method-combiner",
    "exploit-code-author",
    "compile-repair",
    "artifact-reviewer",
    "battle-handoff-writer",
]


def build_child_exploit_tau_dag(*, battle_id: str, child_knowledge_packet: dict[str, Any], spawn_policy_decision: dict[str, Any]) -> dict[str, Any]:
    goal_text = f"{battle_id}: child exploit synthesis DAG birth contract for {child_knowledge_packet['child_lane_id']}"
    goal_hash = "sha256:" + hashlib.sha256(goal_text.encode("utf-8")).hexdigest()
    return {
        "schema": TAU_DAG_SCHEMA,
        "dag_id": f"{battle_id}-child-spawn-synthesis-0001",
        "goal": {
            "goal_id": f"{battle_id}-child-exploit-specimen",
            "goal_version": 1,
            "goal_hash": goal_hash,
            "immutable": True,
            "description": "Create a child exploit-synthesis handoff candidate from public Arena context and parent-approved knowledge only.",
        },
        "target": {
            "repo": "grahama1970/agent-skills",
            "target": "skills/battle",
            "battle_id": battle_id,
            "arena_public_bundle": child_knowledge_packet["arena_public_context_refs"],
            "parent_knowledge_packet": "child-knowledge-packet.json",
            "spawn_policy_decision": "spawn-policy-decision.json",
            "forbidden_inputs": FORBIDDEN_INPUTS,
        },
        "entry_node": "lineage-summarizer",
        "terminal_nodes": ["battle-handoff-writer", "blocked"],
        "limits": {
            "resume": True,
            "default_timeout_seconds": 240,
            "max_total_attempts": 8,
        },
        "nodes": [
            _node("lineage-summarizer", "lineage-planner", "summarize-parent-knowledge", ["child_knowledge_packet.json"]),
            _node("research-scout", "researcher", "source-bearing-security-research", ["research_receipts.json", "candidate_methods.json"], max_attempts=2),
            _node("method-combiner", "strategy-combiner", "exploit-method-selection", ["exploit_genome.json", "combination_rationale.md"]),
            _node("exploit-code-author", "coder", "exploit-specimen-code", ["exploit_specimen.py", "specimen.json"]),
            _node("compile-repair", "compiler-repairer", "compile-and-repair", ["compile_receipt.json", "repaired_exploit_specimen.py"], max_attempts=3),
            _node("artifact-reviewer", "reviewer", "claim-boundary-review", ["review_receipt.json"]),
            _node("battle-handoff-writer", "handoff-writer", "battle-exploit-runner-handoff", ["battle_exploit_handoff.json"]),
            _node("blocked", "blocked", "terminal-blocked-report", ["blocked_report.json"]),
        ],
        "edges": [
            {"from": "lineage-summarizer", "to": "research-scout"},
            {"from": "research-scout", "to": "method-combiner"},
            {"from": "method-combiner", "to": "exploit-code-author"},
            {"from": "exploit-code-author", "to": "compile-repair"},
            {"from": "compile-repair", "to": "artifact-reviewer"},
            {"from": "artifact-reviewer", "to": "battle-handoff-writer"},
            {"from": "compile-repair", "to": "research-scout", "condition": "compile_failed_twice_requires_new_research"},
            {"from": "artifact-reviewer", "to": "blocked", "condition": "forbidden_claim_or_private_input_leak"},
        ],
        "required_evidence": [
            "child_knowledge_packet",
            "source_bearing_research_receipts",
            "exploit_genome",
            "compile_receipt",
            "battle_exploit_handoff",
            "claim_boundary_review",
        ],
        "fail_closed_on": [
            *TAU_FAIL_CLOSED_ON,
        ],
        "battle_fail_closed_on": [
            *BATTLE_FAIL_CLOSED_ON,
        ],
        "claims": {
            "proves": ["Spawn Architect authored a Tau child exploit-synthesis DAG contract."],
            "does_not_prove": ["Tau executed the DAG.", "A child exploit specimen was generated.", "Exploit success."],
        },
        "spawn_policy": {
            "decision": spawn_policy_decision["decision"],
            "materialized_child": False,
        },
    }


def validate_child_exploit_tau_dag(dag: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if dag.get("schema") != TAU_DAG_SCHEMA:
        errors.append("child DAG schema is not tau.dag_contract.v1")
    if not dag.get("dag_id"):
        errors.append("child DAG missing stable dag_id")
    goal = dag.get("goal") if isinstance(dag.get("goal"), dict) else {}
    if not str(goal.get("goal_hash", "")).startswith("sha256:"):
        errors.append("child DAG missing immutable goal hash")
    if goal.get("immutable") is not True:
        errors.append("child DAG goal is not immutable")
    if not dag.get("entry_node"):
        errors.append("child DAG missing entry_node")
    if not dag.get("terminal_nodes"):
        errors.append("child DAG missing terminal_nodes")
    if not isinstance(dag.get("limits"), dict):
        errors.append("child DAG missing bounded limits")
    for key in ("required_evidence", "fail_closed_on"):
        if not dag.get(key):
            errors.append(f"child DAG missing {key}")
    for invariant in BATTLE_FAIL_CLOSED_ON:
        if invariant not in (dag.get("battle_fail_closed_on") or []):
            errors.append(f"child DAG missing Battle invariant {invariant}")
    for invariant in TAU_FAIL_CLOSED_ON:
        if invariant not in (dag.get("fail_closed_on") or []):
            errors.append(f"child DAG missing Tau invariant {invariant}")
    forbidden_inputs = (((dag.get("target") or {}).get("forbidden_inputs")) if isinstance(dag.get("target"), dict) else []) or []
    for forbidden in FORBIDDEN_INPUTS:
        if forbidden not in forbidden_inputs:
            errors.append(f"child DAG missing forbidden input {forbidden}")
    serialized = json.dumps(dag, sort_keys=True)
    for forbidden_literal in ("arena/private/actual", "hidden-ground-truth.json:", "hidden-vulnerability-ledger.json:", "judge/oracle/source.py"):
        if forbidden_literal in serialized:
            errors.append(f"child DAG references private artifact {forbidden_literal}")
    proves = " ".join((dag.get("claims") or {}).get("proves", [])).lower()
    if "exploit success" in proves or "exploited" in proves:
        errors.append("child DAG claims exploit success")
    edge_pairs = [(edge.get("from"), edge.get("to")) for edge in dag.get("edges", []) if isinstance(edge, dict)]
    for left, right in zip(REQUIRED_ROUTE, REQUIRED_ROUTE[1:], strict=False):
        if (left, right) not in edge_pairs:
            errors.append(f"child DAG missing route edge {left}->{right}")
    compile_node = _node_by_id(dag, "compile-repair")
    if compile_node.get("max_attempts") != 3:
        errors.append("child DAG missing compile repair retry limit")
    if not any(edge.get("condition") == "compile_failed_twice_requires_new_research" for edge in dag.get("edges", []) if isinstance(edge, dict)):
        errors.append("child DAG missing research refresh after repeated compile failure")

    return {
        "schema": CHILD_DAG_SUMMARY_SCHEMA,
        "valid": not errors,
        "errors": errors,
        "dag_id": dag.get("dag_id"),
        "schema_validated": dag.get("schema") == TAU_DAG_SCHEMA,
        "private_boundary_passed": not errors,
        "route": REQUIRED_ROUTE,
        "forbidden_inputs": FORBIDDEN_INPUTS,
        "tau_execution": "deferred_to_pr3",
        "claims": {
            "proves": ["Battle validated child DAG shape, route, private boundary, and claim boundary."] if not errors else [],
            "does_not_prove": ["Tau executed the DAG.", "A child exploit ran.", "Exploit success."],
        },
    }


def write_dag_yaml(path: Path, dag: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    # JSON is valid YAML 1.2 and keeps this fixture writer dependency-free.
    path.write_text(json.dumps(dag, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _node(node_id: str, role: str, work_type: str, required_outputs: list[str], *, max_attempts: int | None = None) -> dict[str, Any]:
    node = {"id": node_id, "agent": role, "role": role, "work_type": work_type, "required_outputs": required_outputs}
    if max_attempts is not None:
        node["max_attempts"] = max_attempts
    return node


def _node_by_id(dag: dict[str, Any], node_id: str) -> dict[str, Any]:
    for node in dag.get("nodes", []):
        if isinstance(node, dict) and node.get("id") == node_id:
            return node
    return {}
