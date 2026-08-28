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
