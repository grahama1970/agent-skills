"""test_ask_oracle_protocols - ask.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import json
import socket
import time
from pathlib import Path

import ask.ask_oracle as ask_oracle
import ask.oracle_adapters as oracle_adapters
from ask.run_state import AskRunState, read_status


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
    assert set(calls) == {"Failure Mode Analyst", "Test Proof Reviewer", "Complexity Minimizer"}
    assert len(turns) == 3
    assert len(state["parallel_reviews"]) == 3
    assert len(state["critiques"]) == 3
    assert "Failure Mode Analyst" in summary


def test_structured_review_protocol_enforces_global_timeout_before_moderator(monkeypatch):
    now = {"value": 100.0}

    def fake_parallel_review(**kwargs):
        now["value"] = 103.0
        state = kwargs["state"]
        state["parallel_reviews"].append({"summary": "slow reviewers completed"})
        return "slow reviewers completed", kwargs["model"], [{"iteration": 1}], state

    monkeypatch.setattr(ask_oracle.time, "time", lambda: now["value"])
    monkeypatch.setattr(ask_oracle, "_run_parallel_review_protocol", fake_parallel_review)

    try:
        ask_oracle._run_structured_review_protocol(
            model="gpt-5.5",
            reasoning_effort="high",
            timeout=2,
            idle_timeout=30,
            heartbeat_interval=5,
            base_prompt="Question: Review this",
            backend="subagent-runner",
            roundtable=False,
            roundtable_personas=None,
            roundtable_role_preset="adversarial-review",
            roundtable_rounds=1,
            roundtable_mode="adversarial",
            roundtable_persist="summary",
            parallel_review=True,
            parallel_reviewers=3,
            parallel_review_personas=None,
            parallel_review_focus="fail-closed",
            parallel_review_role_preset="adversarial-review",
        )
    except TimeoutError as exc:
        assert "moderator synthesis" in str(exc)
    else:
        raise AssertionError("expected global timeout before moderator synthesis")


def test_oracle_synthesis_preserves_model_alias_metadata(monkeypatch):
    alias_metadata = {
        "provider_hint": "opencode",
        "family": "kimi",
        "resolved_model": "opencode-go/kimi-k2.6",
        "raw_alias": "oc kimi",
        "source": "live-opencode-go-models",
    }
    result = {
        "question": "answer with one word",
        "scope": "ask",
        "items": [{"problem": "sanity", "solution": "The expected answer is READY."}],
        "answer": "The expected answer is READY.",
        "oracle": {
            "model_alias": alias_metadata,
            "dogpile_mode": "off",
            "dogpile_recommended": False,
        },
    }

    monkeypatch.setattr(ask_oracle, "_load_oracle_persona_profiles", lambda **_kwargs: {})
    monkeypatch.setattr(
        ask_oracle,
        "_run_oracle_iterations",
        lambda **_kwargs: ("READY", "opencode-go/kimi-k2.6", [{"iteration": 1}]),
    )

    ask_oracle._apply_oracle_synthesis(
        result,
        k=1,
        model="opencode-go/kimi-k2.6",
        reasoning_effort="high",
        timeout=30,
        idle_timeout=30,
        heartbeat_interval=5,
        persona=None,
        consult_personas=[],
        peer=None,
        iterations=1,
        backend="scillm",
        persona_model=None,
        peer_model=None,
        persona_scope="personas",
    )

    assert result["answer"] == "READY"
    assert result["oracle"]["model_alias"] == alias_metadata
    assert result["oracle"]["model_served"] == "opencode-go/kimi-k2.6"


def test_subagent_event_socket_receives_structured_events():
    event_socket, socket_path = oracle_adapters._open_subagent_event_socket("socket-test")
    assert event_socket is not None
    assert socket_path
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
            client.connect(socket_path)
            client.sendall(json.dumps({"kind": "session_heartbeat", "status": "running"}).encode("utf-8"))

        events = oracle_adapters._drain_subagent_event_socket(event_socket)

        assert events == [{"kind": "session_heartbeat", "status": "running"}]
    finally:
        oracle_adapters._close_subagent_event_socket(event_socket, socket_path)


def test_wait_for_subagent_session_mirrors_socket_events_to_parent_run(monkeypatch, tmp_path):
    monkeypatch.setattr(oracle_adapters, "_record_subagent_heartbeat", lambda *args, **kwargs: None)
    artifact_dir = tmp_path / "child"
    artifact_dir.mkdir()
    now = time.time()
    (artifact_dir / "status.json").write_text(
        json.dumps(
            {
                "session_id": "child-session",
                "task_id": "child-task",
                "status": "completed",
                "last_output_at": now,
                "status_reason": "done",
            }
        )
    )
    (artifact_dir / "events.jsonl").touch()
    event_socket, socket_path = oracle_adapters._open_subagent_event_socket("mirror-test")
    assert event_socket is not None
    assert socket_path
    run_state = AskRunState("parent-run", output_root=tmp_path)
    run_state.write_request({"command": "ask", "question": "mirror"})
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
            client.connect(socket_path)
            client.sendall(
                json.dumps(
                    {
                        "kind": "session_completed",
                        "status": "completed",
                        "payload": {"transcript_bytes": 123},
                    }
                ).encode("utf-8")
            )

        state = oracle_adapters._wait_for_subagent_session(
            Path("unused-runner"),
            str(artifact_dir),
            timeout=1,
            idle_timeout=30,
            heartbeat_interval=5,
            task_id="child-task",
            persona="oracle",
            model="gpt-5.5",
            turn_number=1,
            event_socket=event_socket,
            run_state=run_state,
        )

        parent_status = read_status("parent-run", tail_events=10, output_root=tmp_path)
        events = [event["event"] for event in parent_status["event_tail"]]
        assert state["status"] == "completed"
        assert "subagent_session_completed" in events
        assert parent_status["subagent"]["status"] == "completed"
        assert parent_status["subagent"]["transcript_bytes"] == 123
    finally:
        oracle_adapters._close_subagent_event_socket(event_socket, socket_path)


def test_mirrored_subagent_started_event_does_not_persist_prompt(tmp_path):
    run_state = AskRunState("sanitize-run", output_root=tmp_path)
    run_state.write_request({"command": "ask", "question": "sanitize"})

    oracle_adapters._mirror_subagent_event(
        run_state,
        {
            "kind": "session_started",
            "status": "running",
            "payload": {
                "command": ["codex", "exec", "secret prompt text"],
                "pid": 123,
                "pty_device": "/dev/pts/1",
            },
        },
        state={"session_id": "child", "status": "running", "last_output_at": time.time()},
        artifact_dir=str(tmp_path / "child"),
        task_id="child-task",
        persona="oracle",
        model="gpt-5.5",
        turn_number=1,
    )

    event_log = run_state.events_path.read_text(encoding="utf-8")
    assert "secret prompt text" not in event_log
    assert "command_argv_count" in event_log


def test_scillm_oracle_call_records_runtime_events(monkeypatch, tmp_path):
    run_state = AskRunState("scillm-oracle-events", output_root=tmp_path)
    run_state.write_request({"command": "ask", "question": "event smoke"})

    captured = {}

    class _StreamResponse:
        def raise_for_status(self):
            return None

        def iter_lines(self):
            yield 'data: {"model":"moonshotai/kimi-k2.6-20260420","choices":[{"delta":{"content":"ok"}}]}'
            yield "data: [DONE]"

    class _StreamContext:
        def __enter__(self):
            return _StreamResponse()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_stream(*args, **kwargs):
        captured.update(kwargs)
        return _StreamContext()

    monkeypatch.setattr(oracle_adapters.httpx, "stream", fake_stream)

    content, model_served = oracle_adapters._complete_oracle_call(
        model="opencode-go/kimi-k2.6",
        reasoning_effort="high",
        timeout=60,
        prompt="event smoke",
        run_state=run_state,
        iteration=1,
        persona="oracle",
    )

    events = run_state.events_path.read_text(encoding="utf-8")
    assert content == "ok"
    assert model_served == "moonshotai/kimi-k2.6-20260420"
    assert captured["json"]["stream"] is True
    assert captured["json"]["timeout"] == 60
    assert "oracle_scillm_call_started" in events
    assert "oracle_scillm_call_finished" in events
    assert "opencode-go/kimi-k2.6" in events
    assert "moonshotai/kimi-k2.6-20260420" in events


def test_wait_for_subagent_session_mirrors_terminal_status_without_socket_event(monkeypatch, tmp_path):
    monkeypatch.setattr(oracle_adapters, "_record_subagent_heartbeat", lambda *args, **kwargs: None)
    artifact_dir = tmp_path / "child-terminal"
    artifact_dir.mkdir()
    (artifact_dir / "status.json").write_text(
        json.dumps(
            {
                "session_id": "child-terminal",
                "task_id": "child-task",
                "status": "completed",
                "last_output_at": time.time(),
                "status_reason": "done",
                "exit_code": 0,
            }
        )
    )
    (artifact_dir / "events.jsonl").touch()
    run_state = AskRunState("parent-terminal", output_root=tmp_path)
    run_state.write_request({"command": "ask", "question": "terminal"})

    state = oracle_adapters._wait_for_subagent_session(
        Path("unused-runner"),
        str(artifact_dir),
        timeout=1,
        idle_timeout=30,
        heartbeat_interval=5,
        task_id="child-task",
        persona="oracle",
        model="gpt-5.5",
        turn_number=1,
        run_state=run_state,
    )

    parent_status = read_status("parent-terminal", tail_events=10, output_root=tmp_path)
    assert state["status"] == "completed"
    assert any(event["event"] == "subagent_session_completed" for event in parent_status["event_tail"])
