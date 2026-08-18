"""A node's ceiling must be fixed before launch and unwidenable after (#1403).

The failures guarded here are escalations that look like nothing: a reviewer
inheriting mutation tools because the ambient host has them, a worker writing
outside its declared paths, a resume swapping the model, or a runtime quietly
weakening the evidence a node must produce.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "src"))

from ask.launch_contract import (  # noqa: E402
    SCHEMA,
    ContractError,
    compile_contract,
    contract_digest,
    preflight_blocks,
    verify_runtime,
)


def _spec(**overrides) -> dict:
    spec = {
        "node_id": "handler-webgpt",
        "role": "worker",
        "goal_hash": "sha256:goal",
        "target_kind": "browser_seat",
        "target_selector": "webgpt",
        "adapter": "tau_opaque_compat",
        "tools": ["read", "search"],
        "skills": ["ask"],
        "effects": ["provider_call"],
        "allowed_paths": [],
        "write_intent": False,
        "required_evidence": ["response_receipt"],
        "timeout_seconds": 600,
        "max_attempts": 2,
    }
    spec.update(overrides)
    return spec


def test_a_contract_compiles_with_a_digest() -> None:
    contract = compile_contract(_spec())
    assert contract["schema"] == SCHEMA
    assert contract["digest"].startswith("sha256:")


def test_reordering_unordered_fields_does_not_change_the_digest() -> None:
    """Required proof 2: order is not intent."""
    a = compile_contract(_spec(tools=["read", "search"], skills=["ask"]))
    b = compile_contract(_spec(tools=["search", "read"], skills=["ask"]))
    assert a["digest"] == b["digest"]


@pytest.mark.parametrize(
    "change",
    [
        {"tools": ["read", "search", "write"]},
        {"target_selector": "webclaude"},
        {"allowed_paths": ["/repo"], "write_intent": True, "effects": ["provider_call", "filesystem_write"]},
        {"required_evidence": ["response_receipt", "screenshot"]},
        {"output_schema": "tau.agent_handoff.v1"},
    ],
)
def test_changing_a_ceiling_changes_the_digest(change: dict) -> None:
    """Required proof 2: capability, target, path, evidence and schema all count."""
    base = compile_contract(_spec())
    changed = compile_contract(_spec(**change))
    assert base["digest"] != changed["digest"]


def test_ephemeral_identities_never_reach_the_digest() -> None:
    """Required proof 3: a reassigned tab must not change the contract."""
    base = compile_contract(_spec())
    with_ephemeral = dict(base)
    with_ephemeral.update({"tab_id": "837389487", "run_dir": "/tmp/x", "created_at": 123.4})
    assert contract_digest(with_ephemeral) == base["digest"]


def test_an_unsupported_target_adapter_pair_fails_closed() -> None:
    """Required proof 5: a browser seat cannot claim native guarantees."""
    with pytest.raises(ContractError, match="unsupported target/adapter"):
        compile_contract(_spec(adapter="tau_native_agent"))


def test_an_unknown_effect_class_fails_closed() -> None:
    with pytest.raises(ContractError, match="unknown effect"):
        compile_contract(_spec(effects=["mine_bitcoin"]))


def test_contradictory_write_intent_fails_closed() -> None:
    """Required proof 5: declaring the effect without the intent, or vice versa."""
    with pytest.raises(ContractError, match="contradictory intent"):
        compile_contract(_spec(effects=["provider_call", "filesystem_write"], write_intent=False))
    with pytest.raises(ContractError, match="contradictory intent"):
        compile_contract(_spec(write_intent=True, allowed_paths=["/repo"]))


def test_write_intent_requires_a_path_scope() -> None:
    with pytest.raises(ContractError, match="requires at least one allowed path"):
        compile_contract(
            _spec(write_intent=True, allowed_paths=[], effects=["provider_call", "filesystem_write"])
        )


def test_a_runtime_that_matches_is_accepted() -> None:
    contract = compile_contract(_spec())
    receipt = verify_runtime(contract, {"tools": ["read", "search"], "required_evidence": ["response_receipt"]})
    assert receipt["accepted"] is True
    assert receipt["problems"] == []


def test_a_runtime_that_adds_a_tool_is_rejected() -> None:
    """Required proof 8: a reviewer must not inherit the host's mutation tools."""
    contract = compile_contract(_spec(role="reviewer", tools=["read"]))
    receipt = verify_runtime(contract, {"tools": ["read", "write", "shell"]})
    assert receipt["accepted"] is False
    assert any("tools widened" in p for p in receipt["problems"])


def test_a_runtime_that_adds_a_path_is_rejected() -> None:
    """Required proof 9: no writing outside the declared scope."""
    contract = compile_contract(
        _spec(write_intent=True, allowed_paths=["/repo/src"], effects=["provider_call", "filesystem_write"])
    )
    receipt = verify_runtime(contract, {"allowed_paths": ["/repo/src", "/etc"]})
    assert receipt["accepted"] is False
    assert any("allowed_paths widened" in p for p in receipt["problems"])


def test_a_runtime_that_adds_an_effect_is_rejected() -> None:
    contract = compile_contract(_spec(effects=["provider_call"]))
    receipt = verify_runtime(contract, {"effects": ["provider_call", "network"]})
    assert receipt["accepted"] is False
    assert any("effects widened" in p for p in receipt["problems"])


def test_a_runtime_that_raises_a_budget_is_rejected() -> None:
    contract = compile_contract(_spec(timeout_seconds=600, max_attempts=2))
    receipt = verify_runtime(contract, {"timeout_seconds": 3600})
    assert receipt["accepted"] is False
    assert any("timeout_seconds widened" in p for p in receipt["problems"])


def test_weakened_evidence_is_rejected() -> None:
    """Weakening evidence is how an unadmitted answer becomes a pass."""
    contract = compile_contract(_spec(required_evidence=["response_receipt", "sentinel"]))
    receipt = verify_runtime(contract, {"required_evidence": ["response_receipt"]})
    assert receipt["accepted"] is False
    assert any("required_evidence weakened" in p for p in receipt["problems"])


def test_a_changed_goal_hash_is_rejected() -> None:
    contract = compile_contract(_spec())
    receipt = verify_runtime(contract, {"goal_hash": "sha256:different"})
    assert receipt["accepted"] is False
    assert any("goal_hash changed" in p for p in receipt["problems"])


def test_model_substitution_is_rejected_unless_allowed() -> None:
    contract = compile_contract(_spec(model_requirements={"model": "gpt-5.5-high"}))
    receipt = verify_runtime(contract, {"model": "some-other-model"})
    assert receipt["accepted"] is False
    assert any("model substituted" in p for p in receipt["problems"])

    permitted = compile_contract(
        _spec(model_requirements={"model": "gpt-5.5-high"}, substitution_allowed=True)
    )
    assert verify_runtime(permitted, {"model": "some-other-model"})["accepted"] is True


def test_a_tighter_runtime_is_accepted_and_reported() -> None:
    """Required proof 6: tightening is a safety decision, not a violation."""
    contract = compile_contract(_spec(tools=["read", "search"]))
    receipt = verify_runtime(contract, {"tools": ["read"]})
    assert receipt["accepted"] is True
    assert any("tools tightened" in t for t in receipt["tightened"])


def test_runtime_binding_holds_the_ephemeral_identities() -> None:
    contract = compile_contract(_spec())
    receipt = verify_runtime(contract, {"tab_id": "837389487", "run_dir": "/tmp/run"})
    assert receipt["runtime_binding"]["tab_id"] == "837389487"
    assert "tab_id" not in contract


def _capability(state: str, attachment: bool | None, stale: bool = False) -> dict:
    return {
        "capabilities": [
            {
                "capability_id": "browser.webgpt",
                "state": state,
                "reason_code": "probe",
                "operations": {"text": True, "attachment": attachment},
                "stale": stale,
                "stale_reason": "ttl_expired" if stale else None,
            }
        ]
    }


def test_an_attachment_needing_node_blocks_on_a_seat_that_cannot_attach() -> None:
    """Required proof 7: block before submission, not after the prompt is in."""
    contract = compile_contract(_spec(output_mode="attachment"))
    blocks = preflight_blocks(contract, _capability("READY", attachment=False))
    assert any("cannot take attachments" in b for b in blocks)


def test_a_blocked_seat_blocks_the_node() -> None:
    contract = compile_contract(_spec())
    assert preflight_blocks(contract, _capability("BLOCKED", attachment=True))


def test_a_stale_readiness_blocks_the_node() -> None:
    """Ties #1405's stale flag to a refusal, which is required proof 10 there."""
    contract = compile_contract(_spec())
    blocks = preflight_blocks(contract, _capability("READY", attachment=True, stale=True))
    assert any("stale" in b for b in blocks)


def test_a_ready_fresh_seat_does_not_block() -> None:
    contract = compile_contract(_spec())
    assert preflight_blocks(contract, _capability("READY", attachment=True)) == []
