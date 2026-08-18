from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "monitor_herdr.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("monitor_herdr", SCRIPT)
assert SPEC and SPEC.loader
monitor = importlib.util.module_from_spec(SPEC)
sys.modules["monitor_herdr"] = monitor
SPEC.loader.exec_module(monitor)

import change_tracking  # noqa: E402
import cron_support  # noqa: E402
import goal_discovery  # noqa: E402
import project_context  # noqa: E402
import transcript_classifier  # noqa: E402
import workspace_sweep  # noqa: E402








































def test_goal_discovery_never_crosses_project_boundary(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    subdir = repo / "subdir"
    subdir.mkdir(parents=True)
    (repo / ".git").mkdir()
    (tmp_path / "GOAL.md").write_text("Parent goal must not leak into repo.", encoding="utf-8")

    result = goal_discovery.discover_immutable_goal(str(subdir), boundary=repo)

    assert result["found"] is False
























def test_goal_achieved_instruction_is_not_completion() -> None:
    text = "Do not claim Goal achieved until tests pass."

    assert transcript_classifier.transcript_goal_claim(text)["state"] == "none"


def test_goal_blocked_instruction_is_not_status_line() -> None:
    text = "Do not treat the words Goal blocked inside prose as a footer."

    assert transcript_classifier.transcript_goal_claim(text)["state"] == "none"


def test_old_attempts_do_not_satisfy_new_blocker(tmp_path: Path) -> None:
    receipt = tmp_path / "review.md"
    receipt.write_text("review", encoding="utf-8")
    text = f"""
    Immutable Goal: BLOCKED:old blocker
    Unblock Attempts: brave-search=USED:{receipt}; browser-oracle=USED:{receipt}

    Status/Phase: new blocker
    Immutable Goal: BLOCKED:new missing credential
    Evidence: none yet
    """

    assert transcript_classifier.exhausted_blocker_claim(text, project_root=tmp_path) is False


def test_empty_not_applicable_reason_is_invalid() -> None:
    assert transcript_classifier.valid_attempt_value("NOT_APPLICABLE:") is False


















def test_goal_file_symlink_escape_is_rejected(tmp_path: Path) -> None:
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    (outside / "GOAL.md").write_text("outside goal", encoding="utf-8")
    (project / "GOAL.md").symlink_to(outside / "GOAL.md")

    result = goal_discovery.discover_immutable_goal(str(project), boundary=project)

    assert result["found"] is False


def test_probe_text_names_human_brave_and_webgpt_routes() -> None:
    text = monitor.build_prompt({
        "pane_id": "w11:pG",
        "agent": "codex",
        "cwd": "/repo",
        "selection_reasons": ["early_stop"],
        "action": "restart_continue",
        "immutable_goal": {"found": False},
    })

    assert "Immutable Goal:" in text
    assert "RESUMING_NOW" in text
    assert "BLOCKED_NEEDS_HUMAN" in text
    assert "CAN_SELF_UNBLOCK_BRAVE_SEARCH" in text
    assert "CAN_SELF_UNBLOCK_WEBGPT" in text
    assert "Unblock Attempts:" in text
    # The resume prompt tells a stalled agent to work, and never re-interrogates it.
    assert "Are you blocked" not in text
    assert "Resume the work now" in text
    assert "do not ask which task to pick" in text
    assert "will not ask you again while nothing changes" in text
    assert "$brave-search" in text
    assert "$ask webgpt" in text
    assert "$ask webkimi" in text
    assert "$ticket" in text
    assert "Ticket Check:" in text
    assert "lease it, diagnose it, fix it" in text
    assert "browser-oracle=" in text
    assert "Strict stop rule:" in text
    assert "partial checkpoint" in text
    assert "Immutable Goal: NOT_MET" in text














def test_monitor_prompt_body_does_not_hide_prior_done_receipt() -> None:
    text = """
    Status/Phase: Stop-condition proof completed.
    Immutable Goal: DONE_WITH_RECEIPT
    Next: STOP_ALLOWED because the goal has a fresh receipt.
    Disposition: DONE_WITH_RECEIPT

    ─ Worked for 3m 22s ─────────────────────────────────────────────────────

    › You stopped or went idle while the transcript still shows follow-up work or no real blocker. Resume the task now.
      Ask the human only for a missing decision, credential, authority, acceptance choice, or external state you cannot obtain.
      Status/Phase: <one line>
      Immutable Goal: <known goal, UNKNOWN, or ACHIEVED_WITH_RECEIPT:path>
      Disposition: <choose exactly one of RESUMING_NOW | BLOCKED_NEEDS_HUMAN | DONE_WITH_RECEIPT>

      gpt-5.5 high · ~/workspace/experiments/sparta
    """

    current = transcript_classifier.latest_transcript_region(text)

    assert "external state" not in current
    assert transcript_classifier.transcript_goal_claim(current)["state"] == "unmet"


def test_wrapped_achieved_receipt_with_done_disposition_does_not_launder_missing_path() -> None:
    text = """
    Status/Phase: Stop-condition proof completed.
    Immutable Goal: ACHIEVED_WITH_RECEIPT:/tmp/codex-ui-verification/sparta/sparta-threat-matrix-goal-stop-
      condition/20260721T1110Z-selected-rd0003.json
    Next: STOP_ALLOWED because the goal has a fresh receipt.
    Disposition: DONE_WITH_RECEIPT
    """

    assert transcript_classifier.transcript_goal_claim(text)["state"] == "unmet"


def test_existing_project_receipt_allows_achieved_stop(tmp_path: Path) -> None:
    receipt = tmp_path / ".codex" / "ui-verification" / "latest.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text('{"ok":true}', encoding="utf-8")
    text = f"""
    Status/Phase: Stop-condition proof completed.
    Immutable Goal: ACHIEVED_WITH_RECEIPT:{receipt}
    Evidence: {receipt}; command=verify-ui-cdp
    Next: STOP_ALLOWED because the goal has a fresh receipt.
    Disposition: DONE_WITH_RECEIPT
    """

    assert transcript_classifier.transcript_goal_claim(text, project_root=tmp_path)["state"] == "achieved"








def test_existing_receipt_without_duplicate_evidence_line_allows_stop(tmp_path: Path) -> None:
    receipt = tmp_path / ".codex" / "ui-verification" / "latest.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text('{"ok":true}', encoding="utf-8")
    text = f"""
    Status/Phase: Stop-condition proof completed.
    Immutable Goal: ACHIEVED_WITH_RECEIPT:{receipt}
    Next: STOP_ALLOWED because the goal has a fresh receipt.
    Disposition: DONE_WITH_RECEIPT
    """

    assert transcript_classifier.transcript_goal_claim(text, project_root=tmp_path)["state"] == "achieved"


def test_out_of_project_receipt_does_not_allow_stop(tmp_path: Path) -> None:
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    receipt = outside / "receipt.json"
    receipt.write_text("{}", encoding="utf-8")
    text = f"Immutable Goal: ACHIEVED_WITH_RECEIPT:{receipt}\nDisposition: DONE_WITH_RECEIPT\n"

    assert transcript_classifier.transcript_goal_claim(text, project_root=project)["state"] == "unmet"
















def test_confirmed_prompt_uses_full_cooldown() -> None:
    prompt_state = {"input_modified": True, "submit_confirmed": True}

    assert monitor.cooldown_for_prompt_state(
        prompt_state,
        cooldown_seconds=3600,
        unconfirmed_cooldown_seconds=600,
    ) == 3600


def test_unconfirmed_prompt_uses_shorter_retry_cooldown() -> None:
    prompt_state = {"input_modified": True, "submit_confirmed": False}

    assert monitor.cooldown_for_prompt_state(
        prompt_state,
        cooldown_seconds=3600,
        unconfirmed_cooldown_seconds=600,
    ) == 600


def test_install_cron_renders_ten_minute_apply_line() -> None:
    exit_code, payload = monitor.install_cron(
        apply=False,
        minute="*/10",
        space="codex",
        apply_prompts=True,
        cwd_prefix="/home/graham/workspace/experiments",
    )

    assert exit_code == 0
    assert payload["status"] == "DRY_RUN"
    assert payload["cron_line"].startswith("*/10 * * * *")
    assert "MONITOR_HERDR_INVOCATION_SOURCE=cron" in payload["cron_line"]
    assert "tick --apply" in payload["cron_line"]
    assert "--space 'codex'" in payload["cron_line"]
    assert "--min-stopped-seconds 600" in payload["cron_line"]
    assert payload["min_stopped_seconds"] == 600
    assert monitor.CRON_MARKER in payload["cron_line"]






















def test_invalid_cron_fields_are_rejected() -> None:
    exit_code, payload = monitor.install_cron(
        apply=False,
        minute="*/5",
        space="codex",
        apply_prompts=True,
        cwd_prefix="/home/graham/workspace/experiments",
    )

    assert exit_code == 2
    assert payload["status"] == "BLOCKED"
    assert payload["error"] == "minute_must_be_exactly_every_10"


def test_scheduler_health_reports_not_installed_without_prompting() -> None:
    health = cron_support.scheduler_health(
        cron_installed=False,
        latest_receipt={},
        stale_after_seconds=900,
    )

    assert health["status"] == "NOT_INSTALLED"
    assert health["backend"] == "cron"
    assert health["cron_installed"] is False


def test_scheduler_health_reports_stale_latest_receipt() -> None:
    health = cron_support.scheduler_health(
        cron_installed=True,
        latest_receipt={"path": "/tmp/receipt.json", "readable": True, "age_seconds": 1200, "ok": True, "status": "OBSERVED"},
        stale_after_seconds=900,
    )

    assert health["status"] == "STALE"
    assert health["latest_receipt_path"] == "/tmp/receipt.json"


def test_latest_receipt_summary_counts_confirmed_prompts(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        """{
          "run_id": "monitor-herdr-test",
          "status": "RESTART_PROMPTS_SUBMITTED",
          "ok": true,
          "invocation_source": "cron",
          "mocked": false,
          "live": true,
          "observed_panes": 2,
          "selected_panes": [{"pane_id": "w1:p1"}],
          "prompts": [{"submit_confirmed": true}]
        }""",
        encoding="utf-8",
    )

    summary = cron_support.latest_receipt_summary(receipt)

    assert summary["readable"] is True
    assert summary["status"] == "RESTART_PROMPTS_SUBMITTED"
    assert summary["invocation_source"] == "cron"
    assert summary["selected_panes"] == 1
    assert summary["prompts"] == 1
    assert summary["submit_confirmed"] == [True]


def test_latest_cron_receipt_ignores_newer_manual_receipt(tmp_path: Path) -> None:
    older_cron = tmp_path / "cron" / "receipt.json"
    newer_cli = tmp_path / "cli" / "receipt.json"
    older_cron.parent.mkdir()
    newer_cli.parent.mkdir()
    older_cron.write_text('{"run_id":"cron","invocation_source":"cron","status":"OBSERVED","ok":true}', encoding="utf-8")
    newer_cli.write_text('{"run_id":"cli","invocation_source":"cli","status":"OBSERVED","ok":true}', encoding="utf-8")

    summary = cron_support.latest_cron_receipt_summary([newer_cli, older_cron])

    assert summary["run_id"] == "cron"
    assert summary["invocation_source"] == "cron"


def test_corrupt_state_suppresses_input() -> None:
    original = monitor.STATE_PATH
    try:
        monitor.STATE_PATH = Path("/tmp/monitor-confused-corrupt-state-test.json")
        monitor.STATE_PATH.write_text("{not-json", encoding="utf-8")
        state = monitor.load_state()
    finally:
        monitor.STATE_PATH.unlink(missing_ok=True)
        monitor.STATE_PATH = original

    assert state["input_suppressed"] is True
    assert state["state_error"] == "corrupt_json"


# --- no-change suppression -------------------------------------------------


def test_unchanged_state_and_transcript_suppresses_reprompt() -> None:
    signature = change_tracking.change_signature({"state_change_seq": 42}, "same transcript")
    prior = {
        "state_change_seq_at_prompt": 42,
        "transcript_digest_at_prompt": change_tracking.transcript_digest("same transcript"),
    }

    verdict = change_tracking.unchanged_since_prompt(signature, prior)

    assert verdict["unchanged"] is True
    assert verdict["reason"] == "no_agent_progress_since_last_prompt"


def test_advanced_state_change_seq_allows_reprompt() -> None:
    signature = change_tracking.change_signature({"state_change_seq": 43}, "same transcript")
    prior = {
        "state_change_seq_at_prompt": 42,
        "transcript_digest_at_prompt": change_tracking.transcript_digest("same transcript"),
    }

    verdict = change_tracking.unchanged_since_prompt(signature, prior)

    assert verdict["unchanged"] is False
    assert verdict["reason"] == "state_change_seq_advanced"


def test_changed_transcript_allows_reprompt_without_seq() -> None:
    signature = change_tracking.change_signature(None, "new work happened")
    prior = {"transcript_digest_at_prompt": change_tracking.transcript_digest("old text")}

    verdict = change_tracking.unchanged_since_prompt(signature, prior)

    assert verdict["unchanged"] is False
    assert verdict["reason"] == "transcript_changed"


def test_first_ever_prompt_is_never_suppressed() -> None:
    signature = change_tracking.change_signature({"state_change_seq": 1}, "text")

    assert change_tracking.unchanged_since_prompt(signature, {})["unchanged"] is False






# --- stale workspace sweep -------------------------------------------------


def test_disposable_workspace_without_live_agent_is_stale() -> None:
    verdict = workspace_sweep.classify_workspace(
        {"workspace_id": "w7G", "label": "rw-sanity-provider-readiness", "agent_status": "unknown", "pane_count": 1}
    )

    assert verdict["stale"] is True


def test_focused_workspace_is_never_stale() -> None:
    verdict = workspace_sweep.classify_workspace(
        {"workspace_id": "w7G", "label": "rw-sanity-x", "agent_status": "unknown", "pane_count": 1, "focused": True}
    )

    assert verdict["stale"] is False
    assert "focused_workspace_never_closed" in verdict["reasons"]


def test_workspace_with_live_agent_is_never_stale() -> None:
    verdict = workspace_sweep.classify_workspace(
        {"workspace_id": "w7G", "label": "rw-sanity-x", "agent_status": "working", "pane_count": 1}
    )

    assert verdict["stale"] is False
    assert "live_agent_status:working" in verdict["reasons"]


def test_real_project_workspace_is_never_stale() -> None:
    verdict = workspace_sweep.classify_workspace(
        {"workspace_id": "w11", "label": "codex", "agent_status": "unknown", "pane_count": 18}
    )

    assert verdict["stale"] is False
    assert "label_not_disposable" in verdict["reasons"]


def test_sweep_bounds_the_close_list() -> None:
    workspaces = [
        {"workspace_id": f"w{i}", "label": "rw-sanity-x", "agent_status": "unknown", "pane_count": 1}
        for i in range(10)
    ]

    payload = workspace_sweep.sweep_workspaces(workspaces, max_closes=3)

    assert payload["stale_total"] == 10
    assert payload["selected_total"] == 3
    assert payload["truncated"] is True


# --- resolved project context ---------------------------------------------


def test_skill_for_cwd_resolves_skill_name(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "skills" / "monitor-herdr" / "scripts").mkdir(parents=True)

    assert project_context.skill_for_cwd(str(root / "skills" / "monitor-herdr" / "scripts"), root) == "monitor-herdr"


def test_skill_for_cwd_returns_none_outside_skills(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)

    assert project_context.skill_for_cwd(str(root / "src"), root) is None


def test_context_lines_render_repo_skill_and_tickets() -> None:
    lines = project_context.context_lines({
        "repo": "grahama1970/agent-skills",
        "branch": "main",
        "project_root": "/repo",
        "skill": "monitor-herdr",
        "open_tickets": [{"number": 1221, "title": "project Tau agent runs"}],
        "tickets_source": "gh",
    })
    blob = "\n".join(lines)

    assert "grahama1970/agent-skills" in blob
    assert "branch main" in blob
    assert "monitor-herdr" in blob
    assert "#1221" in blob


def test_prompt_states_resolved_repo_skill_and_open_tickets() -> None:
    text = monitor.build_prompt({
        "pane_id": "w1:p1",
        "agent": "codex",
        "cwd": "/repo/skills/monitor-herdr",
        "action": "restart_continue",
        "selection_reasons": ["early_stop"],
        "immutable_goal": {"found": False},
        "project_context": {
            "repo": "grahama1970/agent-skills",
            "branch": "main",
            "project_root": "/repo",
            "skill": "monitor-herdr",
            "open_tickets": [{"number": 1221, "title": "project Tau agent runs"}],
            "tickets_source": "gh",
        },
    })

    assert "Repo: grahama1970/agent-skills" in text
    assert "Skill under work: monitor-herdr" in text
    assert "#1221" in text
    assert "Do not re-triage them from scratch" in text
