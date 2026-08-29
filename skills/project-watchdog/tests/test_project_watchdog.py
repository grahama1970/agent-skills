"""Unit tests for project-watchdog parsing, routing, locking, and receipt policy.

These are pure unit tests over the watchdog package. The behavioural acceptance
gates that exercise the real CLI against real files live in ``sanity.sh``.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from watchdog import (  # noqa: E402
    commands,
    config,
    core,
    github,
    handlers,
    issue_fields,
    registry,
    streaks,
)

TAU_REPO = "grahama1970/tau"


def _issue(number: int, *, labels: list[str], body: str = "") -> dict:
    return {
        "number": number,
        "title": f"issue {number}",
        "body": body,
        "labels": [{"name": name} for name in labels],
        "url": f"https://github.com/{TAU_REPO}/issues/{number}",
    }


# --------------------------------------------------------------------------- #
# Issue-body field parsing
# --------------------------------------------------------------------------- #


def test_parse_issue_fields_accepts_shell_style_values() -> None:
    fields = issue_fields.parse_issue_fields(
        'project-watchdog-action:tau-handoff-dispatch start="experiments/start handoff.json" '
        "max_steps=2 apply_transport=true"
    )
    assert fields["start"] == "experiments/start handoff.json"
    assert fields["max_steps"] == "2"
    assert fields["apply_transport"] == "true"


def test_parse_issue_fields_rejects_unbalanced_quotes() -> None:
    with pytest.raises(ValueError, match="not shell-parseable"):
        issue_fields.parse_issue_fields('start="unterminated')


@pytest.mark.parametrize("value", ["0", "-1", "abc", ""])
def test_parse_positive_int_rejects_non_positive(value: str) -> None:
    with pytest.raises(ValueError):
        issue_fields.parse_positive_int(value, field="max_steps")


@pytest.mark.parametrize("value", ["yes", "1", "TRUE!", ""])
def test_parse_bool_rejects_ambiguous_values(value: str) -> None:
    with pytest.raises(ValueError):
        issue_fields.parse_bool(value, field="apply_transport")


def test_parse_goal_hash_requires_sha256_prefix() -> None:
    with pytest.raises(ValueError, match="sha256:"):
        issue_fields.parse_goal_hash("deadbeef")
    assert issue_fields.parse_goal_hash(config.TAU_ACTIVE_GOAL_HASH)


# --------------------------------------------------------------------------- #
# Path containment — issue bodies are untrusted input
# --------------------------------------------------------------------------- #


def test_repo_relative_path_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="without '\\.\\.'"):
        issue_fields.repo_relative_existing_path("../outside.json", worktree=tmp_path)


def test_repo_relative_path_rejects_absolute(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="repo-relative"):
        issue_fields.repo_relative_existing_path("/etc/passwd", worktree=tmp_path)


def test_repo_relative_path_rejects_symlink_escape(tmp_path: Path) -> None:
    worktree = tmp_path / "repo"
    worktree.mkdir()
    outside = tmp_path / "secret.json"
    outside.write_text("{}", encoding="utf-8")
    (worktree / "link.json").symlink_to(outside)
    with pytest.raises(ValueError, match="escapes the project worktree"):
        issue_fields.repo_relative_existing_path("link.json", worktree=worktree)


def test_repo_relative_path_accepts_contained_file(tmp_path: Path) -> None:
    worktree = tmp_path / "repo"
    (worktree / "experiments").mkdir(parents=True)
    target = worktree / "experiments" / "start.json"
    target.write_text("{}", encoding="utf-8")
    resolved = issue_fields.repo_relative_existing_path("experiments/start.json", worktree=worktree)
    assert resolved == target.resolve()


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #


def test_routing_selects_generic_handoff_marker() -> None:
    issue = _issue(
        42,
        labels=["agent-work", "next:reviewer", "executor:local"],
        body="project-watchdog-action:tau-handoff-dispatch start=experiments/foo.json",
    )
    gh_result = {"exit_code": 0, "stdout": json.dumps([issue]), "stderr": ""}
    with mock.patch.object(registry, "run_cmd", return_value=gh_result):
        selected = registry.list_routable_issues("run-test", {"repo": TAU_REPO})
    assert len(selected) == 1
    assert selected[0]["watchdog_action"] == "tau_handoff_dispatch"


@pytest.mark.parametrize("state_label", ["agent-active", "agent-blocked"])
def test_routing_skips_leased_or_blocked_issue(state_label: str) -> None:
    issue = _issue(
        43,
        labels=["agent-work", state_label, "executor:local"],
        body="project-watchdog-action:tau-handoff-dispatch start=experiments/foo.json",
    )
    gh_result = {"exit_code": 0, "stdout": json.dumps([issue]), "stderr": ""}
    with mock.patch.object(registry, "run_cmd", return_value=gh_result):
        assert registry.list_routable_issues("run-test", {"repo": TAU_REPO}) == []


def test_ordinary_ticket_without_marker_is_now_routable() -> None:
    """The 41,607-NOOP fix: /ticket-filed issues must reach the router."""
    issue = _issue(
        44,
        labels=["agent-work", "type:bug", "route:backend_python_or_skill_runtime"],
        body="## Type\n\nbug\n\n## Target\n\nsrc/thing.py",
    )
    gh_result = {"exit_code": 0, "stdout": json.dumps([issue]), "stderr": ""}
    with mock.patch.object(registry, "run_cmd", return_value=gh_result):
        selected = registry.list_routable_issues(
            "run-test", {"repo": TAU_REPO, "worktree": "/tmp/x"}
        )
    assert len(selected) == 1
    assert selected[0]["watchdog_action"] == "ticket_repair"


def test_a_non_tau_project_is_routable(monkeypatch) -> None:
    """runner_kind no longer decides routability (#1044 revisited).

    The lane required `tau-command-loop` because it hand-authored a contract
    against Tau's own command-spec tree. $ask compiles the DAG for any repo, so
    the only structural requirement is a worktree to author in.
    """
    issue = _issue(
        45,
        labels=["agent-work", "type:bug", "route:backend_python_or_skill_runtime"],
        body="type: bug\ntarget: skills/x\n",
    )
    gh_result = {"exit_code": 0, "stdout": json.dumps([issue]), "stderr": ""}
    with mock.patch.object(registry, "run_cmd", return_value=gh_result):
        selected = registry.list_routable_issues(
            "run-test",
            {"repo": TAU_REPO, "project_id": "agent-skills",
             "runner_kind": "project-local", "worktree": "/tmp/x"},
        )

    assert [i["number"] for i in selected] == [45]
    assert registry.LAST_SCAN["unroutable_no_repair_lane"] == 0


def test_a_project_with_no_worktree_is_not_routable() -> None:
    """Nowhere to author the repair; claiming it only to block it is worse."""
    issue = _issue(
        47,
        labels=["agent-work", "type:bug", "route:backend_python_or_skill_runtime"],
        body="type: bug\ntarget: skills/x\n",
    )
    gh_result = {"exit_code": 0, "stdout": json.dumps([issue]), "stderr": ""}
    with mock.patch.object(registry, "run_cmd", return_value=gh_result):
        selected = registry.list_routable_issues(
            "run-test", {"repo": TAU_REPO, "project_id": "nowhere"}
        )
    assert selected == []
    assert registry.LAST_SCAN["unroutable_no_repair_lane"] == 1


def test_marker_routes_still_work_without_a_repair_lane() -> None:
    """Only ticket_repair depends on the lane; legacy marker routes do not."""
    issue = _issue(
        46,
        labels=["agent-work", "executor:local"],
        body=f"{config.TAU_HANDOFF_DISPATCH_MARKER}\nstart=experiments/start.json",
    )
    gh_result = {"exit_code": 0, "stdout": json.dumps([issue]), "stderr": ""}
    with mock.patch.object(registry, "run_cmd", return_value=gh_result):
        selected = registry.list_routable_issues(
            "run-test", {"repo": TAU_REPO, "runner_kind": "project-local"}
        )

    assert len(selected) == 1
    assert selected[0]["watchdog_action"] == "tau_handoff_dispatch"


def test_issue_without_ready_label_is_not_routable() -> None:
    issue = _issue(45, labels=["type:bug", "route:backend_python_or_skill_runtime"])
    assert registry.classify_issue(issue) is None


@pytest.mark.parametrize("hold", sorted(config.HUMAN_HOLD_LABELS))
def test_human_hold_labels_always_win(hold: str) -> None:
    """A maintainer parking a ticket must never be overridden by the router."""
    issue = _issue(46, labels=["agent-work", hold])
    assert registry.classify_issue(issue) is None


def test_body_markers_still_take_precedence_over_the_generic_route() -> None:
    issue = _issue(
        47,
        labels=["agent-work", "executor:local"],
        body="project-watchdog-action:tau-handoff-dispatch start=experiments/foo.json",
    )
    assert registry.classify_issue(issue) == "tau_handoff_dispatch"


def test_failed_scan_raises_and_is_never_reported_as_empty() -> None:
    """A scan that cannot reach GitHub must not look like an empty queue."""
    gh_result = {"exit_code": 1, "stdout": "", "stderr": "gh: auth required"}
    with mock.patch.object(registry, "run_cmd", return_value=gh_result):
        with pytest.raises(RuntimeError, match="gh issue list failed"):
            registry.list_routable_issues("run-test", {"repo": TAU_REPO})


# --------------------------------------------------------------------------- #
# Registry lookup
# --------------------------------------------------------------------------- #


def test_find_project_error_lists_registered_ids() -> None:
    projects = {"projects": [{"project_id": "tau"}, {"project_id": "scillm"}]}
    with pytest.raises(ValueError) as excinfo:
        registry.find_project(projects, "taau")
    message = str(excinfo.value)
    assert "taau" in message
    assert "scillm" in message and "tau" in message


def test_project_repo_requires_repo_field() -> None:
    with pytest.raises(ValueError, match="no 'repo' field"):
        registry.project_repo({"project_id": "orphan"})


def test_real_registry_entries_are_all_addressable() -> None:
    projects = core.load_json(config.PROJECTS_PATH)
    entries = projects.get("projects", [])
    assert entries, "registry must declare at least one project"
    for entry in entries:
        assert registry.project_repo(entry).count("/") == 1
        assert registry.project_worktree(entry).is_absolute()


# --------------------------------------------------------------------------- #
# Configuration — regression guard for the ${HOME} literal-path bug
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "resolver",
    [config.workspace_root, config.agents_root, config.state_root, config.receipt_root],
)
def test_config_paths_are_absolute_and_expanded(resolver) -> None:
    path = resolver()
    assert path.is_absolute()
    assert "$" not in str(path), f"{resolver.__name__} contains an unexpanded shell variable"


def test_state_root_honours_environment_override(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_WATCHDOG_STATE_ROOT", str(tmp_path))
    assert config.state_root() == tmp_path.resolve()


# --------------------------------------------------------------------------- #
# GitHub wrappers — repo must never be implicit
# --------------------------------------------------------------------------- #


def test_github_helpers_address_the_repo_they_are_given() -> None:
    captured: list[list[str]] = []

    def fake_run(command, **_kwargs):
        captured.append(command)
        return {"exit_code": 0, "stdout": "", "stderr": ""}

    with mock.patch.object(github, "run_cmd", side_effect=fake_run):
        github.issue_comment("owner/other", 7, "body")
        github.issue_edit("owner/other", 7, add=["x"], remove=["y"])
        github.issue_close("owner/other", 7)

    for command in captured:
        assert "owner/other" in command
        assert TAU_REPO not in command


# --------------------------------------------------------------------------- #
# Locking
# --------------------------------------------------------------------------- #


def test_second_tick_cannot_take_a_held_lock(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_WATCHDOG_STATE_ROOT", str(tmp_path))
    assert core.acquire_lock("run-a") is True
    assert core.acquire_lock("run-b") is False
    core.release_lock()
    assert core.acquire_lock("run-c") is True
    core.release_lock()


def test_stale_lock_is_reclaimed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_WATCHDOG_STATE_ROOT", str(tmp_path))
    assert core.acquire_lock("crashed-run") is True
    owner = config.lock_dir() / "owner.json"
    payload = json.loads(owner.read_text(encoding="utf-8"))
    payload["epoch"] = time.time() - (config.LOCK_STALE_SECONDS + 60)
    payload["pid"] = 999_999_999
    owner.write_text(json.dumps(payload), encoding="utf-8")
    assert core.acquire_lock("recovery-run") is True
    core.release_lock()


def test_stale_lock_with_live_owner_is_not_reclaimed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_WATCHDOG_STATE_ROOT", str(tmp_path))
    assert core.acquire_lock("live-long-run") is True
    owner = config.lock_dir() / "owner.json"
    payload = json.loads(owner.read_text(encoding="utf-8"))
    payload["epoch"] = time.time() - (config.LOCK_STALE_SECONDS + 60)
    owner.write_text(json.dumps(payload), encoding="utf-8")

    assert core.acquire_lock("overlapping-run") is False
    readback = json.loads(owner.read_text(encoding="utf-8"))
    assert readback["run_id"] == "live-long-run"
    assert readback["pid"] == os.getpid()
    core.release_lock()


def test_fresh_lock_is_not_reclaimed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_WATCHDOG_STATE_ROOT", str(tmp_path))
    assert core.acquire_lock("live-run") is True
    assert core.acquire_lock("impatient-run") is False
    core.release_lock()


# --------------------------------------------------------------------------- #
# Receipt persistence policy
# --------------------------------------------------------------------------- #


def test_uneventful_receipts_are_not_persisted(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("PROJECT_WATCHDOG_STATE_ROOT", str(tmp_path))
    receipt_dir = config.receipt_root() / "run-noop"
    receipt_dir.mkdir(parents=True)
    receipt = core.base_receipt("run-noop", receipt_dir, False)
    receipt["status"] = "NOOP"
    core.finish("run-noop", receipt_dir, receipt, 0)
    capsys.readouterr()
    assert not receipt_dir.exists(), "NOOP ticks must not leave a receipt directory behind"


@pytest.mark.parametrize("status", ["COMPLETED", "NEEDS_ATTENTION"])
def test_eventful_receipts_are_persisted(tmp_path, monkeypatch, capsys, status: str) -> None:
    monkeypatch.setenv("PROJECT_WATCHDOG_STATE_ROOT", str(tmp_path))
    receipt_dir = config.receipt_root() / f"run-{status}"
    receipt_dir.mkdir(parents=True)
    receipt = core.base_receipt(f"run-{status}", receipt_dir, True)
    receipt["status"] = status
    core.finish(f"run-{status}", receipt_dir, receipt, 0)
    capsys.readouterr()
    written = receipt_dir / "receipt.json"
    assert written.is_file()
    assert json.loads(written.read_text(encoding="utf-8"))["status"] == status


# --------------------------------------------------------------------------- #
# Idle-streak escalation — silence must not read as success
# --------------------------------------------------------------------------- #


def test_first_idle_tick_does_not_escalate(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_WATCHDOG_STATE_ROOT", str(tmp_path))
    status = streaks.record_idle("tau")
    assert status.consecutive_ticks == 1
    assert status.escalated is False
    assert status.should_persist_receipt is False


def test_idle_ticks_accumulate(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_WATCHDOG_STATE_ROOT", str(tmp_path))
    for expected in (1, 2, 3):
        assert streaks.record_idle("tau").consecutive_ticks == expected


def test_idle_streak_escalates_past_threshold(tmp_path, monkeypatch) -> None:
    """The 41,607-tick incident: a month of idle must not report as healthy."""
    monkeypatch.setenv("PROJECT_WATCHDOG_STATE_ROOT", str(tmp_path))
    streaks.record_idle("tau")
    _backdate_first_idle("tau", seconds=config.NOOP_ESCALATION_SECONDS + 60)

    status = streaks.record_idle("tau")

    assert status.escalated is True
    assert status.should_persist_receipt is True
    assert status.diagnosis, "an escalation must carry an actionable diagnosis"
    assert any("agent-work" in line for line in status.diagnosis)


def test_escalation_does_not_persist_a_receipt_every_tick(tmp_path, monkeypatch) -> None:
    """Escalating must not reintroduce one receipt directory per minute."""
    monkeypatch.setenv("PROJECT_WATCHDOG_STATE_ROOT", str(tmp_path))
    streaks.record_idle("tau")
    _backdate_first_idle("tau", seconds=config.NOOP_ESCALATION_SECONDS + 60)

    first = streaks.record_idle("tau")
    followups = [streaks.record_idle("tau") for _ in range(5)]

    assert first.should_persist_receipt is True
    assert all(item.escalated for item in followups)
    assert not any(item.should_persist_receipt for item in followups)


def test_finding_work_clears_the_streak(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_WATCHDOG_STATE_ROOT", str(tmp_path))
    streaks.record_idle("tau")
    streaks.record_idle("tau")
    streaks.clear_idle("tau")
    assert streaks.peek("tau") == {}
    assert streaks.record_idle("tau").consecutive_ticks == 1


def test_streaks_are_tracked_per_project(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_WATCHDOG_STATE_ROOT", str(tmp_path))
    streaks.record_idle("tau")
    streaks.record_idle("tau")
    streaks.record_idle("scillm")
    streaks.clear_idle("scillm")
    assert streaks.peek("tau")["consecutive_idle_ticks"] == 2
    assert streaks.peek("scillm") == {}


def test_corrupt_streak_file_is_survivable(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_WATCHDOG_STATE_ROOT", str(tmp_path))
    streaks.record_idle("tau")
    (tmp_path / "streaks.json").write_text("{ not json", encoding="utf-8")
    assert streaks.record_idle("tau").consecutive_ticks == 1


def test_escalation_threshold_is_configurable(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_WATCHDOG_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("PROJECT_WATCHDOG_IDLE_ESCALATION_SECONDS", "5")
    importlib.reload(config)
    importlib.reload(streaks)
    try:
        streaks.record_idle("tau")
        _backdate_first_idle("tau", seconds=10)
        assert streaks.record_idle("tau").escalated is True
    finally:
        monkeypatch.delenv("PROJECT_WATCHDOG_IDLE_ESCALATION_SECONDS")
        importlib.reload(config)
        importlib.reload(streaks)


def _backdate_first_idle(project_id: str, *, seconds: float) -> None:
    """Rewind a project's idle start so threshold crossing is testable."""
    path = config.state_root() / "streaks.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    moment = datetime.now(UTC) - timedelta(seconds=seconds)
    payload["projects"][project_id]["first_idle_at"] = moment.isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    path.write_text(json.dumps(payload), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Generic ticket_repair handler
# --------------------------------------------------------------------------- #


def test_ticket_repair_serves_a_project_that_is_not_tau(tmp_path) -> None:
    """runner_kind no longer gates the repair lane.

    It required `tau-command-loop`, and the spec paths it then demanded exist
    only in the tau checkout, so every other registered project was refused
    before it could dispatch anything. $ask compiles the DAG for any repo.
    """
    project = {
        "project_id": "agent-skills",
        "repo": "grahama1970/agent-skills",
        "worktree": str(_clean_worktree(tmp_path)),
        "runner_kind": "project-local",
    }
    issue = _issue(7, labels=["agent-work"])
    issue["watchdog_action"] = "ticket_repair"
    with mock.patch.object(handlers.github, "issue_comment") as comment:
        result = handlers.handle_issue("run", tmp_path, project, issue, apply=False)
    assert result["status"] == "DRY_RUN", result.get("summary")
    assert not comment.called


def _clean_worktree(tmp_path: Path) -> Path:
    """A real git worktree on a clean ``main``.

    Dispatch fails closed on a worktree that is on a feature branch or whose
    target paths are dirty (#1045), so a fixture that is not a real, clean git
    worktree does not represent a dispatchable project.
    """
    (tmp_path / "skills" / "x").mkdir(parents=True, exist_ok=True)
    (tmp_path / "skills" / "x" / "SKILL.md").write_text("x\n", encoding="utf-8")
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    }
    for args in (("init", "-q", "-b", "main", "."), ("add", "-A"), ("commit", "-q", "-m", "init")):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True,
                       capture_output=True, env=env)
    return tmp_path


def test_ticket_repair_dry_run_makes_no_github_call(tmp_path) -> None:
    project = {
        "project_id": "tau",
        "repo": TAU_REPO,
        "worktree": str(_clean_worktree(tmp_path)),
        "runner_kind": "tau-command-loop",
    }
    issue = _issue(8, labels=["agent-work"])
    issue["watchdog_action"] = "ticket_repair"
    with mock.patch.object(handlers.github, "issue_comment") as comment:
        result = handlers.handle_issue("run", tmp_path, project, issue, apply=False)
    assert result["status"] == "DRY_RUN"
    assert not comment.called


def test_ticket_repair_dispatches_through_ask_tau_dag(tmp_path) -> None:
    project = {
        "project_id": "tau",
        "repo": TAU_REPO,
        "worktree": str(_clean_worktree(tmp_path)),
        "runner_kind": "tau-command-loop",
        "repair_creator": "gpt-5.5-high",
        "repair_reviewer": "claude-fable-low",
        "ticket_repair_timeout_s": 10800,
    }
    issue = _issue(9, labels=["agent-work"])
    issue["watchdog_action"] = "ticket_repair"
    with (
        mock.patch.object(handlers.github, "issue_comment", return_value={"exit_code": 0}),
        mock.patch.object(handlers.github, "issue_edit", return_value={"exit_code": 0}),
        mock.patch.object(
            handlers, "run_ask_tau_dag_with_stream_monitor", side_effect=_passing_ask_tau_dag
        ) as bounded,
        mock.patch.object(handlers, "run_cmd", return_value={"exit_code": 0, "stderr": ""}),
        mock.patch.object(
            handlers.registry,
            "prepare_repair_worktree",
            return_value={"ok": True, "branch": "watchdog/issue-9",
                          "worktree": str(tmp_path / "repair-worktrees" / "tau-9")},
        ),
    ):
        result = handlers.handle_issue("run", tmp_path, project, issue, apply=True)
    # A stubbed $ask writes no seat responses, no proof artifact and no commit,
    # so the proof gate refuses closure. That is the point of the gate: exit 0
    # from the DAG is a dispatch receipt, not a repaired ticket (#1504).
    assert result["status"] == "NEEDS_ATTENTION", result.get("summary")
    # The proof gate runs git after the dispatch, so the $ask call is no longer
    # the last bounded command.
    asks = [c.args[0] for c in bounded.call_args_list
            if str(c.args[0][0]).endswith("ask/run.sh")]
    assert len(asks) == 1, "repair must go through $ask, exactly once"
    argv = asks[0]
    # Authored in a worktree of the lane's own making, never the registered
    # checkout: that one is a human's working tree.
    workspace = argv[argv.index("--handler-workspace") + 1]
    assert workspace.startswith("gpt-5.5-high=")
    assert str(tmp_path) != workspace.split("=", 1)[1]
    assert "repair-worktrees" in workspace
    assert argv[1] == "tau-dag"
    assert "--dag-template" in argv and argv[argv.index("--dag-template") + 1] == "creator-reviewer"
    assert "--topology" in argv and argv[argv.index("--topology") + 1] == "sequential"
    assert "--execute" in argv and "--allow-provider-calls" in argv
    assert "--scillm-api-key" not in argv
    assert "--scillm-base-url" not in argv
    assert not any("localhost:4001" in str(item) or "/v1/scillm/" in str(item) for item in argv)
    assert argv[argv.index("--execution-timeout-seconds") + 1] == "3600"
    # The creator seat mutates and needs a workspace; the reviewer seat does not.
    assert "claude-fable-low" in argv
    # $ask fails preflight without an immutable goal, before any handler runs.
    goal = argv[argv.index("--immutable-goal") + 1]
    assert "#9" in goal and "Do not weaken or delete a test" in goal

    task = (tmp_path / "repair-task.md").read_text(encoding="utf-8")
    assert "VERDICT: PASS" in task, "the reviewer seat must be asked for a verdict"


def test_ticket_repair_documents_tau_owned_scillm_boundary() -> None:
    skill = Path(__file__).resolve().parents[1] / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    compact = " ".join(text.split())

    assert "project-watchdog never calls SciLLM directly" in text
    assert "project-watchdog -> $ask tau-dag -> Tau-executed DAG/command_spec -> Tau-owned SciLLM adapter" in text
    assert "SCILLM_AUTH_INVALID_API_KEY" in text
    assert "must not reimplement SciLLM auth probing" in text
    assert "Browser/web" in compact
    assert "cannot run local code" in compact
    assert "must not be configured as `repair_creator` or `repair_reviewer`" in compact
    assert "creating focused `$ticket` items" in compact


def test_ticket_repair_allows_gpt55_high_creator_through_tau_workspace(tmp_path) -> None:
    project = {
        "project_id": "pdf_oxide",
        "repo": "grahama1970/pdf_oxide",
        "worktree": str(_clean_worktree(tmp_path)),
        "repair_creator": "gpt-5.5-high",
        "repair_reviewer": "claude-fable-low",
    }
    issue = _issue(32, labels=["agent-work"])
    issue["watchdog_action"] = "ticket_repair"
    with (
        mock.patch.object(handlers.github, "issue_comment", return_value={"exit_code": 0}),
        mock.patch.object(handlers.github, "issue_edit", return_value={"exit_code": 0}),
        mock.patch.object(
            handlers, "run_ask_tau_dag_with_stream_monitor", side_effect=_passing_ask_tau_dag
        ) as dispatched,
        mock.patch.object(handlers, "run_cmd", return_value={"exit_code": 0, "stderr": ""}),
        mock.patch.object(
            handlers.registry,
            "prepare_repair_worktree",
            return_value={"ok": True, "branch": "watchdog/issue-32",
                          "worktree": str(tmp_path / "repair-worktrees" / "pdf-oxide-32")},
        ),
    ):
        result = handlers.handle_issue("run", tmp_path, project, issue, apply=True)
    assert result["status"] == "NEEDS_ATTENTION", result.get("summary")
    asks = [c.args[0] for c in dispatched.call_args_list
            if str(c.args[0][0]).endswith("ask/run.sh")]
    assert len(asks) == 1
    argv = asks[0]
    workspace = argv[argv.index("--handler-workspace") + 1]
    assert workspace.startswith("gpt-5.5-high=")
    assert "repair-worktrees" in workspace
    assert argv[1] == "tau-dag"
    assert "--scillm-api-key" not in argv
    assert "--scillm-base-url" not in argv


# --------------------------------------------------------------------------- #
# Repair proof gate — agent-skills#1504
# --------------------------------------------------------------------------- #


def test_a_seat_that_refused_is_read_as_a_refusal() -> None:
    """agent-skills#1499's creator seat: node receipt PASS, response NEEDS_ATTENTION."""
    assert handlers.declared_verdict(
        "## Position\n\nNEEDS_ATTENTION - no shell, filesystem, or git access.\n"
    ) == "NEEDS_ATTENTION"
    assert handlers.declared_verdict("Some notes.\n\n**VERDICT: PASS**\n") == "PASS"
    assert handlers.declared_verdict("VERDICT: FAIL\n") == "FAIL"


def test_prose_about_a_failing_proof_is_not_read_as_a_verdict() -> None:
    """The #1499 reviewer described a failed proof and a running retry in prose.

    The watchdog does not classify prose into a verdict. No declared verdict is
    no verdict, which the gate then treats as unproven.
    """
    assert handlers.declared_verdict(
        "Ran the required live proof once. It failed fail-closed: `status: FAIL`, "
        "`stop_condition: g1_delta_validation_failed`. The second attempt is running.\n"
    ) is None


def test_only_the_proof_section_names_required_artifacts() -> None:
    body = (
        "## Target\n\nskills/project-watchdog\n\n"
        "## Required proof\n\nRun: skills/agentic-evals/run.sh run f.json "
        "--output /tmp/proof-gate.json --timeout-seconds 600\n\n"
        "## Ticket type details\n\n- **Reproduction:** /tmp/unrelated.json\n"
    )
    assert handlers.required_proof_artifacts(body) == ["/tmp/proof-gate.json"]
    assert handlers.required_proof_artifacts("## Target\n\nskills/x\n") == []


def test_a_proof_artifact_from_a_previous_run_does_not_count(tmp_path) -> None:
    """#1499 had a July receipt on disk; accepting it would close on a stale pass."""
    artifact = tmp_path / "proof.json"
    artifact.write_text(json.dumps({"readiness": "READY"}), encoding="utf-8")
    stale = artifact.stat().st_mtime
    fresh = handlers.inspect_proof_artifact(str(artifact), not_before=stale - 10)
    assert fresh["passed"] is True
    old = handlers.inspect_proof_artifact(str(artifact), not_before=stale + 10)
    assert old["passed"] is False and old["reason"] == "predates this dispatch"


def test_a_proof_artifact_that_reports_a_failure_does_not_count(tmp_path) -> None:
    artifact = tmp_path / "proof.json"
    artifact.write_text(
        json.dumps({"readiness": "READY", "cases": [{"name": "c", "status": "FAIL"}]}),
        encoding="utf-8",
    )
    record = handlers.inspect_proof_artifact(str(artifact), not_before=0)
    assert record["passed"] is False and "FAIL" in record["reason"]


def test_a_dag_that_passed_but_proved_nothing_does_not_close_the_issue(tmp_path) -> None:
    """agent-skills#1499 verbatim: DAG exit 0, seats PASS, nothing proven.

    The creator said it had no tools, the reviewer said the proof failed and a
    retry was still running, and no commit existed -- and the watchdog closed
    the issue as completed.
    """
    project = {
        "project_id": "p", "repo": TAU_REPO, "worktree": str(_clean_worktree(tmp_path)),
        "repair_creator": "gpt-5.5-high", "repair_reviewer": "claude-fable-low",
        "auto_land_main": True,
    }
    issue = _issue(1499, labels=["agent-work"], body=(
        "type: bug\ntarget: skills/x\n\n"
        "## Required proof\n\nRun: skills/x/run.sh proof "
        f"--output {tmp_path / 'never-written.json'}\n"
    ))
    issue["watchdog_action"] = "ticket_repair"
    ask_dir = tmp_path / "ask" / "run-1" / "node-artifacts"
    for handler, text in (
        ("gpt-5.5-high", "## Position\n\nNEEDS_ATTENTION - no tools in this session.\n"),
        ("claude-fable-low", "The proof failed; the second attempt is still running.\n"),
    ):
        node = ask_dir / handlers.repair_node_id(handler)
        node.mkdir(parents=True)
        (node / "response.md").write_text(text, encoding="utf-8")
    edits: list[dict] = []
    with (
        mock.patch.object(handlers.github, "issue_comment", return_value={"exit_code": 0}),
        mock.patch.object(
            handlers.github, "issue_edit",
            side_effect=lambda *a, **k: edits.append(k) or {"exit_code": 0},
        ),
        mock.patch.object(handlers.github, "issue_close") as close,
        mock.patch.object(
            handlers.registry, "prepare_repair_worktree",
            return_value={"ok": True, "branch": "watchdog/issue-1499",
                          "worktree": str(tmp_path / "wt")},
        ),
        mock.patch.object(handlers.registry, "remote_main_sha", side_effect=["a", "a"]),
        mock.patch.object(handlers, "run_ask_tau_dag_with_stream_monitor", side_effect=_passing_ask_tau_dag),
        mock.patch.object(handlers, "run_cmd", return_value={"exit_code": 0, "stderr": ""}),
    ):
        result = handlers.handle_issue("run", tmp_path, project, issue, apply=True)

    assert result["status"] == "NEEDS_ATTENTION" and result["ok"] is False
    assert not close.called, "an unproven repair must not close its ticket"
    assert not any(e.get("add") == [config.DONE_LABEL] for e in edits), "must not mark it done"
    assert any(e.get("add") == [config.BLOCKED_LABEL] for e in edits)
    reasons = " | ".join(result["proof_gate"]["reasons"])
    assert "declared NEEDS_ATTENTION" in reasons
    assert "declared no VERDICT" in reasons
    assert "no required proof artifact" in reasons


def test_failed_ticket_repair_blocks_the_issue(tmp_path) -> None:
    """A failed repair must stop cron retrying it every minute."""
    project = {
        "project_id": "tau",
        "repo": TAU_REPO,
        "worktree": str(_clean_worktree(tmp_path)),
        "runner_kind": "tau-command-loop",
    }
    issue = _issue(10, labels=["agent-work"])
    issue["watchdog_action"] = "ticket_repair"
    edits: list[dict] = []
    with (
        mock.patch.object(handlers.github, "issue_comment", return_value={"exit_code": 0}),
        mock.patch.object(
            handlers.github,
            "issue_edit",
            side_effect=lambda *a, **k: edits.append(k) or {"exit_code": 0},
        ),
        mock.patch.object(
            handlers, "run_ask_tau_dag_with_stream_monitor", side_effect=_failed_ask_tau_dag
        ),
        mock.patch.object(
            handlers.registry,
            "prepare_repair_worktree",
            return_value={"ok": True, "branch": "watchdog/issue-10",
                          "worktree": str(tmp_path / "repair-worktrees" / "tau-10")},
        ),
    ):
        result = handlers.handle_issue("run", tmp_path, project, issue, apply=True)
    assert result["status"] == "NEEDS_ATTENTION"
    assert any(e.get("add") == [config.BLOCKED_LABEL] for e in edits)


def test_the_repair_task_names_the_bar_the_reviewer_applies() -> None:
    """A transport-only stub must not be able to report a repair it never did."""
    goal = handlers.repair_immutable_goal(TAU_REPO, 7)
    assert "#7" in goal
    assert "proven by the proof command the ticket names" in goal
    assert "Do not weaken or delete a test" in goal

    task = handlers.build_repair_task(
        repo=TAU_REPO, issue_number=7, issue_title="t",
        issue_body="type: bug\ntarget: skills/x\n", targets=["skills/x"],
    )
    assert "VERDICT: PASS" in task and "VERDICT: FAIL" in task
    assert "Allowed paths: skills/x" in task
    assert "type: bug" in task, "the ticket body carries the orientation a cron agent needs"


def test_goal_hash_is_stable_across_reruns() -> None:
    """Tau requires one goal_hash across every node, receipt, and rerun."""
    a = handlers.issue_goal_hash(TAU_REPO, 149)
    b = handlers.issue_goal_hash(TAU_REPO, 149)
    assert a == b and a.startswith("sha256:")
    assert a != handlers.issue_goal_hash(TAU_REPO, 150)


def _seed_passing_repair_evidence(receipt_dir: Path) -> None:
    ask_dir = receipt_dir / "ask" / "run-1" / "node-artifacts"
    for handler in (config.DEFAULT_REPAIR_CREATOR, config.DEFAULT_REPAIR_REVIEWER):
        node = ask_dir / handlers.repair_node_id(handler)
        node.mkdir(parents=True, exist_ok=True)
        (node / "response.md").write_text("VERDICT: PASS\n", encoding="utf-8")


def _passing_repair_run_cmd(command, **_kwargs):  # noqa: ANN001, ANN003
    if command[:3] == ["git", "rev-list", "--count"]:
        return {"exit_code": 0, "stdout": "1\n", "stderr": ""}
    return {"exit_code": 0, "stdout": "", "stderr": ""}


def _passing_ask_tau_dag(command, **kwargs):  # noqa: ANN001, ANN003
    monitor_path = kwargs["monitor_path"]
    handlers.write_json(
        monitor_path,
        {
            "schema": "agent_skills.project_watchdog.tau_stream_monitor.v1",
            "stream_readable": True,
            "terminal": True,
            "terminal_status": "PASS",
            "current_node": "reviewer",
            "current_status": "PASS",
            "event_count": 1,
            "poll_count": 1,
        },
    )
    return {"command": command, "exit_code": 0, "stdout": "", "stderr": "",
            "stream_monitor": str(monitor_path)}


def _failed_ask_tau_dag(command, **kwargs):  # noqa: ANN001, ANN003
    monitor_path = kwargs["monitor_path"]
    handlers.write_json(
        monitor_path,
        {
            "schema": "agent_skills.project_watchdog.tau_stream_monitor.v1",
            "stream_readable": True,
            "terminal": True,
            "terminal_status": "NEEDS_ATTENTION",
            "current_node": "creator",
            "current_status": "NEEDS_ATTENTION",
            "event_count": 1,
            "poll_count": 1,
        },
    )
    return {"command": command, "exit_code": 1, "stdout": "", "stderr": "x",
            "stream_monitor": str(monitor_path)}


def test_tau_stream_monitor_reads_terminal_progress_and_events(tmp_path) -> None:
    run = tmp_path / "ask" / "run-1"
    run.mkdir(parents=True)
    (run / "events.jsonl").write_text(
        json.dumps({"event_id": 1, "node_id": "creator", "status": "RUNNING"}) + "\n"
        + json.dumps({"event_id": 2, "node_id": "reviewer", "status": "PASS"}) + "\n",
        encoding="utf-8",
    )
    (run / "dag-progress.json").write_text(
        json.dumps({"status": "PASS", "current_node": "reviewer"}),
        encoding="utf-8",
    )

    monitor = handlers.inspect_tau_stream(tmp_path / "ask")

    assert monitor["stream_readable"] is True
    assert monitor["event_count"] == 2
    assert monitor["terminal"] is True
    assert monitor["terminal_status"] == "PASS"
    assert monitor["current_node"] == "reviewer"


def test_ask_tau_dag_runner_polls_stream_until_process_exit(tmp_path) -> None:
    ask_dir = tmp_path / "ask"
    monitor_path = tmp_path / "tau-stream-monitor.json"
    script = (
        "import json, pathlib, time\n"
        f"run = pathlib.Path({str(ask_dir / 'run-1')!r})\n"
        "run.mkdir(parents=True)\n"
        "(run/'events.jsonl').write_text(json.dumps({'event_id':1,'status':'RUNNING'})+'\\n')\n"
        "time.sleep(0.2)\n"
        "(run/'dag-progress.json').write_text(json.dumps({'status':'PASS','current_node':'reviewer'}))\n"
    )

    result = handlers.run_ask_tau_dag_with_stream_monitor(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        timeout_s=5,
        ask_run_dir=ask_dir,
        monitor_path=monitor_path,
        poll_interval_s=0.05,
    )
    monitor = json.loads(monitor_path.read_text(encoding="utf-8"))

    assert result["exit_code"] == 0
    assert monitor["stream_readable"] is True
    assert monitor["terminal"] is True
    assert monitor["terminal_status"] == "PASS"
    assert monitor["poll_count"] >= 1


def test_a_dirty_registered_target_is_reported_but_does_not_block_isolated_authoring(tmp_path) -> None:
    """Repairs are authored in isolated worktrees, not the registered checkout.

    agent-skills has 111 dirty skills out of 364. Requiring the whole
    repository to be clean withheld the 253 that are not; requiring the target
    path to be clean still blocked normal monitor-opportunities operation where
    tracked files are always dirty. The dirty registered checkout is reported,
    while repair authoring proceeds from a fresh origin/main worktree.
    """
    worktree = _clean_worktree(tmp_path)
    (worktree / "skills" / "x" / "SKILL.md").write_text("locally edited\n", encoding="utf-8")
    project = {
        "project_id": "agent-skills",
        "repo": "grahama1970/agent-skills",
        "worktree": str(worktree),
        "runner_kind": "project-local",
    }
    issue = _issue(11, labels=["agent-work"], body="type: bug\ntarget: skills/x\n")
    issue["watchdog_action"] = "ticket_repair"
    result = handlers.handle_issue("run", tmp_path, project, issue, apply=False)
    assert result["status"] == "DRY_RUN", result.get("summary")
    assert "tracked_files_dirty" in " ".join(result["worktree_readiness"]["reasons"])
    assert result["registered_checkout_dirty_tracked"] == 1
    assert result["worktree_dispatch_blocking_reasons"] == []


def test_a_clean_target_dispatches_despite_an_unrelated_dirty_skill(tmp_path) -> None:
    worktree = _clean_worktree(tmp_path)
    (worktree / "skills" / "other").mkdir(parents=True, exist_ok=True)
    (worktree / "skills" / "other" / "SKILL.md").write_text("untracked mess\n", encoding="utf-8")
    project = {
        "project_id": "agent-skills",
        "repo": "grahama1970/agent-skills",
        "worktree": str(worktree),
        "runner_kind": "project-local",
    }
    issue = _issue(12, labels=["agent-work"], body="type: bug\ntarget: skills/x\n")
    issue["watchdog_action"] = "ticket_repair"
    result = handlers.handle_issue("run", tmp_path, project, issue, apply=False)
    assert result["status"] == "DRY_RUN", result.get("summary")
    assert result["targets"] == ["skills/x"]


# --------------------------------------------------------------------------- #
# Lease exclusion — agent-skills#1082
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("lease", sorted(config.LEASE_LABELS))
def test_any_agent_lease_blocks_routing(lease: str) -> None:
    """A ticket held by ANY agent is untouchable, not just this watchdog's own.

    maintainer-active is what `ticket lease` writes, so omitting it meant the
    watchdog dispatched a second agent onto a skill someone was already editing.
    """
    assert registry.classify_issue(_issue(1, labels=["agent-work", lease])) is None


def test_maintainer_active_is_in_the_lease_set() -> None:
    assert "maintainer-active" in config.LEASE_LABELS
    assert "agent-active" in config.LEASE_LABELS


def test_lease_and_human_hold_are_distinct_concepts() -> None:
    """A lease means taken; a human hold means a decision is owed. Not the same."""
    assert not (config.LEASE_LABELS & config.HUMAN_HOLD_LABELS)


# --------------------------------------------------------------------------- #
# A lease that did not take must stop the dispatch
# --------------------------------------------------------------------------- #


def test_a_failed_lease_stops_the_dispatch(tmp_path) -> None:
    """Neither agent-active nor agent-blocked existed in agent-skills.

    Every `gh issue edit --add-label` exited nonzero, the lease comment posted
    regardless, and the repair dispatched unleased -- so the in-flight guard read
    the ticket as free and nothing stopped the next tick starting a second one.
    """
    project = {
        "project_id": "agent-skills",
        "repo": "grahama1970/agent-skills",
        "worktree": str(_clean_worktree(tmp_path)),
        "runner_kind": "project-local",
    }
    issue = _issue(21, labels=["agent-work"], body="type: bug\ntarget: skills/x\n")
    issue["watchdog_action"] = "ticket_repair"
    with (
        mock.patch.object(handlers.github, "issue_comment", return_value={"exit_code": 0}),
        mock.patch.object(
            handlers.github,
            "issue_edit",
            return_value={"exit_code": 1, "stderr": "could not add label: 'agent-active' not found"},
        ),
        mock.patch.object(
            handlers.registry,
            "prepare_repair_worktree",
            return_value={"ok": True, "branch": "watchdog/issue-21",
                          "worktree": str(tmp_path / "wt")},
        ),
        mock.patch.object(handlers, "run_cmd") as dispatched,
        mock.patch.object(handlers, "run_ask_tau_dag_with_stream_monitor") as ask_dispatch,
    ):
        result = handlers.handle_issue("run", tmp_path, project, issue, apply=True)

    assert result["status"] == "BLOCKED"
    assert "ensure-labels" in result["summary"], "must name the command that fixes it"
    assert not dispatched.called, "must not dispatch a repair it could not lease"
    assert not ask_dispatch.called, "must not dispatch Ask/Tau without a lease"


def test_a_lease_that_takes_proceeds(tmp_path) -> None:
    _seed_passing_repair_evidence(tmp_path)
    project = {
        "project_id": "agent-skills",
        "repo": "grahama1970/agent-skills",
        "worktree": str(_clean_worktree(tmp_path)),
        "runner_kind": "project-local",
    }
    issue = _issue(22, labels=["agent-work"], body="type: bug\ntarget: skills/x\n")
    issue["watchdog_action"] = "ticket_repair"
    with (
        mock.patch.object(handlers.github, "issue_comment", return_value={"exit_code": 0}),
        mock.patch.object(handlers.github, "issue_edit", return_value={"exit_code": 0}),
        mock.patch.object(
            handlers.registry,
            "prepare_repair_worktree",
            return_value={"ok": True, "branch": "watchdog/issue-22",
                          "worktree": str(tmp_path / "wt")},
        ),
        mock.patch.object(handlers, "run_ask_tau_dag_with_stream_monitor", side_effect=_passing_ask_tau_dag),
        mock.patch.object(handlers, "run_cmd", side_effect=_passing_repair_run_cmd),
    ):
        result = handlers.handle_issue("run", tmp_path, project, issue, apply=True)
    assert result["status"] == "COMPLETED", result.get("summary")


# --------------------------------------------------------------------------- #
# Two seats, two model families (agent-skills#1086)
# --------------------------------------------------------------------------- #


def test_the_two_repair_seats_are_different_model_families() -> None:
    """gpt-5.5-xhigh resolves to `codex exec --model ...` -- the creator's own
    family. A reviewer sharing the creator's blind spots is a second pass, not a
    second opinion."""
    creator = config.repair_creator({})
    reviewer = config.repair_reviewer({})
    assert creator != reviewer
    assert "codex" not in reviewer and "gpt" not in reviewer


def test_a_project_may_name_its_own_seats() -> None:
    project = {"repair_creator": "gpt-5.5-high", "repair_reviewer": "claude-opus-4-8-high"}
    assert config.repair_creator(project) == "gpt-5.5-high"
    assert config.repair_reviewer(project) == "claude-opus-4-8-high"


def test_registered_repair_seats_can_author_and_review_code() -> None:
    registry_path = Path(__file__).resolve().parents[1] / "registry" / "projects.json"
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    projects = payload["projects"] if isinstance(payload, dict) else payload

    invalid: list[str] = []
    for project in projects:
        if not project.get("repair_creator") and not project.get("repair_reviewer"):
            continue
        try:
            config.repair_seats(project)
        except config.SeatIndependenceError as exc:
            invalid.append(f"{project.get('project_id', '<unknown>')}: {exc}")

    assert invalid == []


def test_tau_repair_reviewer_is_local_claude_opus_48_high() -> None:
    registry_path = Path(__file__).resolve().parents[1] / "registry" / "projects.json"
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    projects = payload["projects"] if isinstance(payload, dict) else payload
    tau = next(project for project in projects if project["project_id"] == "tau")

    assert tau["repair_reviewer"] == "claude-opus-4-8-high"
    creator, reviewer = config.repair_seats(tau)
    assert creator == "gpt-5.5-high"
    assert reviewer == "claude-opus-4-8-high"


def test_memory_project_auto_lands_reviewer_passed_repairs() -> None:
    registry_path = Path(__file__).resolve().parents[1] / "registry" / "projects.json"
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    projects = payload["projects"] if isinstance(payload, dict) else payload
    memory = next(project for project in projects if project["project_id"] == "memory")

    assert config.auto_land_main(memory) is True
    assert memory["repair_reviewer"] == "claude-opus-4-8-high"


def test_identical_seats_are_refused_before_dispatch(tmp_path) -> None:
    project = {
        "project_id": "agent-skills",
        "repo": "grahama1970/agent-skills",
        "worktree": str(_clean_worktree(tmp_path)),
        "repair_creator": "codex",
        "repair_reviewer": "codex",
    }
    issue = _issue(31, labels=["agent-work"], body="type: bug\ntarget: skills/x\n")
    issue["watchdog_action"] = "ticket_repair"
    with mock.patch.object(handlers, "run_ask_tau_dag_with_stream_monitor") as dispatched:
        result = handlers.handle_issue("run", tmp_path, project, issue, apply=True)
    assert result["status"] == "BLOCKED"
    assert "Codex CLI" in result["summary"]
    assert not dispatched.called


def test_oc_chat_creator_is_refused_before_ask_dispatch(tmp_path) -> None:
    project = {
        "project_id": "sparta",
        "repo": "grahama1970/sparta",
        "worktree": str(_clean_worktree(tmp_path)),
        "repair_creator": "oc-deepseek",
        "repair_reviewer": "claude-opus-5-medium",
    }
    issue = _issue(85, labels=["agent-work"], body="type: bug\ntarget: src/x\n")
    issue["watchdog_action"] = "ticket_repair"
    with mock.patch.object(handlers, "run_ask_tau_dag_with_stream_monitor") as dispatched:
        result = handlers.handle_issue("run", tmp_path, project, issue, apply=True)
    assert result["status"] == "BLOCKED"
    assert "not a Tau repair authoring lane" in result["summary"]
    assert "oc-*" in result["summary"]
    assert not dispatched.called


def test_web_model_creator_is_refused_before_ask_dispatch(tmp_path) -> None:
    project = {
        "project_id": "memory",
        "repo": "grahama1970/graph-memory-operator",
        "worktree": str(_clean_worktree(tmp_path)),
        "repair_creator": "webgpt",
        "repair_reviewer": "claude-fable-low",
    }
    issue = _issue(146, labels=["agent-work"], body="type: bug\ntarget: src/x\n")
    issue["watchdog_action"] = "ticket_repair"
    with mock.patch.object(handlers, "run_ask_tau_dag_with_stream_monitor") as dispatched:
        result = handlers.handle_issue("run", tmp_path, project, issue, apply=True)
    assert result["status"] == "BLOCKED"
    assert "not a Tau repair authoring lane" in result["summary"]
    assert "webgpt" in result["summary"]
    assert not dispatched.called


def test_a_repair_that_moved_main_is_flagged_and_blocked(tmp_path) -> None:
    """The creator seat pushed a850e22a6 to origin/main while its own DAG node
    reported NEEDS_ATTENTION and the ticket stayed agent-blocked. Unreviewed work
    reached main anyway -- the exact thing two seats exist to prevent."""
    project = {
        "project_id": "agent-skills",
        "repo": "grahama1970/agent-skills",
        "worktree": str(_clean_worktree(tmp_path)),
    }
    issue = _issue(41, labels=["agent-work"], body="type: bug\ntarget: skills/x\n")
    issue["watchdog_action"] = "ticket_repair"
    edits: list[dict] = []
    with (
        mock.patch.object(handlers.github, "issue_comment", return_value={"exit_code": 0}),
        mock.patch.object(
            handlers.github, "issue_edit",
            side_effect=lambda *a, **k: edits.append(k) or {"exit_code": 0},
        ),
        mock.patch.object(
            handlers.registry, "prepare_repair_worktree",
            return_value={"ok": True, "branch": "watchdog/issue-41",
                          "worktree": str(tmp_path / "wt")},
        ),
        mock.patch.object(handlers.registry, "remote_main_sha", side_effect=["aaa111", "bbb222"]),
        mock.patch.object(handlers, "run_ask_tau_dag_with_stream_monitor", side_effect=_passing_ask_tau_dag),
        mock.patch.object(handlers, "run_cmd", return_value={"exit_code": 0, "stderr": ""}),
    ):
        result = handlers.handle_issue("run", tmp_path, project, issue, apply=True)

    assert result["status"] == "NEEDS_ATTENTION"
    assert "origin/main moved" in result["summary"]
    assert any(e.get("add") == [config.BLOCKED_LABEL] for e in edits)


def test_an_untouched_main_completes_normally(tmp_path) -> None:
    _seed_passing_repair_evidence(tmp_path)
    project = {
        "project_id": "agent-skills",
        "repo": "grahama1970/agent-skills",
        "worktree": str(_clean_worktree(tmp_path)),
    }
    issue = _issue(42, labels=["agent-work"], body="type: bug\ntarget: skills/x\n")
    issue["watchdog_action"] = "ticket_repair"
    with (
        mock.patch.object(handlers.github, "issue_comment", return_value={"exit_code": 0}),
        mock.patch.object(handlers.github, "issue_edit", return_value={"exit_code": 0}),
        mock.patch.object(
            handlers.registry, "prepare_repair_worktree",
            return_value={"ok": True, "branch": "watchdog/issue-42",
                          "worktree": str(tmp_path / "wt")},
        ),
        mock.patch.object(handlers.registry, "remote_main_sha", side_effect=["aaa111", "aaa111"]),
        mock.patch.object(handlers, "run_ask_tau_dag_with_stream_monitor", side_effect=_passing_ask_tau_dag),
        mock.patch.object(handlers, "run_cmd", side_effect=_passing_repair_run_cmd),
    ):
        result = handlers.handle_issue("run", tmp_path, project, issue, apply=True)
    assert result["status"] == "COMPLETED", result.get("summary")


def test_landed_repair_cleanup_invokes_ops_worktrees_archive(tmp_path, monkeypatch) -> None:
    project_worktree = tmp_path / "project"
    repair_worktree = tmp_path / "repair"
    project_worktree.mkdir()
    repair_worktree.mkdir()
    calls: list[dict] = []

    def fake_run(command, **kwargs):  # noqa: ANN001, ANN003
        calls.append({"command": command, **kwargs})
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"outcome": "archived", "archive_dir": "/mnt/storage12tb/worktrees/deprecated/x"}),
            stderr="",
        )

    monkeypatch.setattr(handlers.subprocess, "run", fake_run)

    result = handlers._cleanup_landed_repair_worktree(project_worktree, repair_worktree, "run", 42)

    assert result["exit_code"] == 0
    assert result["receipt"]["outcome"] == "archived"
    assert calls[0]["command"][-3:] == [str(repair_worktree), "--apply", "--json"]
    assert calls[0]["command"][0].endswith("skills/ops-worktrees/run.sh")
    assert calls[0]["env"]["OPS_WORKTREES_REPO"] == str(project_worktree)


def test_auto_landed_repair_archives_worktree_before_closing(tmp_path) -> None:
    _seed_passing_repair_evidence(tmp_path)
    project = {
        "project_id": "p", "repo": TAU_REPO, "worktree": str(_clean_worktree(tmp_path)),
        "auto_land_main": True,
    }
    issue = _issue(52, labels=["agent-work"], body="type: bug\ntarget: skills/x\n")
    issue["watchdog_action"] = "ticket_repair"
    comments: list[str] = []
    cleanup = {
        "cmd": ["skills/ops-worktrees/run.sh", "archive", str(tmp_path / "wt"), "--apply", "--json"],
        "exit_code": 0,
        "stdout": json.dumps({"outcome": "archived"}),
        "stderr": "",
        "receipt": {"outcome": "archived", "archive_dir": "/mnt/storage12tb/worktrees/deprecated/p-52"},
    }
    with (
        mock.patch.object(
            handlers.github,
            "issue_comment",
            side_effect=lambda *_a: comments.append(str(_a[-1])) or {"exit_code": 0},
        ),
        mock.patch.object(handlers.github, "issue_edit", return_value={"exit_code": 0}),
        mock.patch.object(handlers.github, "issue_close", return_value={"exit_code": 0}) as close,
        mock.patch.object(
            handlers.registry, "prepare_repair_worktree",
            return_value={"ok": True, "branch": "watchdog/issue-52",
                          "worktree": str(tmp_path / "wt")},
        ),
        mock.patch.object(handlers.registry, "remote_main_sha", side_effect=["a", "a"]),
        mock.patch.object(handlers, "run_ask_tau_dag_with_stream_monitor", side_effect=_passing_ask_tau_dag),
        mock.patch.object(handlers, "run_cmd", side_effect=_passing_repair_run_cmd),
        mock.patch.object(handlers, "_land_repair_to_main", return_value=(True, [])),
        mock.patch.object(handlers, "_cleanup_landed_repair_worktree", return_value=cleanup) as cleanup_call,
    ):
        result = handlers.handle_issue("run", tmp_path, project, issue, apply=True)

    assert result["status"] == "LANDED"
    assert result["repair_worktree_cleanup"]["receipt"]["outcome"] == "archived"
    assert cleanup_call.called
    assert close.called
    assert any("Repair worktree archived" in comment for comment in comments)


def test_auto_landed_repair_cleanup_failure_keeps_ticket_open(tmp_path) -> None:
    _seed_passing_repair_evidence(tmp_path)
    project = {
        "project_id": "p", "repo": TAU_REPO, "worktree": str(_clean_worktree(tmp_path)),
        "auto_land_main": True,
    }
    issue = _issue(53, labels=["agent-work"], body="type: bug\ntarget: skills/x\n")
    issue["watchdog_action"] = "ticket_repair"
    cleanup = {
        "cmd": ["skills/ops-worktrees/run.sh", "archive", str(tmp_path / "wt"), "--apply", "--json"],
        "exit_code": 1,
        "stdout": json.dumps({"outcome": "archived_not_unregistered"}),
        "stderr": "could not unregister worktree",
        "receipt": {"outcome": "archived_not_unregistered"},
    }
    edits: list[dict] = []
    with (
        mock.patch.object(handlers.github, "issue_comment", return_value={"exit_code": 0}),
        mock.patch.object(
            handlers.github, "issue_edit",
            side_effect=lambda *a, **k: edits.append(k) or {"exit_code": 0},
        ),
        mock.patch.object(handlers.github, "issue_close") as close,
        mock.patch.object(
            handlers.registry, "prepare_repair_worktree",
            return_value={"ok": True, "branch": "watchdog/issue-53",
                          "worktree": str(tmp_path / "wt")},
        ),
        mock.patch.object(handlers.registry, "remote_main_sha", side_effect=["a", "a"]),
        mock.patch.object(handlers, "run_ask_tau_dag_with_stream_monitor", side_effect=_passing_ask_tau_dag),
        mock.patch.object(handlers, "run_cmd", side_effect=_passing_repair_run_cmd),
        mock.patch.object(handlers, "_land_repair_to_main", return_value=(True, [])),
        mock.patch.object(handlers, "_cleanup_landed_repair_worktree", return_value=cleanup),
    ):
        result = handlers.handle_issue("run", tmp_path, project, issue, apply=True)

    assert result["status"] == "NEEDS_ATTENTION"
    assert result["ok"] is False
    assert not close.called
    assert "could not archive/remove the repair worktree" in result["summary"]
    assert any(e.get("add") == [config.BLOCKED_LABEL] for e in edits)


def test_the_creator_is_told_not_to_push() -> None:
    goal = handlers.repair_immutable_goal("o/r", 7)
    assert "do not push" in goal and "do not merge" in goal
    task = handlers.build_repair_task(
        repo="o/r", issue_number=7, issue_title="t", issue_body="", targets=["skills/x"],
    )
    assert "Do not push" in task
    assert "reviewer's decision" in task


# --------------------------------------------------------------------------- #
# Closure audit — a closure is a claim, not evidence
# --------------------------------------------------------------------------- #


def _closed(number: int, *, labels: list[str], closed_at: str) -> dict:
    return {
        "number": number,
        "title": f"issue {number}",
        "body": "type: bug\ntarget: skills/x\n",
        "labels": [{"name": n} for n in labels],
        "closedAt": closed_at,
        "stateReason": "COMPLETED",
        "url": "u",
    }


def _audit_scan(issues: list[dict], now: float):
    gh = {"exit_code": 0, "stdout": json.dumps(issues), "stderr": ""}
    with mock.patch.object(registry, "run_cmd", return_value=gh):
        return registry.list_closed_for_audit(
            "run", {"repo": TAU_REPO, "project_id": "p"}, now=now
        )


def test_audit_skips_closures_already_verified_or_owned_by_a_human() -> None:
    import datetime as _dt

    now = _dt.datetime(2026, 7, 28, tzinfo=_dt.UTC)
    recent = (now - _dt.timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    pending = _audit_scan(
        [
            _closed(1, labels=["agent-work"], closed_at=recent),
            _closed(2, labels=["agent-work", config.CLOSURE_VERIFIED_LABEL], closed_at=recent),
            _closed(3, labels=["agent-work", "needs-human"], closed_at=recent),
        ],
        now.timestamp(),
    )
    assert [i["number"] for i in pending] == [1]


def test_audit_ignores_closures_older_than_the_window() -> None:
    import datetime as _dt

    now = _dt.datetime(2026, 7, 28, tzinfo=_dt.UTC)
    old = (now - _dt.timedelta(days=30)).isoformat().replace("+00:00", "Z")
    recent = (now - _dt.timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    pending = _audit_scan(
        [
            _closed(4, labels=["agent-work"], closed_at=old),
            _closed(5, labels=["agent-work"], closed_at=recent),
        ],
        now.timestamp(),
    )
    assert [i["number"] for i in pending] == [5], "an old closure is history, not a reopen"


def _run_audit(tmp_path, response, *, exit_code: int = 0, comments=None):
    """`response` is either one string (both seats agree) or {node: text}."""
    project = {"project_id": "p", "repo": TAU_REPO, "worktree": str(tmp_path)}
    issue = _closed(9, labels=["agent-work"], closed_at="2026-07-28T00:00:00Z")
    calls: dict = {"edits": [], "reopened": [], "comments": []}
    with (
        mock.patch.object(handlers.github, "issue_comments", return_value=comments or []),
        mock.patch.object(
            handlers.github, "issue_comment",
            side_effect=lambda r, n, b: calls["comments"].append(b) or {"exit_code": 0},
        ),
        mock.patch.object(
            handlers.github, "issue_edit",
            side_effect=lambda *a, **k: calls["edits"].append(k) or {"exit_code": 0},
        ),
        mock.patch.object(
            handlers.github, "issue_reopen",
            side_effect=lambda r, n: calls["reopened"].append(n) or {"exit_code": 0},
        ),
        mock.patch.object(handlers, "run_cmd", return_value={"exit_code": exit_code, "stderr": ""}),
        mock.patch.object(
            handlers,
            "_read_ask_responses_by_node",
            return_value=(
                response
                if isinstance(response, dict)
                else {"handler-a": response, "handler-b": response}
            ),
        ),
    ):
        result = handlers.handle_closure_audit("run", tmp_path, project, issue, apply=True)
    return result, calls


def test_an_upheld_closure_is_labelled_and_left_closed(tmp_path) -> None:
    result, calls = _run_audit(tmp_path, "The proof command was run and shown.\nVERDICT: PASS")
    assert result["verdict"] == "PASS" and result["status"] == "COMPLETED"
    assert calls["reopened"] == [], "a passing audit must not reopen"
    assert any(e.get("add") == [config.CLOSURE_VERIFIED_LABEL] for e in calls["edits"])


def test_a_closure_that_fails_review_is_reopened(tmp_path) -> None:
    result, calls = _run_audit(
        tmp_path, "The named proof was never run; the comment only asserts it.\nVERDICT: FAIL"
    )
    assert result["verdict"] == "FAIL" and result["status"] == "COMPLETED"
    assert calls["reopened"] == [9]
    assert any(e.get("add") == [config.READY_LABEL] for e in calls["edits"]), "routable again"


def test_an_unreadable_audit_is_not_treated_as_a_pass(tmp_path) -> None:
    """A reviewer that produced no verdict leaves the closure unreviewed."""
    result, calls = _run_audit(tmp_path, "the model rambled and never answered")
    assert result["status"] == "NEEDS_ATTENTION" and result["verdict"] is None
    assert calls["reopened"] == []
    assert not any(e.get("add") == [config.CLOSURE_VERIFIED_LABEL] for e in calls["edits"])


def test_a_failed_reviewer_run_is_not_treated_as_a_pass(tmp_path) -> None:
    result, calls = _run_audit(tmp_path, "VERDICT: PASS", exit_code=1)
    assert result["status"] == "NEEDS_ATTENTION"
    assert not any(e.get("add") == [config.CLOSURE_VERIFIED_LABEL] for e in calls["edits"])


def test_nonzero_audit_with_needs_attention_verdict_is_made_durable(tmp_path) -> None:
    result, calls = _run_audit(
        tmp_path,
        {"handler-a": "VERDICT: NEEDS_ATTENTION", "handler-b": "VERDICT: NEEDS_ATTENTION"},
        exit_code=4,
    )
    assert result["verdict"] == "NEEDS_ATTENTION"
    assert result["status"] == "NEEDS_ATTENTION"
    assert result["failure_code"] == handlers.CLOSURE_AUDIT_NONZERO_NEEDS_ATTENTION_CODE
    assert result["triage"]["code"] == handlers.CLOSURE_AUDIT_NONZERO_NEEDS_ATTENTION_CODE
    assert calls["reopened"] == []
    assert any(e.get("add") == [config.CLOSURE_UNVERIFIED_LABEL] for e in calls["edits"])


def test_nonzero_needs_attention_audit_cools_down_if_selected_again(tmp_path) -> None:
    state: dict = {"projects": {"p": {"state": "active"}}, "closure_audit_attempts": {}}
    receipt: dict = {}
    issue = _closed(9, labels=["agent-work"], closed_at="2026-07-28T00:00:00Z")
    project = {"project_id": "p", "repo": TAU_REPO, "worktree": str(tmp_path)}
    calls: dict = {"run_cmd": 0, "persisted": []}

    def fake_run_cmd(*args, **kwargs):
        calls["run_cmd"] += 1
        return {"exit_code": 4, "stderr": "join gate had no usable receipt"}

    with (
        mock.patch.object(registry, "list_closed_for_audit", return_value=[issue]),
        mock.patch.object(handlers.github, "issue_comments", return_value=[]),
        mock.patch.object(handlers.github, "issue_comment", return_value={"exit_code": 0}),
        mock.patch.object(
            handlers.github,
            "issue_edit",
            return_value={"exit_code": 1, "stderr": "label missing"},
        ),
        mock.patch.object(handlers, "run_cmd", side_effect=fake_run_cmd),
        mock.patch.object(
            handlers,
            "_read_ask_responses_by_node",
            return_value={
                "handler-a": "VERDICT: NEEDS_ATTENTION",
                "handler-b": "VERDICT: NEEDS_ATTENTION",
            },
        ),
        mock.patch.object(
            commands,
            "_persist_tick_state",
            side_effect=lambda s: calls["persisted"].append(dict(s)),
        ),
    ):
        first = commands._audit_one_closure(
            "run", tmp_path, state, receipt, apply=True, candidates=[project]
        )
        second = commands._audit_one_closure(
            "run", tmp_path, state, receipt, apply=True, candidates=[project]
        )

    assert first is not None and first["verdict"] == "NEEDS_ATTENTION"
    assert first["failure_code"] == handlers.CLOSURE_AUDIT_NONZERO_NEEDS_ATTENTION_CODE
    assert second is None, "the cooldown must suppress the duplicate audit on the next tick"
    assert calls["run_cmd"] == 1
    assert state["closure_audit_attempts"][f"{TAU_REPO}#9"] > 0


def test_repeated_audit_failures_stop_reopening_and_ask_for_a_person(tmp_path) -> None:
    """Without a bound, a reviewer that always fails reopens the same ticket forever."""
    prior = [
        {"body": f"{handlers.CLOSURE_AUDIT_MARKER} REOPENED", "author": {"login": "x"}}
        for _ in range(config.CLOSURE_AUDIT_MAX_REOPENS)
    ]
    result, calls = _run_audit(tmp_path, "VERDICT: FAIL", comments=prior)
    assert calls["reopened"] == [], "must stop reopening once the budget is spent"
    assert any(e.get("add") == ["needs-human"] for e in calls["edits"])
    assert result["status"] == "NEEDS_ATTENTION"


def test_the_reviewer_excerpt_is_clean_text_not_the_provider_envelope(tmp_path) -> None:
    """`response.raw.md` is the whole chat-completion envelope.

    Globbing `response*.md` matched it alongside `response.md`, so the excerpt
    posted to GitHub was raw JSON with the reasoning buried inside it.
    """
    node = tmp_path / "run" / "node-artifacts" / "handler-x"
    node.mkdir(parents=True)
    (node / "response.md").write_text("## Position\n\nVERDICT: FAIL\n\nThe proof never ran.\n")
    (node / "response.raw.md").write_text(
        '{"choices":[{"message":{"content":"VERDICT: FAIL"}}],"_hidden_params":{"x":1}}'
    )

    text = handlers._read_ask_response(tmp_path)

    assert "_hidden_params" not in text
    assert "The proof never ran." in text
    assert handlers._extract_verdict(text) == "FAIL"


def test_a_lane_with_only_a_raw_response_still_yields_a_verdict(tmp_path) -> None:
    node = tmp_path / "run" / "node-artifacts" / "handler-y"
    node.mkdir(parents=True)
    (node / "response.raw.md").write_text('{"content":"VERDICT: PASS"}')
    assert handlers._extract_verdict(handlers._read_ask_response(tmp_path)) == "PASS"


# --- the audit panel: two seats, not one ------------------------------------


def test_a_split_panel_reopens(tmp_path) -> None:
    """One seat showing the named proof was never run is decisive.

    A closure is a claim that has to be established, not a default to fall back
    on when reviewers disagree.
    """
    result, calls = _run_audit(
        tmp_path,
        {"handler-a": "Looks fine to me.\nVERDICT: PASS",
         "handler-b": "The named proof was never run.\nVERDICT: FAIL"},
    )
    assert result["verdict"] == "FAIL"
    assert calls["reopened"] == [9]


def test_a_closure_is_upheld_only_when_every_seat_answers_pass(tmp_path) -> None:
    result, calls = _run_audit(
        tmp_path,
        {"handler-a": "VERDICT: PASS", "handler-b": "I could not tell from this."},
    )
    assert result["verdict"] is None, "a silent seat is not a passing seat"
    assert result["status"] == "NEEDS_ATTENTION"
    assert calls["reopened"] == []
    assert not any(e.get("add") == [config.CLOSURE_VERIFIED_LABEL] for e in calls["edits"])


def test_a_unanimous_pass_upholds_the_closure(tmp_path) -> None:
    result, calls = _run_audit(
        tmp_path, {"handler-a": "VERDICT: PASS", "handler-b": "VERDICT: PASS"}
    )
    assert result["verdict"] == "PASS" and result["status"] == "COMPLETED"
    assert any(e.get("add") == [config.CLOSURE_VERIFIED_LABEL] for e in calls["edits"])


def test_the_panel_records_every_seat_verdict(tmp_path) -> None:
    result, _ = _run_audit(
        tmp_path, {"handler-a": "VERDICT: PASS", "handler-b": "VERDICT: FAIL"}
    )
    assert result["seat_verdicts"] == {"handler-a": "PASS", "handler-b": "FAIL"}


def test_a_single_seat_panel_is_refused(tmp_path) -> None:
    """One model that over-accepts would uphold its own bad closures."""
    project = {
        "project_id": "p", "repo": TAU_REPO, "worktree": str(tmp_path),
        "closure_auditors": ["claude-opus-4-8"],
    }
    issue = _closed(9, labels=["agent-work"], closed_at="2026-07-28T00:00:00Z")
    with mock.patch.object(handlers, "run_cmd") as dispatched:
        result = handlers.handle_closure_audit("run", tmp_path, project, issue, apply=True)
    assert result["status"] == "BLOCKED"
    assert "two distinct seats" in result["summary"]
    assert not dispatched.called


def test_duplicate_seats_are_refused(tmp_path) -> None:
    project = {
        "project_id": "p", "repo": TAU_REPO, "worktree": str(tmp_path),
        "closure_auditors": ["claude-opus-4-8", "claude-opus-4-8"],
    }
    issue = _closed(9, labels=["agent-work"], closed_at="2026-07-28T00:00:00Z")
    with mock.patch.object(handlers, "run_cmd") as dispatched:
        result = handlers.handle_closure_audit("run", tmp_path, project, issue, apply=True)
    assert result["status"] == "BLOCKED"
    assert not dispatched.called


def test_the_two_default_seats_are_different_families() -> None:
    seats = config.closure_auditors()
    assert len(seats) == 2 and len(set(seats)) == 2
    assert not (all("gpt" in s for s in seats) or all("claude" in s for s in seats))


# --------------------------------------------------------------------------- #
# Completion attestation — an empty queue is not proof of a finished project
# --------------------------------------------------------------------------- #


def _run_attestation(tmp_path, response: str, *, exit_code: int = 0, project=None, recent=None):
    project = project or {"project_id": "p", "repo": TAU_REPO}
    recent = recent or [{"number": 1, "title": "did a thing", "stateReason": "COMPLETED"}]
    calls: dict = {"reopened": [], "edits": []}
    with (
        mock.patch.object(handlers, "run_cmd", return_value={"exit_code": exit_code, "stderr": ""}),
        mock.patch.object(handlers, "_read_ask_response", return_value=response),
        mock.patch.object(handlers.github, "issue_comment", return_value={"exit_code": 0}),
        mock.patch.object(
            handlers.github, "issue_edit",
            side_effect=lambda *a, **k: calls["edits"].append(k) or {"exit_code": 0},
        ),
        mock.patch.object(
            handlers.github, "issue_reopen",
            side_effect=lambda r, n: calls["reopened"].append(n) or {"exit_code": 0},
        ),
    ):
        result = handlers.handle_completion_attestation(
            "run", tmp_path, project, recent, apply=True
        )
    result["_calls"] = calls
    return result


def test_the_attestor_is_a_different_transport_from_the_working_models() -> None:
    """Every judgement before this came from API-routed models that did and
    reviewed the work; the attestation must not be self-certified."""
    attestor = config.completion_attestor()
    assert attestor not in config.closure_auditors()
    assert attestor != config.repair_creator() and attestor != config.repair_reviewer()


def test_an_attested_project_passes(tmp_path) -> None:
    result = _run_attestation(tmp_path, "Nothing obviously missing.\nVERDICT: PASS")
    assert result["verdict"] == "PASS" and result["ok"] is True
    assert result["status"] == "COMPLETED"


def test_a_refused_attestation_reopens_what_it_named(tmp_path) -> None:
    """The cycle repeats: rejected closures go back to the repair lane."""
    recent = [
        {"number": 12, "title": "a", "stateReason": "COMPLETED"},
        {"number": 13, "title": "b", "stateReason": "COMPLETED"},
    ]
    result = _run_attestation(
        tmp_path,
        "#12 was closed without the work being done.\nVERDICT: FAIL\nREOPEN: #12",
        recent=recent,
    )
    assert result["verdict"] == "FAIL" and result["ok"] is False
    assert result["reopened"] == [12]
    assert 13 not in result["reopened"], "only what it named"
    assert any(e.get("add") == [config.READY_LABEL] for e in result["_calls"]["edits"])


def test_an_inconclusive_attestation_reopens_nothing(tmp_path) -> None:
    """"Cannot tell" is not a finding that a ticket was wrongly closed."""
    result = _run_attestation(
        tmp_path, "I cannot judge these from titles.\nVERDICT: NEEDS_ATTENTION\nREOPEN: #1"
    )
    assert result["reopened"] == []


def test_the_attestor_cannot_reopen_a_ticket_it_was_not_shown() -> None:
    """A number outside the set is a guess, and reopening on a guess sends a
    repair agent at a ticket nobody reviewed."""
    picked = handlers.extract_reopen_list("VERDICT: FAIL\nREOPEN: #1, #999", allowed={1, 2})
    assert picked == [1]


def test_a_failed_attestor_run_does_not_attest(tmp_path) -> None:
    """A browser seat that could not run is not agreement that work is done."""
    result = _run_attestation(tmp_path, "VERDICT: PASS", exit_code=1)
    assert result["ok"] is False and result["status"] == "NEEDS_ATTENTION"


def test_the_attestation_task_names_the_empty_queue_trap(tmp_path) -> None:
    task = handlers.build_completion_attestation_task(
        repo=TAU_REPO, recent=[{"number": 7, "title": "t", "stateReason": "COMPLETED"}]
    )
    assert "empty queue is not evidence" in task
    assert "VERDICT: PASS" in task and "VERDICT: FAIL" in task
    assert "#7" in task


def test_a_project_may_name_its_own_attestor() -> None:
    assert config.completion_attestor({"completion_attestor": "webkimi"}) == "webkimi"


# --------------------------------------------------------------------------- #
# cron environment — a credential the cron cannot see is a credential it lacks
# --------------------------------------------------------------------------- #


def test_the_cron_line_sources_a_shell_init_file(tmp_path, monkeypatch) -> None:
    """Every audit seat under cron failed `scillm_auth_invalid_api_key` while
    the same handler answered from an interactive shell: cron's environment is
    nearly empty and never read the rc file exporting the key."""
    rc = tmp_path / ".zshrc"
    rc.write_text("export SCILLM_PROXY_KEY=x\n")
    monkeypatch.setenv("PROJECT_WATCHDOG_SHELL_INIT", str(rc))
    monkeypatch.setenv("PROJECT_WATCHDOG_LOGIN_SHELL", "/usr/bin/zsh")

    from watchdog import commands  # noqa: PLC0415

    captured: dict = {}

    def fake_finish(run_id, receipt_dir, receipt, code, **kwargs):
        captured["receipt"] = receipt
        return code

    monkeypatch.setattr(commands, "run_cmd", lambda *a, **k: {"exit_code": 0, "stdout": ""})
    monkeypatch.setattr(commands, "finish", fake_finish)
    commands.install_cron(apply=False, minute="*/5")

    line = captured["receipt"]["cron_line"]
    assert f"source {rc}" in line, "the rc file must be sourced before the tick"
    assert "/usr/bin/zsh -c" in line
    assert "--project all" in line


def test_a_missing_rc_file_is_not_sourced(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_WATCHDOG_SHELL_INIT", str(tmp_path / "nope"))
    assert config.shell_init_file() is None


# --------------------------------------------------------------------------- #
# Lock contention is not failure
# --------------------------------------------------------------------------- #


def test_a_tick_stepping_aside_for_a_live_tick_is_not_a_failure(tmp_path, monkeypatch) -> None:
    """An audit takes minutes. Treating contention as failure logged BLOCKED and
    exit 1 every minute of it, so a healthy long lane read as a broken one."""
    from watchdog import commands  # noqa: PLC0415

    captured: dict = {}
    monkeypatch.setattr(commands.config, "QUIET_HOURS", "")
    monkeypatch.setattr(commands, "acquire_lock", lambda run_id: False)
    monkeypatch.setattr(commands, "lock_holder_alive", lambda: True)
    monkeypatch.setattr(
        commands, "finish",
        lambda run_id, d, receipt, code, **k: captured.update(receipt=receipt, code=code) or code,
    )
    commands.tick(apply=True, project_id="tau", max_tickets=1)

    assert captured["code"] == 0
    assert captured["receipt"]["status"] == "SKIPPED"
    assert captured["receipt"]["ok"] is True
    assert captured["receipt"]["stop_reason"] == "tick_already_running"


def test_a_lock_held_by_nothing_is_still_a_fault(tmp_path, monkeypatch) -> None:
    from watchdog import commands  # noqa: PLC0415

    captured: dict = {}
    monkeypatch.setattr(commands.config, "QUIET_HOURS", "")
    monkeypatch.setattr(commands, "acquire_lock", lambda run_id: False)
    monkeypatch.setattr(commands, "lock_holder_alive", lambda: False)
    monkeypatch.setattr(
        commands, "finish",
        lambda run_id, d, receipt, code, **k: captured.update(receipt=receipt, code=code) or code,
    )
    commands.tick(apply=True, project_id="tau", max_tickets=1)

    assert captured["code"] == 1
    assert captured["receipt"]["status"] == "BLOCKED"


def test_a_dead_pid_does_not_count_as_a_live_holder(tmp_path, monkeypatch) -> None:
    from watchdog import config, core  # noqa: PLC0415

    lock = tmp_path / "lock"
    lock.mkdir()
    (lock / "owner.json").write_text(json.dumps({"pid": 2**31 - 1, "run_id": "x"}))
    monkeypatch.setattr(config, "lock_dir", lambda: lock)
    assert core.lock_holder_alive() is False

    (lock / "owner.json").write_text(json.dumps({"pid": os.getpid(), "run_id": "x"}))
    assert core.lock_holder_alive() is True


# --------------------------------------------------------------------------- #
# The audit reads the proof, not just the prose about it
# --------------------------------------------------------------------------- #


def _evidence_comment(artifact: str) -> dict:
    payload = {
        "schema": handlers.CLOSURE_EVIDENCE_SCHEMA,
        "unit": {"command": "uv run pytest -q", "exit_code": 0},
        "e2e": {"command": "./run.sh --allow-live", "exit_code": 0,
                "mocked": False, "live": True, "artifact": artifact},
    }
    return {"body": f"# Proof\n\n```json\n{json.dumps(payload)}\n```\n"}


def test_the_audit_reads_the_artifact_a_closure_cited(tmp_path) -> None:
    """Both seats reported they cannot read local files, so they judged "was the
    proof run" from prose. The closer already submits artifact paths; nothing
    read them, so a genuinely-proven closure could not pass."""
    art = tmp_path / "live.txt"
    art.write_text("PASS: live run against the real repo\n")

    found = handlers.collect_closure_artifacts([_evidence_comment(str(art))])

    assert len(found) == 1
    assert found[0]["tier"] == "e2e"
    assert "PASS: live run" in found[0]["content"]


def test_a_cited_artifact_that_is_gone_is_reported_not_dropped(tmp_path) -> None:
    """An artifact that cannot be produced is itself a fact about the closure."""
    found = handlers.collect_closure_artifacts([_evidence_comment(str(tmp_path / "nope.txt"))])
    assert len(found) == 1 and "missing" in found[0]
    rendered = handlers.render_closure_artifacts(found)
    assert "NOT READABLE" in rendered


def test_artifacts_are_capped_so_a_huge_log_cannot_crowd_out_the_ticket(tmp_path) -> None:
    art = tmp_path / "big.txt"
    art.write_text("x" * (handlers.ARTIFACT_EXCERPT_CHARS * 3))
    found = handlers.collect_closure_artifacts([_evidence_comment(str(art))])
    assert len(found[0]["content"]) == handlers.ARTIFACT_EXCERPT_CHARS
    assert found[0]["bytes"] > handlers.ARTIFACT_EXCERPT_CHARS


def test_the_audit_prompt_tells_the_seat_the_artifacts_are_real_output(tmp_path) -> None:
    art = tmp_path / "a.txt"
    art.write_text("PASS")
    found = handlers.collect_closure_artifacts([_evidence_comment(str(art))])
    task = handlers.build_closure_audit_task(
        repo="o/r", issue_number=1, issue_title="t", issue_body="b",
        evidence="e", artifacts=handlers.render_closure_artifacts(found),
    )
    assert "read from disk" in task
    assert "PASS" in task


def test_closure_audit_prompt_omits_absolute_local_paths(tmp_path) -> None:
    """Browser-backed audit seats reject prompts containing live local paths."""
    art = tmp_path / "a.txt"
    art.write_text("PASS")
    found = handlers.collect_closure_artifacts([_evidence_comment(str(art))])

    task = handlers.build_closure_audit_task(
        repo="o/r",
        issue_number=1,
        issue_title="t",
        issue_body="read /home/graham/workspace/experiments/pdf_oxide/local/HANDOFF.md",
        evidence="receipt: /home/graham/.local/state/project-watchdog/receipts/r/receipt.json",
        artifacts=handlers.render_closure_artifacts(found),
    )

    assert "/home/" not in task
    assert "/tmp/" not in task
    assert "[local path omitted:" in task
    assert "PASS" in task


def test_a_comment_without_the_schema_yields_no_artifacts() -> None:
    assert handlers.collect_closure_artifacts([{"body": "```json\n{\"a\": 1}\n```"}]) == []


def test_a_pre_contract_closure_is_not_grounds_for_fail() -> None:
    """40 closures predate the evidence contract and cite no artifacts. Failing
    them for absent-by-design evidence would reopen all 40 and send repair
    agents at work that may be finished."""
    task = handlers.build_closure_audit_task(
        repo="o/r", issue_number=1, issue_title="t", issue_body="b",
        evidence="a closing comment with no evidence block",
        artifacts=handlers.render_closure_artifacts([]),
    )
    assert "predates the evidence contract" in task
    assert "not grounds for FAIL" in task
    assert "absent by design" in task


def test_a_duplicate_closure_is_not_audited_for_proof_of_work() -> None:
    """tau#213 was closed as a duplicate of a lower-numbered ticket. The audit
    reopened it for lacking proof of work it was never going to do."""
    import datetime as _dt

    now = _dt.datetime(2026, 7, 28, tzinfo=_dt.UTC)
    recent = (now - _dt.timedelta(hours=1)).isoformat().replace("+00:00", "Z")

    def closed(number, reason):
        return {"number": number, "title": "t", "body": "", "labels": [{"name": "agent-work"}],
                "closedAt": recent, "stateReason": reason, "url": "u"}

    gh = {"exit_code": 0, "stdout": json.dumps([
        closed(1, "COMPLETED"), closed(2, "NOT_PLANNED"), closed(3, "REOPENED"),
    ]), "stderr": ""}
    with mock.patch.object(registry, "run_cmd", return_value=gh):
        pending = registry.list_closed_for_audit(
            "run", {"repo": TAU_REPO, "project_id": "p"}, now=now.timestamp()
        )
    assert [i["number"] for i in pending] == [1], "only closures claiming the work is done"


def test_the_attestation_shows_whether_each_closure_was_verified() -> None:
    """Given only titles and statuses the attestor refused to certify anything --
    "a set of titles and statuses with no underlying evidence" -- so the lane
    could only ever answer NEEDS_ATTENTION."""
    recent = [
        {"number": 1, "title": "a", "stateReason": "COMPLETED",
         "labels": [{"name": config.CLOSURE_VERIFIED_LABEL}]},
        {"number": 2, "title": "b", "stateReason": "COMPLETED", "labels": []},
    ]
    task = handlers.build_completion_attestation_task(repo=TAU_REPO, recent=recent)
    assert "#1 [COMPLETED] [audited+upheld]" in task
    assert "#2 [COMPLETED] [closure NOT independently verified]" in task
    assert "independently" in task


# --------------------------------------------------------------------------- #
# A finished repair must not be re-dispatched over itself
# --------------------------------------------------------------------------- #


def test_a_finished_repair_stops_being_routable() -> None:
    """watchdog-probe#1: the repair completed, the lease was released, the ticket
    stayed agent-work, and cron re-dispatched it -- each dispatch resetting the
    branch over the previous fix."""
    issue = _issue(1, labels=["agent-work", config.DONE_LABEL], body="target: src/x.py\n")
    action, reason = registry.classify_issue_with_reason(issue)
    assert action is None and reason == "awaiting_review"


def test_a_completed_repair_marks_the_ticket_done(tmp_path) -> None:
    _seed_passing_repair_evidence(tmp_path)
    project = {
        "project_id": "p", "repo": TAU_REPO, "worktree": str(_clean_worktree(tmp_path)),
    }
    issue = _issue(51, labels=["agent-work"], body="type: bug\ntarget: skills/x\n")
    issue["watchdog_action"] = "ticket_repair"
    edits: list[dict] = []
    with (
        mock.patch.object(handlers.github, "issue_comment", return_value={"exit_code": 0}),
        mock.patch.object(
            handlers.github, "issue_edit",
            side_effect=lambda *a, **k: edits.append(k) or {"exit_code": 0},
        ),
        mock.patch.object(
            handlers.registry, "prepare_repair_worktree",
            return_value={"ok": True, "branch": "watchdog/issue-51",
                          "worktree": str(tmp_path / "wt")},
        ),
        mock.patch.object(handlers.registry, "remote_main_sha", side_effect=["a", "a"]),
        mock.patch.object(handlers, "run_ask_tau_dag_with_stream_monitor", side_effect=_passing_ask_tau_dag),
        mock.patch.object(handlers, "run_cmd", side_effect=_passing_repair_run_cmd),
    ):
        result = handlers.handle_issue("run", tmp_path, project, issue, apply=True)

    assert result["status"] == "COMPLETED"
    assert any(e.get("add") == [config.DONE_LABEL] for e in edits), "must mark it done"


def test_a_worktree_holding_unmerged_work_is_not_reset(tmp_path, monkeypatch) -> None:
    """`worktree add -B` resets the branch to origin/main. Removing and re-adding
    blindly destroyed codex's commit 9feb862 on watchdog-probe#1."""
    wt = tmp_path / "wt"
    wt.mkdir()
    calls: list[list[str]] = []

    def fake_run(cmd, timeout_s=None):
        calls.append(cmd)
        if "log" in cmd:
            return {"exit_code": 0, "stdout": "9feb862 Fix partial-window rolling means\n"}
        return {"exit_code": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(registry, "run_cmd", fake_run)
    out = registry.prepare_repair_worktree(tmp_path / "repo", wt, 1)

    assert out["ok"] is False
    assert "unmerged" in out and out["unmerged"]
    assert "lose that work" in out["error"]
    assert not any("remove" in c for c in calls), "must not remove a worktree holding work"


def test_a_panel_that_could_not_reach_a_provider_names_the_cause(tmp_path) -> None:
    """A revoked Claude OAuth token surfaced only as "no usable panel verdict";
    the operator had to dig through recovery packets to find it."""
    node = tmp_path / "run" / "node-artifacts" / "handler-claude-opus-4-8"
    node.mkdir(parents=True)
    (node / "node-receipt.json").write_text(json.dumps(
        {"node_id": "handler-claude-opus-4-8", "status": "NEEDS_ATTENTION",
         "failure_code": "scillm_auth_invalid_api_key"}))
    ok = tmp_path / "run" / "node-artifacts" / "handler-gpt-5-5-xhigh"
    ok.mkdir(parents=True)
    (ok / "node-receipt.json").write_text(json.dumps({"node_id": "x", "status": "PASS"}))

    failures = handlers.read_seat_failures(tmp_path)

    assert failures == {"handler-claude-opus-4-8": "scillm_auth_invalid_api_key"}


def test_an_upheld_closure_that_cannot_be_marked_is_not_reported_clean(tmp_path) -> None:
    """`closure-verified` existed in no repo and was absent from ensure-labels,
    so the first unanimous PASS marked nothing and the closure would be
    re-audited every tick."""
    result, calls = _run_audit(
        tmp_path, {"handler-a": "VERDICT: PASS", "handler-b": "VERDICT: PASS"}
    )
    assert result["verdict"] == "PASS" and result["status"] == "COMPLETED"

    with (
        mock.patch.object(handlers.github, "issue_comments", return_value=[]),
        mock.patch.object(handlers.github, "issue_comment", return_value={"exit_code": 0}),
        mock.patch.object(
            handlers.github, "issue_edit",
            return_value={"exit_code": 1, "stderr": "label 'closure-verified' not found"},
        ),
        mock.patch.object(handlers, "run_cmd", return_value={"exit_code": 0, "stderr": ""}),
        mock.patch.object(
            handlers, "_read_ask_responses_by_node",
            return_value={"a": "VERDICT: PASS", "b": "VERDICT: PASS"},
        ),
    ):
        blocked = handlers.handle_closure_audit(
            "run", tmp_path, {"project_id": "p", "repo": TAU_REPO, "worktree": str(tmp_path)},
            _closed(9, labels=["agent-work"], closed_at="2026-07-29T00:00:00Z"), apply=True,
        )
    assert blocked["status"] == "NEEDS_ATTENTION"
    assert "re-audited every tick" in blocked["summary"]


def test_a_once_a_minute_schedule_is_refused(capsys) -> None:
    from watchdog import commands

    """The measured runaway: ticks reach 302.8s, so a 60s period overlaps.

    1,381 tick_already_running collisions, 43,581 no-op ticks, a 1.2 GB log,
    and the entry disabled by hand on 2026-08-14. `*` stays reachable, but only
    as a decision somebody makes.
    """
    assert commands.install_cron(apply=False, minute="*") == 2
    # The message now names the measured period rather than a spelling, because
    # the check counts firings instead of matching "*".
    assert "refusing a schedule that fires every 60s" in capsys.readouterr().err


def test_an_explicit_override_still_allows_every_minute() -> None:
    from watchdog import commands

    assert commands.install_cron(apply=False, minute="*", allow_every_minute=True) == 0


def test_the_default_minute_is_not_every_minute() -> None:
    """The default is what gets installed when the docs are followed."""
    import inspect

    from watchdog import commands as _c

    assert inspect.signature(_c.install_cron).parameters["allow_every_minute"].default is False


@pytest.mark.parametrize("spelling", ["*", "*/1", "0-59"])
def test_every_spelling_of_once_a_minute_is_refused(spelling: str) -> None:
    """Matching a bare '*' was bypassable by three other spellings.

    Adversarial review predicted this and it reproduced: */1, 0-59 and an
    enumerated 0,1,...,59 all installed the same once-a-minute job the runaway
    came from.
    """
    from watchdog import commands

    assert commands.install_cron(apply=False, minute=spelling) == 2


def test_an_enumerated_every_minute_list_is_refused() -> None:
    from watchdog import commands

    assert commands.install_cron(apply=False, minute=",".join(str(i) for i in range(60))) == 2


def test_an_unparseable_minute_field_fails_closed() -> None:
    """A field nobody has reasoned about must not be installed verbatim."""
    from watchdog import commands

    assert commands.install_cron(apply=False, minute="bogus") == 2


@pytest.mark.parametrize(("field", "period"), [("*", 60), ("*/5", 300), ("0", 3600), ("0,30", 1800)])
def test_the_period_is_computed_from_expansion_not_spelling(field: str, period: int) -> None:
    from watchdog import commands

    assert commands.minute_field_period_seconds(field) == period


def test_a_tick_starting_before_the_batch_window_is_deferred() -> None:
    """A start-time-only check let work begun at 01:59:59 invade 02:00."""
    import datetime

    from watchdog import config

    assert config.tick_would_enter_quiet_hours(datetime.datetime(2026, 1, 1, 1, 59))
    assert not config.tick_would_enter_quiet_hours(datetime.datetime(2026, 1, 1, 15, 0))


def test_the_tick_deadline_is_derived_from_the_installed_period(monkeypatch) -> None:
    """A deadline longer than the period is the overlap it exists to prevent."""
    from watchdog import commands

    monkeypatch.delenv("PROJECT_WATCHDOG_TICK_DEADLINE_SECONDS", raising=False)
    monkeypatch.setattr(commands, "installed_cron_minute", lambda: "*/5")
    assert commands.tick_deadline_seconds() == 240

    monkeypatch.setattr(commands, "installed_cron_minute", lambda: "*/15")
    assert commands.tick_deadline_seconds() == 720


def test_the_tick_deadline_falls_back_when_no_cron_is_installed(monkeypatch) -> None:
    from watchdog import commands

    monkeypatch.delenv("PROJECT_WATCHDOG_TICK_DEADLINE_SECONDS", raising=False)
    monkeypatch.setattr(commands, "installed_cron_minute", lambda: None)
    assert commands.tick_deadline_seconds() == commands.DEFAULT_TICK_DEADLINE_SECONDS


def test_the_installed_minute_is_read_from_the_marked_line(monkeypatch) -> None:
    from watchdog import commands, config

    crontab = f"0 3 * * * something-else\n{config.CRON_MARKER}\n*/5 * * * * watchdog tick\n"
    monkeypatch.setattr(
        commands, "run_cmd", lambda *a, **k: {"exit_code": 0, "stdout": crontab}
    )
    assert commands.installed_cron_minute() == "*/5"


def test_the_first_issue_is_never_deferred_by_the_deadline() -> None:
    """A deadline that starves the queue is not a safety property."""
    from watchdog import commands

    assert commands.defer_for_deadline(0, elapsed=10_000.0, deadline=240) is False


def test_later_issues_are_deferred_once_the_deadline_passes() -> None:
    from watchdog import commands

    assert commands.defer_for_deadline(1, elapsed=241.0, deadline=240) is True
    assert commands.defer_for_deadline(1, elapsed=1.0, deadline=240) is False


def test_the_deadline_is_always_shorter_than_the_period(monkeypatch) -> None:
    """The invariant the deadline exists for: it must not span a firing."""
    from watchdog import commands

    monkeypatch.delenv("PROJECT_WATCHDOG_TICK_DEADLINE_SECONDS", raising=False)
    for field in ("*/2", "*/5", "*/15", "0,30"):
        monkeypatch.setattr(commands, "installed_cron_minute", lambda f=field: f)
        period = commands.minute_field_period_seconds(field)
        assert commands.tick_deadline_seconds() < period
