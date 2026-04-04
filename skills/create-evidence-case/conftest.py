"""Shared fixtures for create-evidence-case tests (v4 5-gate architecture)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from models import ClaimNode, EvidenceNode, GateResult, StrategyNode, VerdictNode


@pytest.fixture
def gate_results_all_pass() -> list[GateResult]:
    return [
        GateResult(
            gate="step_1_topic",
            passed=True,
            detail="category=compliance",
            data={"category": "compliance", "method": "assistant_classifier"},
        ),
        GateResult(
            gate="step_2_recall",
            passed=True,
            detail="4 QRAs, 3 entities, 2 overlap (extract_entities)",
            data={"qra_count": 4, "entity_count": 3, "overlap_count": 2},
        ),
        GateResult(
            gate="step_3_technique_bridge",
            passed=True,
            detail="Technique bridge: dominant=Harden (3/4 QRAs, 75% coherence), 2 techniques",
            data={"bridge_found": True, "technique_names": ["Harden", "Detect"]},
        ),
        GateResult(
            gate="step_4_decompose",
            passed=True,
            detail="2 sub-claims",
            data={"single_claim": False, "claims": ["[Harden] CM0028: protects firmware"]},
        ),
        GateResult(
            gate="step_5_lean4",
            passed=True,
            detail="provable=formalizable, proof=success",
            data={"prediction": "formalizable", "proof_attempted": True, "proof_success": True},
        ),
    ]


@pytest.fixture
def claim_node() -> ClaimNode:
    return ClaimNode(
        text="What SPARTA countermeasures protect against firmware tampering?",
        category="compliance",
        id="claim_001",
        control_ids=["CM0028", "SI-7(2)"],
    )


@pytest.fixture
def strategy_nodes() -> list[StrategyNode]:
    return [
        StrategyNode(
            name="agent_driven",
            skills=["/memory recall", "/extract-entities", "/lean4-prove"],
            id="strat_001",
            score=1.0,
            turns=5,
            selected=True,
        ),
    ]


@pytest.fixture
def evidence_nodes() -> list[EvidenceNode]:
    return [
        EvidenceNode(
            method="EXAMINE",
            layer="sparta_qra",
            id="ev_001",
            confidence=0.9,
            collector="agent_decision",
            result={
                "source": "sparta_qra",
                "qra_text": "CM0028 Tamper Protection prevents firmware manipulation.",
                "technique": "Harden",
            },
            control_ids=["CM0028"],
        ),
        EvidenceNode(
            method="EXAMINE",
            layer="sparta_qra",
            id="ev_002",
            confidence=0.8,
            collector="agent_decision",
            result={
                "source": "sparta_qra",
                "qra_text": "SI-7(2) supports integrity checks during maintenance.",
                "technique": "Detect",
            },
            control_ids=["SI-7(2)"],
        ),
    ]


@pytest.fixture
def verdict_node() -> VerdictNode:
    return VerdictNode(
        state="satisfied",
        grade="A+",
        score=1.0,
        strategy_id="strat_001",
        evidence_ids=["ev_001", "ev_002"],
        id="verdict_001",
        reasoning="Found 4 QRAs across techniques: Harden, Detect [Lean4 verified]",
        grader={"type": "agent_driven", "model_id": "", "modified_in_session": False},
    )


@pytest.fixture
def golden_case(
    claim_node: ClaimNode,
    strategy_nodes: list[StrategyNode],
    evidence_nodes: list[EvidenceNode],
    verdict_node: VerdictNode,
    gate_results_all_pass: list[GateResult],
) -> dict:
    return {
        "claim": claim_node.to_dict(),
        "strategies": [s.to_dict() for s in strategy_nodes],
        "evidence": [e.to_dict() for e in evidence_nodes],
        "verdict": verdict_node.to_dict(),
        "answer": verdict_node.reasoning,
        "gate_trace": [g.to_dict() for g in gate_results_all_pass],
        "gates_passed": 5,
        "gates_total": 5,
        "technique_groups": {"Harden": 3, "Detect": 1},
        "sub_claims": ["[Harden] CM0028: protects firmware"],
        "decomposition": {
            "id": "decomp_001",
            "question": claim_node.text,
            "given_components": ["firmware tampering"],
            "then_components": ["SPARTA countermeasures"],
            "component_queries": {
                "firmware tampering": "firmware tampering",
                "SPARTA countermeasures": "SPARTA countermeasures",
            },
            "component_entity_types": {
                "firmware tampering": "scope",
                "SPARTA countermeasures": "target",
            },
        },
        "component_results": {
            "firmware tampering": [
                {"control_id": "CM0028", "tactical_tags": ["Harden"], "question": "How to stop tampering?", "answer": "Use tamper protections."}
            ],
            "SPARTA countermeasures": [
                {"control_id": "SI-7(2)", "tactical_tags": ["Detect"], "question": "What detects tampering?", "answer": "Use integrity checks."}
            ],
        },
        "entities": {"all_control_ids": ["CM0028", "SI-7(2)"], "related_pairs": [{"source": "CM0028", "target": "SI-7(2)", "relation": "supports"}]},
        "lean4_result": {
            "prediction": "formalizable",
            "provable_confidence": 0.92,
            "proof_attempted": True,
            "proof_success": True,
            "code": "theorem firmware_safe : True := by trivial",
            "lemma_deps": [{"lemma": "firmware_safe", "imports": ["Mathlib"]}],
            "attempts": 1,
            "retrieval": {"retrieved": 2, "tactics_added": ["simp"]},
        },
    }


@pytest.fixture
def mock_memory(monkeypatch):
    """Patch httpx-based memory helpers in storage.py."""

    def fake_learn(problem, solution, scope, tags):
        return {"meta": {"ok": True}}

    def fake_recall(q, scope="", tags=None):
        return {"results": []}

    import storage
    monkeypatch.setattr(storage, "_run_memory_learn", fake_learn)
    monkeypatch.setattr(storage, "_run_memory_recall", fake_recall)
    return fake_learn


@pytest.fixture
def mock_skills(monkeypatch):
    """Patch _invoke_skill in runner.py to return canned evidence dicts."""

    def fake_invoke(run_sh, args, timeout=20, env=None):
        return {
            "items": [{"answer": "test data", "control_id": "CM0028", "tactical_tags": ["Harden"]}],
        }

    import collect
    monkeypatch.setattr(collect, "_invoke_skill", fake_invoke)
    return fake_invoke


@pytest.fixture
def tmp_storage(tmp_path, monkeypatch):
    """Redirect UCT cache + audit log to temp dirs."""
    uct_dir = tmp_path / "uct_cache"
    uct_dir.mkdir()
    audit_dir = tmp_path / "audit_logs"
    audit_dir.mkdir()

    import storage
    monkeypatch.setattr(storage, "UCT_CACHE", uct_dir)
    monkeypatch.setattr(storage, "AUDIT_LOG", audit_dir)
    monkeypatch.setattr(storage, "STORAGE_ROOT", tmp_path)
    return tmp_path
