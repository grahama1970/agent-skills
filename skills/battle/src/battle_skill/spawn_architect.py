"""Fixture-backed Spawn Architect proof for Battle PR2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .arena_battle_proof import _write_json
from .child_knowledge_packet import build_child_knowledge_packet, load_parent_combiner_receipt
from .tau_child_dag import COMMAND_SPEC_ROOT, build_child_exploit_tau_dag, validate_child_exploit_tau_dag, write_child_dag_command_specs, write_dag_yaml


SPAWN_ARCHITECT_RECEIPT_SCHEMA = "battle.spawn_architect_receipt.v1"
NORMALIZED_SCHEMA = "battle.spawn_architect_normalized.v1"


def run_spawn_architect_proof(*, battle_id: str, out_dir: Path, parent_combiner_proof: Path) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    parent_receipt = load_parent_combiner_receipt(parent_combiner_proof)
    spawn_policy = _spawn_policy_from_parent_combiner(parent_receipt)
    spawn_policy_path = _write_json(out_dir / "spawn-policy-decision.json", spawn_policy)
    events = [
        _event("spawn_policy_loaded", artifact="spawn-policy-decision.json", detail={"decision": spawn_policy["decision"]}),
        _event("spawn_architect_started", artifact=_parent_artifact(parent_combiner_proof), detail={"agentic": False}),
    ]

    child_packet = build_child_knowledge_packet(battle_id=battle_id, parent_combiner_receipt=parent_receipt)
    child_packet_path = _write_json(out_dir / "child-knowledge-packet.json", child_packet)
    events.append(_event("child_knowledge_packet_created", artifact="child-knowledge-packet.json", detail={"failed_specimens": len(child_packet["parent_specimens"])}))

    dag = build_child_exploit_tau_dag(battle_id=battle_id, child_knowledge_packet=child_packet, spawn_policy_decision=spawn_policy)
    command_spec_paths = write_child_dag_command_specs(out_dir / COMMAND_SPEC_ROOT)
    dag_path = write_dag_yaml(out_dir / "child-exploit-dag.yaml", dag)
    events.append(
        _event(
            "child_tau_dag_authored",
            artifact="child-exploit-dag.yaml",
            detail={"dag_id": dag["dag_id"], "command_specs": len(command_spec_paths)},
        )
    )

    validation = validate_child_exploit_tau_dag(dag)
    summary_path = _write_json(out_dir / "child-exploit-dag.summary.json", validation)
    validation_path = _write_json(out_dir / "validation.json", validation)
    events.append(_event("child_tau_dag_validated", artifact="validation.json", detail={"valid": validation["valid"]}))
    events.append(_event("child_tau_dag_private_boundary_passed", artifact="validation.json", detail={"private_boundary_passed": validation["private_boundary_passed"]}))
    events.append(_event("child_tau_execution_deferred", artifact="child-exploit-dag.summary.json", detail={"tau_execution": "deferred_to_pr3"}))

    scoreboard = {
        "schema": "battle.spawn_architect_scoreboard.v1",
        "battle_id": battle_id,
        "child_knowledge_packets": 1,
        "child_tau_dags_authored": 1,
        "child_tau_dags_validated": 1 if validation["valid"] else 0,
        "live_tau_executions": 0,
        "child_exploits_materialized": 0,
        "judge_verified_exploits": 0,
        "verdict": "DAG_BIRTH_CONTRACT_VALID" if validation["valid"] else "DAG_BIRTH_CONTRACT_INVALID",
    }
    events.append(_event("spawn_architect_scoreboard_written", artifact="spawn-architect-receipt.json", detail={"verdict": scoreboard["verdict"]}))
    _write_events(out_dir / "events.jsonl", events)
    normalized_path = _write_json(out_dir / "normalized" / "battle-004-spawn-architect.normalized.json", _normalized_fixture(battle_id=battle_id, events=events, scoreboard=scoreboard))

    receipt = {
        "schema": SPAWN_ARCHITECT_RECEIPT_SCHEMA,
        "battle_id": battle_id,
        "scenario_id": str(parent_receipt.get("scenario_id") or "arena-zip-slip-import-001"),
        "status": "PASS" if validation["valid"] else "FAIL",
        "mocked": False,
        "live": "local_fixture_dag_authoring_and_validation",
        "agentic": False,
        "tau_execution": "deferred_to_pr3",
        "proof_mode": "spawn_architect_fixture_dag_birth",
        "parent_combiner_proof": _parent_artifact(parent_combiner_proof),
        "artifacts": {
            "spawn_policy_decision": _rel(out_dir, spawn_policy_path),
            "child_knowledge_packet": _rel(out_dir, child_packet_path),
            "child_exploit_dag": _rel(out_dir, dag_path),
            "child_exploit_dag_summary": _rel(out_dir, summary_path),
            "child_tau_command_specs": COMMAND_SPEC_ROOT,
            "validation": _rel(out_dir, validation_path),
            "events": "events.jsonl",
            "normalized": _rel(out_dir, normalized_path),
        },
        "spawn_policy": spawn_policy,
        "validation": validation,
        "scoreboard": scoreboard,
        "claims": {
            "proves": [
                "Battle can construct a child knowledge packet from parent specimen evidence.",
                "Battle can author a Tau child exploit-synthesis DAG contract.",
                "Battle can validate that the DAG references only public Arena artifacts and parent-approved knowledge.",
                "Battle can preserve spawn/lineage intent without materializing a child exploit.",
            ],
            "does_not_prove": [
                "Tau executed the DAG.",
                "A child exploit subagent ran.",
                "A child exploit specimen was generated.",
                "Any exploit code compiled.",
                "Any exploit code contacted the target.",
                "Any exploit succeeded.",
                "Any Blue detection, kill, or block occurred.",
            ],
        },
    }
    _write_json(out_dir / "spawn-architect-receipt.json", receipt)
    return receipt


def _spawn_policy_from_parent_combiner(parent_receipt: dict[str, Any]) -> dict[str, Any]:
    scoreboard = parent_receipt.get("scoreboard") if isinstance(parent_receipt.get("scoreboard"), dict) else {}
    stalled_evidence = int(scoreboard.get("compile_failed") or 0) + int(scoreboard.get("runtime_failed") or 0)
    return {
        "schema": "battle.spawn_policy_decision.v1",
        "status": "ALLOWED_STALLED_PRE_TERMINAL",
        "decision": "ALLOWED_STALLED_PRE_TERMINAL",
        "reason": "parent combiner produced compile/runtime failures and remains non-terminal; PR2 materializes DAG birth contract only",
        "parent_terminal": False,
        "strategic_pre_kill_proven": False,
        "materialized_child": False,
        "evidence_refs": ["parent-combiner/run-receipt.json"],
        "stalled_evidence_count": stalled_evidence,
        "claims": {
            "proves": ["Battle spawn policy can authorize a child DAG planning pass from stalled non-terminal parent evidence."],
            "does_not_prove": ["A child exploit spawned.", "Strategic pre-kill replication occurred.", "Blue pressure was detected."],
        },
    }


def _normalized_fixture(*, battle_id: str, events: list[dict[str, Any]], scoreboard: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": NORMALIZED_SCHEMA,
        "battle_id": battle_id,
        "mocked": False,
        "live": "local_fixture_dag_authoring_and_validation",
        "proof_mode": "spawn_architect_fixture_dag_birth",
        "events": events,
        "scoreboard": scoreboard,
        "claims": {
            "proves": ["Backend emitted normalized Spawn Architect semantic events."],
            "does_not_prove": ["Tau DAG execution.", "Child exploit materialization.", "Exploit success."],
        },
    }


def _event(event_type: str, *, artifact: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {"event_type": event_type, "artifact": artifact, "detail": detail}


def _write_events(path: Path, events: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(event, sort_keys=True) + "\n" for event in events), encoding="utf-8")


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _parent_artifact(parent_combiner_proof: Path) -> str:
    return str(parent_combiner_proof)
