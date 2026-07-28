"""Unit tests for project-watchdog parsing, routing, locking, and receipt policy.

These are pure unit tests over the watchdog package. The behavioural acceptance
gates that exercise the real CLI against real files live in ``sanity.sh``.
"""

from __future__ import annotations

import importlib
import json
import sys
import time
from datetime import UTC, datetime, timedelta
import os
import subprocess
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from watchdog import (  # noqa: E402
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
            "run-test", {"repo": TAU_REPO, "runner_kind": "tau-command-loop"}
        )
    assert len(selected) == 1
    assert selected[0]["watchdog_action"] == "ticket_repair"


def test_ticket_repair_is_not_routable_without_a_repair_lane() -> None:
    """A project with no Tau DAG lane must not claim ticket_repair (#1044).

    Claiming it only to block it leases and blocks a different ticket every
    tick and exits 1 every minute, which reads as many broken tickets rather
    than one unconfigured project.
    """
    issue = _issue(
        45,
        labels=["agent-work", "type:bug", "route:backend_python_or_skill_runtime"],
        body="## Type\n\nbug\n\n## Target\n\nsrc/thing.py",
    )
    gh_result = {"exit_code": 0, "stdout": json.dumps([issue]), "stderr": ""}
    with mock.patch.object(registry, "run_cmd", return_value=gh_result):
        selected = registry.list_routable_issues(
            "run-test",
            {"repo": TAU_REPO, "project_id": "agent-skills", "runner_kind": "project-local"},
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
    owner.write_text(json.dumps(payload), encoding="utf-8")
    assert core.acquire_lock("recovery-run") is True
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


def test_ticket_repair_refuses_a_project_with_no_bounded_runner(tmp_path) -> None:
    project = {
        "project_id": "memory",
        "repo": "grahama1970/graph-memory-operator",
        "worktree": str(tmp_path),
        "runner_kind": "project-local",
    }
    issue = _issue(7, labels=["agent-work"])
    issue["watchdog_action"] = "ticket_repair"
    result = handlers.handle_issue("run", tmp_path, project, issue, apply=True)
    assert result["status"] == "BLOCKED"
    assert "runner_kind" in result["summary"]
    assert "tau-command-loop" in result["summary"]


def _worktree_with_specs(tmp_path: Path) -> Path:
    """Create the Tau command-spec layout the repair DAG requires.

    Committed on a clean ``main``: dispatch fails closed on a worktree that is
    on a feature branch or has dirty tracked files (#1045), so a fixture that is
    not a real, clean git worktree no longer represents a dispatchable project.
    """
    root = tmp_path / "experiments/goal-locked-subagents/agent-command-specs"
    for node in ("coder", "reviewer"):
        (root / node).mkdir(parents=True)
        (root / node / "tau-dispatch-command.json").write_text("{}", encoding="utf-8")
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    }
    for args in (("init", "-q", "-b", "main", "."), ("add", "-A"), ("commit", "-q", "-m", "specs")):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True,
                       capture_output=True, env=env)
    return tmp_path


def test_ticket_repair_dry_run_makes_no_github_call(tmp_path) -> None:
    project = {
        "project_id": "tau",
        "repo": TAU_REPO,
        "worktree": str(_worktree_with_specs(tmp_path)),
        "runner_kind": "tau-command-loop",
    }
    issue = _issue(8, labels=["agent-work"])
    issue["watchdog_action"] = "ticket_repair"
    with mock.patch.object(handlers.github, "issue_comment") as comment:
        result = handlers.handle_issue("run", tmp_path, project, issue, apply=False)
    assert result["status"] == "DRY_RUN"
    assert not comment.called


def test_ticket_repair_compiles_a_dag_contract_and_runs_dag_run(tmp_path) -> None:
    project = {
        "project_id": "tau",
        "repo": TAU_REPO,
        "worktree": str(_worktree_with_specs(tmp_path)),
        "runner_kind": "tau-command-loop",
    }
    issue = _issue(9, labels=["agent-work"])
    issue["watchdog_action"] = "ticket_repair"
    with (
        mock.patch.object(handlers.github, "issue_comment", return_value={"exit_code": 0}),
        mock.patch.object(handlers.github, "issue_edit", return_value={"exit_code": 0}),
        mock.patch.object(
            handlers, "run_cmd", return_value={"exit_code": 0, "stderr": ""}
        ) as bounded,
    ):
        result = handlers.handle_issue("run", tmp_path, project, issue, apply=True)
    assert result["ok"] is True and result["status"] == "COMPLETED"
    argv = bounded.call_args.args[0]
    assert argv[1:4] == ["run", "tau", "dag-run"], "repair must go through Tau's DAG lane"
    assert "--command-spec-root" in argv

    contract = json.loads((tmp_path / "repair-dag.json").read_text(encoding="utf-8"))
    assert contract["schema"] == "tau.dag_contract.v1"
    assert contract["entry_node"] == "coder"
    assert contract["terminal_nodes"] == ["human"]
    node_ids = [n["id"] for n in contract["nodes"]]
    assert node_ids == ["coder", "reviewer", "human"]


def test_failed_ticket_repair_blocks_the_issue(tmp_path) -> None:
    """A failed repair must stop cron retrying it every minute."""
    project = {
        "project_id": "tau",
        "repo": TAU_REPO,
        "worktree": str(_worktree_with_specs(tmp_path)),
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
        mock.patch.object(handlers, "run_cmd", return_value={"exit_code": 1, "stderr": "x"}),
    ):
        result = handlers.handle_issue("run", tmp_path, project, issue, apply=True)
    assert result["status"] == "NEEDS_ATTENTION"
    assert any(e.get("add") == [config.BLOCKED_LABEL] for e in edits)


def test_repair_contract_gates_on_real_repair_evidence() -> None:
    """A transport-only stub must not be able to report a repair it never did."""
    contract = handlers.build_repair_contract(
        repo=TAU_REPO,
        issue_number=7,
        issue_title="t",
        goal_hash="sha256:" + "0" * 64,
        spec_root="/specs",
    )
    coder = next(n for n in contract["nodes"] if n["id"] == "coder")
    assert coder["required_evidence"] == ["changed_files", "focused_tests"]
    assert "missing_required_evidence" in contract["fail_closed_on"]
    assert "goal_hash_mismatch" in contract["fail_closed_on"]


def test_goal_hash_is_stable_across_reruns() -> None:
    """Tau requires one goal_hash across every node, receipt, and rerun."""
    a = handlers.issue_goal_hash(TAU_REPO, 149)
    b = handlers.issue_goal_hash(TAU_REPO, 149)
    assert a == b and a.startswith("sha256:")
    assert a != handlers.issue_goal_hash(TAU_REPO, 150)


def test_missing_command_specs_block_before_any_github_write(tmp_path) -> None:
    project = {
        "project_id": "tau",
        "repo": TAU_REPO,
        "worktree": str(tmp_path),
        "runner_kind": "tau-command-loop",
    }
    issue = _issue(11, labels=["agent-work"])
    issue["watchdog_action"] = "ticket_repair"
    with mock.patch.object(handlers.github, "issue_comment") as comment:
        result = handlers.handle_issue("run", tmp_path, project, issue, apply=True)
    assert result["status"] == "BLOCKED"
    assert "missing Tau command specs" in result["summary"]
    assert not comment.called
