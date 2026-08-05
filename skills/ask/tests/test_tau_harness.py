"""Tests for the Tau-native execution seam (agent-skills#1220).

Deterministic: Tau's real compiler and scheduler run, but the node executor
is injected, so no provider is contacted. The live path is covered by
scripts/ask_tau_native_canary.py and the live intent smoke.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ask.tau_harness import (
    TauHarnessUnavailable,
    build_single_agent_spec,
    run_single_tau_agent,
)


def _fake_execute(final_text: str):
    def execute(plan_node: Any, accepted_inputs: Any, execution: Any) -> dict[str, Any]:
        return {
            "node_id": plan_node.node_id,
            "status": "PASS",
            "verdict": "PASS",
            "accepted_output": {
                "final_text": final_text,
                "settlement": {"state": "completed"},
            },
            "errors": [],
        }

    return execute


def test_single_agent_spec_shape(tmp_path: Path) -> None:
    spec = build_single_agent_spec(
        prompt="say hi", profile_id="codex-model-turn", run_id="r1", run_dir=tmp_path
    )
    assert spec["schema"] == "tau.generic_dag_spec.v1"
    node = spec["nodes"][0]
    assert node["tau_agent"]["model"] == "profile:codex-model-turn"
    assert node["tau_agent"]["allowed_paths"] == []
    assert node["max_attempts"] == 1


def test_run_single_tau_agent_via_tau_scheduler(tmp_path: Path) -> None:
    outcome = run_single_tau_agent(
        prompt="classify this",
        profile_id="codex-model-turn",
        purpose="unit-test",
        execute_node=_fake_execute('{"intent": "OS_QUERY", "confidence": 0.9}'),
        run_root=tmp_path,
    )
    assert outcome["scheduler_status"] == "PASS"
    assert outcome["settlement"]["state"] == "completed"
    assert '"intent"' in outcome["final_text"]


def test_unavailable_tau_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAU_REPO", str(tmp_path / "nope"))
    with pytest.raises(TauHarnessUnavailable):
        run_single_tau_agent(
            prompt="x", profile_id="p", purpose="t", execute_node=_fake_execute("x"), run_root=tmp_path
        )


def test_intent_parses_tau_final_text(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from ask import ask_intent

    def fake_run(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["purpose"] == "intent-classify"
        return {
            "final_text": '{"intent": "OS_HEALTH", "confidence": 0.95, "persona": null, "subsystem": "memory"}',
            "run_id": "r",
            "run_dir": str(tmp_path),
            "scheduler_status": "PASS",
            "settlement": {"state": "completed"},
        }

    monkeypatch.delenv("ASK_DIRECT_INTENT_COMPAT", raising=False)
    import ask.tau_harness as th

    monkeypatch.setattr(th, "run_single_tau_agent", fake_run)
    result = ask_intent.classify_llm("is memory healthy?")
    assert result.intent == "OS_HEALTH"
    assert result.subsystem == "memory"


def test_intent_degrades_when_tau_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    from ask import ask_intent
    import ask.tau_harness as th

    def raise_unavailable(**kwargs: Any) -> dict[str, Any]:
        raise TauHarnessUnavailable("no tau")

    monkeypatch.delenv("ASK_DIRECT_INTENT_COMPAT", raising=False)
    monkeypatch.setattr(th, "run_single_tau_agent", raise_unavailable)
    result = ask_intent.classify_llm("anything")
    assert result.intent == "TOPIC_QUERY"
    assert result.confidence == 0.4


def test_run_chat_via_tau_flattens_system_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ask.tau_harness import run_chat_via_tau

    seen: dict[str, Any] = {}

    def capture(plan_node: Any, accepted_inputs: Any, execution: Any) -> dict[str, Any]:
        return {
            "node_id": plan_node.node_id,
            "status": "PASS",
            "verdict": "PASS",
            "accepted_output": {"final_text": "persona reply", "settlement": {"state": "completed"}},
            "errors": [],
        }

    monkeypatch.setenv("ASK_TAU_RUN_ROOT", str(tmp_path))
    text = run_chat_via_tau(
        user_prompt="question",
        system_prompt="you are Brandon",
        profile_id="claude-model-turn",
        purpose="unit-consult",
        execute_node=capture,
    )
    assert text == "persona reply"


def test_run_chat_via_tau_returns_none_when_unavailable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from ask.tau_harness import run_chat_via_tau

    monkeypatch.setenv("TAU_REPO", str(tmp_path / "missing"))
    assert (
        run_chat_via_tau(
            user_prompt="q", profile_id="p", purpose="t"
        )
        is None
    )


def test_consult_generate_response_routes_via_tau(monkeypatch: pytest.MonkeyPatch) -> None:
    from ask import consult
    import ask.tau_harness as th

    def fake_chat(**kwargs: Any) -> str:
        assert kwargs["purpose"] == "persona-consult"
        assert kwargs["profile_id"] == consult.CONSULT_PROFILE
        return "grounded persona answer"

    monkeypatch.delenv("ASK_DIRECT_SCILLM_COMPAT", raising=False)
    monkeypatch.setattr(th, "run_chat_via_tau", fake_chat)
    assert consult.generate_response("q", "sys") == "grounded persona answer"
