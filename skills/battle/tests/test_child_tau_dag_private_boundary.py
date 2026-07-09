from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from battle_skill.child_knowledge_packet import build_child_knowledge_packet
from battle_skill.exploit_combiner import run_exploit_combiner_proof
from battle_skill.spawn_architect import _spawn_policy_from_parent_combiner
from battle_skill.tau_child_dag import build_child_exploit_tau_dag, validate_child_exploit_tau_dag


SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def _build_valid_dag(tmp_path: Path) -> dict:
    parent = run_exploit_combiner_proof(
        battle_id="battle-004",
        out_dir=tmp_path / "combiner",
        max_attempts=4,
        docker_image="python:3.12-slim",
        model="not-used",
        scillm_base_url="not-used",
    )
    packet = build_child_knowledge_packet(battle_id="battle-004", parent_combiner_receipt=parent)
    return build_child_exploit_tau_dag(
        battle_id="battle-004",
        child_knowledge_packet=packet,
        spawn_policy_decision=_spawn_policy_from_parent_combiner(parent),
    )


def test_child_tau_dag_validates_required_route_and_claim_boundary(tmp_path: Path) -> None:
    dag = _build_valid_dag(tmp_path)
    summary = validate_child_exploit_tau_dag(dag)
    jsonschema.validate(summary, _load_schema("battle.child_exploit_tau_dag_summary.v1.schema.json"))

    assert dag["schema"] == "tau.dag_contract.v1"
    assert dag["dag_id"] == "battle-004-child-spawn-synthesis-0001"
    assert dag["goal"]["goal_hash"].startswith("sha256:")
    assert dag["entry_node"] == "lineage-summarizer"
    assert "battle-handoff-writer" in dag["terminal_nodes"]
    assert summary["valid"] is True
    assert summary["private_boundary_passed"] is True
    assert summary["tau_execution"] == "deferred_to_pr3"
    assert "compile_failed_twice_requires_new_research" in {edge.get("condition") for edge in dag["edges"]}
    assert "exploit success" not in " ".join(dag["claims"]["proves"]).lower()


def test_child_tau_dag_rejects_private_artifact_reference(tmp_path: Path) -> None:
    dag = _build_valid_dag(tmp_path)
    dag["target"]["arena_public_bundle"].append("arena/private/actual")

    summary = validate_child_exploit_tau_dag(dag)

    assert summary["valid"] is False
    assert summary["private_boundary_passed"] is False
    assert any("private artifact" in error for error in summary["errors"])
