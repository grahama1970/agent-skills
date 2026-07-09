from __future__ import annotations

import json
from pathlib import Path

from battle_skill.child_dag_node_adapter import run_node
from battle_skill.exploit_combiner import run_exploit_combiner_proof
from battle_skill.spawn_architect import run_spawn_architect_proof


def _start_payload(dag_path: Path) -> dict:
    return {
        "schema": "tau.agent_handoff.v1",
        "github": {"repo": "grahama1970/agent-skills", "target": "skills/battle"},
        "goal": {"goal_id": "battle-004-child-exploit-specimen", "goal_version": 1, "goal_hash": "sha256:test"},
        "previous_subagent": "human",
        "context": {"summary": "Dispatch test.", "artifacts": [str(dag_path)]},
        "result": {"status": "DAG_DISPATCH_REQUESTED", "summary": "dispatch", "evidence": []},
        "rationale": "test",
        "next_agent": {"name": "lineage-summarizer", "executor": "local", "reason": "test"},
        "required_evidence": ["child_knowledge_packet.json"],
        "stop_condition": "test",
    }


def _spawn_architect_dir(tmp_path: Path) -> Path:
    combiner = tmp_path / "combiner"
    run_exploit_combiner_proof(
        battle_id="battle-004",
        out_dir=combiner,
        max_attempts=4,
        docker_image="python:3.12-slim",
        model="not-used",
        scillm_base_url="not-used",
    )
    spawn = tmp_path / "spawn-architect"
    run_spawn_architect_proof(battle_id="battle-004", out_dir=spawn, parent_combiner_proof=combiner)
    return spawn


def test_lineage_summarizer_adapter_emits_handoff_and_receipts(tmp_path: Path, monkeypatch) -> None:
    spawn = _spawn_architect_dir(tmp_path)
    artifact_dir = tmp_path / "artifacts" / "lineage-summarizer"
    monkeypatch.setenv("TAU_HANDOFF_SELECTED_AGENT", "lineage-summarizer")
    response, exit_code = run_node(
        node_id="lineage-summarizer",
        start_payload=_start_payload(spawn / "child-exploit-dag.yaml"),
        artifact_dir=artifact_dir,
    )

    assert exit_code == 0
    assert response is not None
    assert response["previous_subagent"] == "lineage-summarizer"
    assert response["next_agent"]["name"] == "research-scout"
    assert (artifact_dir / "lineage_summary.json").exists()
    receipt = json.loads((artifact_dir / "lineage-summarizer-node-receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "PASS"
    assert receipt["fixture_fallback_used"] is False


def test_research_scout_adapter_blocks_without_fake_research(tmp_path: Path, monkeypatch) -> None:
    artifact_dir = tmp_path / "artifacts" / "research-scout"
    monkeypatch.setenv("TAU_HANDOFF_SELECTED_AGENT", "research-scout")
    response, exit_code = run_node(
        node_id="research-scout",
        start_payload=_start_payload(tmp_path / "child-exploit-dag.yaml"),
        artifact_dir=artifact_dir,
    )

    assert response is None
    assert exit_code == 1
    receipt = json.loads((artifact_dir / "research-scout-node-receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "BLOCKED"
    assert receipt["verdict"] == "RESEARCH_ADAPTER_MISSING"
    assert receipt["fixture_fallback_used"] is False
    assert not (artifact_dir / "research_receipts.json").exists()
