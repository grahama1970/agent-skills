"""Regression tests for pipeline-self-repair deterministic core."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import importlib.util

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "pipeline_self_repair.py"
SPEC = importlib.util.spec_from_file_location("pipeline_self_repair", MODULE_PATH)
assert SPEC and SPEC.loader
psr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(psr)


def test_category_key_is_stable_and_agentic_eval_scoped() -> None:
    triage = psr.TriageResult(code="webgpt_preflight_logged_out", layer="surf", ambiguous=False)
    key, cid = psr._category("persona-dream", "Phase 11 / Kling Submit", triage, "skills/persona-dream", "grahama1970/agent-skills")
    assert key == "persona-dream/phase-11-kling-submit/webgpt-preflight-logged-out/skills-persona-dream/v1"
    assert cid == "agentic-evals:agent-skills:persona-dream-phase-11-kling-submit-webgpt-preflight-logged-out"


def test_ticket_binding_prefers_open_category_marker() -> None:
    disposition = psr._choose_ticket(
        [
            {"issue_ref": "grahama1970/agent-skills#5", "number": 5, "state": "CLOSED", "has_category_marker": True, "depends_on": []},
            {"issue_ref": "grahama1970/agent-skills#8", "number": 8, "state": "OPEN", "has_category_marker": True, "depends_on": []},
        ]
    )
    assert disposition is not None
    assert disposition.action == "bind_existing"
    assert disposition.issue_ref == "grahama1970/agent-skills#8"


def test_ticket_binding_flags_blocked_upstream() -> None:
    disposition = psr._choose_ticket(
        [{"issue_ref": "grahama1970/agent-skills#9", "number": 9, "state": "OPEN", "has_category_marker": True, "depends_on": ["grahama1970/agent-skills#7"]}]
    )
    assert disposition is not None
    assert disposition.action == "blocked_by_upstream"
    assert disposition.depends_on == ["grahama1970/agent-skills#7"]


def test_ticket_binding_ignores_broad_matches_without_category_or_triage_code() -> None:
    disposition = psr._choose_ticket(
        [
            {
                "issue_ref": "grahama1970/agent-skills#1173",
                "number": 1173,
                "state": "OPEN",
                "has_category_marker": False,
                "has_triage_code": False,
                "depends_on": [],
            }
        ]
    )
    assert disposition is None


def test_provider_unknown_spend_blocks_resubmission(tmp_path: Path) -> None:
    request = tmp_path / "request.json"
    request.write_text('{"prompt":"render"}')
    effect, inputs, outputs = psr._provider_effect(
        request_body=request,
        provider_task_id="",
        provider_response=None,
        media_urls=[],
        local_artifacts=[],
        spend_state=psr.SpendState.UNKNOWN,
    )
    assert inputs and not outputs
    assert effect["resubmission_allowed"] is False
    assert effect["next_legal_command"] == "reconcile_provider_effect_before_resubmit"


def test_append_event_hash_chain(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    triage = psr.TriageResult(code="pipeline_unclassified_test", ambiguous=True)
    payload = {
        "event_id": "evt_test_1",
        "occurred_at": psr._now(),
        "pipeline": "persona-dream",
        "run_id": "run-1",
        "step_id": "step-1",
        "repo": "grahama1970/agent-skills",
        "target": "skills/persona-dream",
        "raw_signal_sha256": psr._sha_bytes(b"boom"),
        "raw_signal_excerpt": "boom",
        "triage": triage.model_dump(),
        "category_key": "persona-dream/step-1/pipeline-unclassified-test/skills-persona-dream/v1",
        "failure_category_id": "agentic-evals:agent-skills:persona-dream-step-1-pipeline-unclassified-test",
        "fingerprint": psr._sha_json({"x": 1}),
        "repair_state": psr.RepairState.NEEDS_TRIAGE.value,
        "goal_hash": "sha256:" + "0" * 64,
        "goal_alignment": {"status": "PASS_COMPARED_TO_IMMUTABLE_GOAL", "project": "persona-dream"},
        "ticket": {"action": "ticket_skipped"},
    }
    first = psr._append_event(ledger, payload.copy())
    second_payload = payload.copy()
    second_payload["event_id"] = "evt_test_2"
    second = psr._append_event(ledger, second_payload)
    assert first.previous_event_hash is None
    assert second.previous_event_hash == first.event_hash
    assert len(ledger.read_text().splitlines()) == 2


def test_push_pull_monitoring_names_project_agent_and_research_boundary() -> None:
    plan = psr._push_pull_monitoring(
        ["run-123"],
        [Path("/tmp/ask-run")],
        ["grahama1970/agent-skills#1533"],
    )
    assert plan["owner"] == "project-agent"
    assert 'subagent_wait({"id":"run-123","nonBlocking":true})' in plan["push"]["pi_wake_subscriptions"]
    assert "skills/ask/run.sh status --run /tmp/ask-run --projection --json" in plan["pull"]["ask_status_commands"]
    assert "skills/ticket/run.sh lookup --issue 1533 --repo grahama1970/agent-skills" in plan["pull"]["ticket_status_commands"]
    assert "brave-search or $dogpile" in plan["pull"]["research_escalation"]


def test_monitor_cli_emits_push_pull_plan(tmp_path: Path) -> None:
    run_sh = Path(__file__).resolve().parents[1] / "run.sh"
    ledger = tmp_path / "replay_ledger.jsonl"
    proc = subprocess.run(
        [
            str(run_sh),
            "monitor",
            "--ledger",
            str(ledger),
            "--subagent-run-id",
            "run-123",
            "--skip-watchdog",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    data = json.loads(proc.stdout)
    assert data["schema"] == "pipeline_self_repair.monitor.v1"
    assert data["project_agent_role"]["owner"] == "project-agent"
    assert data["ledger"]["open_failure_count"] == 0
    assert data["monitoring"]["push"]["pi_wake_subscriptions"]


def test_parse_webgpt_ticket_blocks_requires_focused_fields() -> None:
    parsed = psr._parse_webgpt_ticket_blocks(
        """TICKET
Type: feature
Title: Add hardening cycle command
Target: skills/pipeline-self-repair
Current state: WebGPT output must be translated by hand.
Requested outcome: One command emits parsed ticket candidates and monitor receipt.
Route: backend_python_or_skill_runtime
Requested repair agent: agent-skill-maintainer
Scoped files: skills/pipeline-self-repair/scripts/pipeline_self_repair.py
Non-goals: broad memory refactor
Required proof: pipeline-self-repair sanity passes and hardening-cycle emits a receipt.
Failure code: TRIAGE_REQUIRED

NO_TICKET: Current scorecard is already a status fact, not an independently actionable repair.
"""
    )
    assert parsed["ticket_count"] == 1
    assert parsed["tickets"][0]["status"] == "READY"
    assert parsed["tickets"][0]["failure_code"] == "TRIAGE_REQUIRED"
    assert parsed["no_ticket_count"] == 1


def test_hardening_webgpt_prompt_redacts_browser_rejected_local_paths(tmp_path: Path) -> None:
    handoff_dir = tmp_path / "local"
    handoff_dir.mkdir()
    (handoff_dir / "HANDOFF.md").write_text("Use /home/graham/workspace/experiments/memory/file.json and ./run.sh; about ~6 cases")
    prompt = psr._hardening_webgpt_prompt(
        memory_repo=tmp_path,
        scorecard={"receipt": "/tmp/secret/receipt.json"},
        receipt={"path": "/mnt/storage12tb/skills/ask/outputs/run"},
        ledgers=[],
        ticket_refs=[],
        prior_ask_run_dirs=[Path("/home/graham/workspace/experiments/agent-skills/skills/ask")],
        focus="test",
    )
    assert "/home/graham" not in prompt
    assert "/tmp/" not in prompt
    assert "/mnt/" not in prompt
    assert "./run.sh" not in prompt
    assert "[local-path:" in prompt


def test_ticket_candidate_repo_comes_from_route_repo_hint() -> None:
    candidate = {
        "status": "READY",
        "type": "feature",
        "title": "Typed persistence",
        "target": "$memory skill-chain",
        "current_state": "missing",
        "requested_outcome": "typed records",
        "required_proof": "live proof",
        "failure_code": "MEMORY_TYPED_PERSISTENCE_UNSEALED",
        "route": "$ticket -> grahama1970/graph-memory-operator",
    }
    cmd = psr._ticket_candidate_command(candidate, "grahama1970/agent-skills", apply=False)
    assert cmd is not None
    assert "grahama1970/graph-memory-operator" in cmd
    route_index = cmd.index("--route") + 1
    assert cmd[route_index] == "backend_python_or_skill_runtime"


def test_watchdog_dispatch_targets_memory_project_for_graph_memory_operator(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, timeout=120):
        calls.append(cmd)
        return psr.CommandResult(command=cmd, returncode=0, stdout_excerpt='{"status":"COMPLETED","receipt_path":"/tmp/receipt.json"}')

    monkeypatch.setattr(psr, "_run_with_stdout", lambda cmd, timeout=120: (fake_run(cmd, timeout), '{"status":"COMPLETED","receipt_path":"/tmp/receipt.json"}'))
    result = psr._dispatch_watchdog_ticket(
        "grahama1970/graph-memory-operator#157",
        "grahama1970/graph-memory-operator",
        "agent-skills",
        enabled=True,
    )
    assert result["status"] == "COMPLETED"
    assert "memory" in calls[0]
    assert "157" in calls[0]


def test_ask_response_path_from_stdout_finds_handler_response(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    response = run_root / "node-artifacts" / "handler-webgpt" / "response.md"
    response.parent.mkdir(parents=True)
    response.write_text("NO_TICKET: fixture")
    join = run_root / "node-artifacts" / "join" / "node-receipt.json"
    join.parent.mkdir(parents=True)
    join.write_text("{}")
    stdout = json.dumps({"join_artifact_path": str(join)})
    assert psr._ask_response_path_from_stdout(stdout) == response


def test_hardening_cycle_cli_dry_run_emits_prompt_and_receipt(tmp_path: Path) -> None:
    run_sh = Path(__file__).resolve().parents[1] / "run.sh"
    proc = subprocess.run(
        [
            str(run_sh),
            "hardening-cycle",
            "--output-dir",
            str(tmp_path),
            "--skip-scorecard",
            "--skip-watchdog",
            "--skip-triage",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    data = json.loads(proc.stdout)
    assert data["schema"] == "pipeline_self_repair.hardening_cycle.v1"
    assert Path(data["prompt_path"]).exists()
    assert Path(data["receipt_path"]).exists()
    prompt = Path(data["prompt_path"]).read_text()
    assert "return ONLY zero or more TICKET blocks or NO_TICKET lines" in prompt
    assert data["project_agent_role"]["owner"] == "project-agent"


def test_hardening_cycle_cli_appends_replay_ledger_event(tmp_path: Path) -> None:
    run_sh = Path(__file__).resolve().parents[1] / "run.sh"
    ledger = tmp_path / "replay_ledger.jsonl"
    proc = subprocess.run(
        [
            str(run_sh),
            "hardening-cycle",
            "--output-dir",
            str(tmp_path / "cycle"),
            "--replay-ledger",
            str(ledger),
            "--skip-scorecard",
            "--skip-watchdog",
            "--skip-triage",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    data = json.loads(proc.stdout)
    assert data["replay_ledger"] == str(ledger)
    line = json.loads(ledger.read_text().strip())
    assert line["schema"] == "pipeline_self_repair.hardening_cycle_event.v1"
    assert line["event_type"] == "hardening_cycle.generated"
    assert line["event_hash"].startswith("sha256:")
    assert line["receipt_path"] == data["receipt_path"]


def test_resume_hardening_cycle_marks_blocked_ticket_and_appends_event(tmp_path: Path, monkeypatch) -> None:
    prior = tmp_path / "hardening-cycle-receipt.json"
    prior.write_text(json.dumps({
        "schema": "pipeline_self_repair.hardening_cycle.v1",
        "output_dir": str(tmp_path / "cycle"),
        "ticket_projections": [{"repo": "grahama1970/graph-memory-operator", "issue_ref": "grahama1970/agent-skills#157", "status": "CREATED"}],
        "watchdog_dispatches": [{"issue_ref": "grahama1970/agent-skills#157", "status": "NEEDS_ATTENTION", "receipt": {"status": "NEEDS_ATTENTION"}}],
    }))
    ledger = tmp_path / "replay_ledger.jsonl"
    monkeypatch.setattr(psr, "_github_issue_view", lambda issue_ref, skip=False: {
        "status": "PASS",
        "issue_ref": issue_ref,
        "state": "OPEN",
        "labels": ["agent-work", "agent-blocked"],
    })
    payload = psr._resume_hardening_cycle_payload(
        prior,
        replay_ledger=ledger,
        watchdog_project="memory",
        skip_ticket=False,
        skip_watchdog=True,
    )
    assert payload["status"] == "PASS"
    assert payload["followups"][0]["followup"]["state"] == "WATCHDOG_BLOCKED_NEEDS_ATTENTION"
    line = json.loads(ledger.read_text().strip())
    assert line["event_type"] == "hardening_cycle.resumed"
    assert line["repair_state"] == psr.RepairState.NEEDS_HUMAN.value
    assert line["ticket"]["issue_refs"] == ["grahama1970/graph-memory-operator#157"]


def test_missing_immutable_goal_fails_preflight_before_ledger(tmp_path: Path) -> None:
    run_sh = Path(__file__).resolve().parents[1] / "run.sh"
    ledger = tmp_path / "replay_ledger.jsonl"
    proc = subprocess.run(
        [
            str(run_sh),
            "record-failure",
            "--pipeline",
            "no-such-immutable-goal-project",
            "--step-id",
            "phase_01",
            "--run-id",
            "test-run",
            "--raw-signal",
            "expected complex pipeline failure",
            "--target",
            "skills/no-such-immutable-goal-project",
            "--run-root",
            str(tmp_path),
            "--ledger",
            str(ledger),
            "--skip-memory",
            "--skip-github",
            "--no-ticket",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "immutable goal preflight failed" in proc.stderr
    assert not ledger.exists()


def test_record_failure_cli_writes_replay_ledger(tmp_path: Path) -> None:
    run_sh = Path(__file__).resolve().parents[1] / "run.sh"
    ledger = tmp_path / "replay_ledger.jsonl"
    proc = subprocess.run(
        [
            str(run_sh),
            "record-failure",
            "--pipeline",
            "persona-dream",
            "--step-id",
            "phase_11_kling_submit",
            "--run-id",
            "test-run",
            "--raw-signal",
            "multi_prompt prompt exceeds 512 characters",
            "--layer",
            "kling",
            "--target",
            "skills/persona-dream",
            "--run-root",
            str(tmp_path),
            "--ledger",
            str(ledger),
            "--skip-memory",
            "--skip-github",
            "--no-ticket",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    data = json.loads(proc.stdout)
    assert data["status"] == "RECORDED_NEEDS_TRIAGE"
    line = json.loads(ledger.read_text().strip())
    assert line["event_type"] == "step.failed"
    assert line["triage"]["code"].startswith("kling_unclassified_")
    assert line["goal_alignment"]["status"] == "PASS_COMPARED_TO_IMMUTABLE_GOAL"
    assert line["goal_hash"].startswith("sha256:")
    assert line["ticket"]["action"] == "ticket_skipped"


def test_fold_categories_closes_previous_failed_event() -> None:
    failed = {
        "category_key": "persona-dream/phase16/x/target/v1",
        "blocking": True,
        "repair_state": psr.RepairState.NEEDS_TRIAGE.value,
        "ticket": {"issue_ref": None},
        "triage": {"code": "x"},
    }
    repaired = {
        **failed,
        "event_type": "step.repaired",
        "repair_state": psr.RepairState.CATEGORY_GREEN.value,
        "agentic_eval": {"report": {"path": "proof.json", "sha256": "sha256:0", "bytes": 2}},
    }
    folded = psr._fold_categories([failed, repaired])
    assert folded["persona-dream/phase16/x/target/v1"]["events"] == 2
    assert folded["persona-dream/phase16/x/target/v1"]["latest_state"] == psr.RepairState.CATEGORY_GREEN.value
