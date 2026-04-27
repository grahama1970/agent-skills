"""test_ask_oracle_protocols - ask.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import json

import ask.ask_oracle as ask_oracle


def _fake_protocol_turn(*, model, prompt, persona, turn_number, backend, **_kwargs):
    if persona == "moderator":
        return (
            "## Consensus\nFormal methods matter when assurance cost is justified.\n"
            "## Disagreements\nAdoption burden remains unresolved.",
            model,
            "",
        )
    content = json.dumps(
        {
            "speaker": persona,
            "protocol_role": "failure_mode",
            "summary": f"{persona} reviewed the artifact",
            "claims": [{"id": f"C{turn_number}", "text": f"{persona} claim", "confidence": "medium"}],
            "critiques": [
                {
                    "target_claim": "prompt claim",
                    "issue_type": "unsupported",
                    "severity": "high",
                    "critique": f"{persona} needs evidence",
                    "proposed_fix": "Add evidence",
                }
            ],
            "blocking_findings": [f"{persona} blocker"],
            "open_issues": [f"{persona} issue"],
        }
    )
    return content, model, ""


def test_roundtable_protocol_runs_sequential_turns(monkeypatch):
    calls = []

    def fake_turn(**kwargs):
        calls.append((kwargs["persona"], kwargs["turn_number"]))
        return _fake_protocol_turn(**kwargs)

    monkeypatch.setattr(ask_oracle, "_run_protocol_turn", fake_turn)

    content, model_served, turns, state = ask_oracle._run_roundtable_protocol(
        model="gpt-5.5",
        reasoning_effort="xhigh",
        timeout=30,
        idle_timeout=30,
        heartbeat_interval=5,
        base_prompt="Question: Is this sound?",
        backend="scillm",
        persona_specs="Brandon:failure_mode,Margaret:evidence_auditor,Jennifer:complexity_minimizer",
        role_preset="adversarial-review",
        rounds=2,
        mode="adversarial",
        persist="summary",
        state={"claims": [], "critiques": [], "open_issues": [], "turns": [], "parallel_reviews": [], "roundtable_turns": []},
    )

    assert model_served == "gpt-5.5"
    assert "Consensus" in content
    assert calls == [
        ("Brandon", 1),
        ("Margaret", 2),
        ("Jennifer", 3),
        ("Brandon", 4),
        ("Margaret", 5),
        ("Jennifer", 6),
        ("moderator", 7),
    ]
    assert len(state["roundtable_turns"]) == 6
    assert len(state["claims"]) == 6
    assert len(state["critiques"]) == 6
    assert len(turns) == 7


def test_parallel_review_protocol_runs_all_reviewers(monkeypatch):
    calls = []

    def fake_turn(**kwargs):
        calls.append(kwargs["persona"])
        return _fake_protocol_turn(**kwargs)

    monkeypatch.setattr(ask_oracle, "_run_protocol_turn", fake_turn)
    state = {"claims": [], "critiques": [], "open_issues": [], "turns": [], "parallel_reviews": [], "roundtable_turns": []}

    summary, model_served, turns, state = ask_oracle._run_parallel_review_protocol(
        model="gpt-5.5",
        reasoning_effort="xhigh",
        timeout=30,
        idle_timeout=30,
        heartbeat_interval=5,
        base_prompt="Question: Review this",
        backend="scillm",
        reviewer_count=3,
        reviewer_specs=None,
        reviewer_focus="correctness,tests,maintainability",
        role_preset="adversarial-review",
        state=state,
    )

    assert model_served == "gpt-5.5"
    assert set(calls) == {"correctness", "tests", "maintainability"}
    assert len(turns) == 3
    assert len(state["parallel_reviews"]) == 3
    assert len(state["critiques"]) == 3
    assert "correctness" in summary
