"""Unit tests for project-watchdog parsing, routing, locking, and receipt policy.

These are pure unit tests over the watchdog package. The behavioural acceptance
gates that exercise the real CLI against real files live in ``sanity.sh``.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from watchdog import config, core, github, issue_fields, registry  # noqa: E402

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


def test_routing_skips_issue_without_marker() -> None:
    issue = _issue(44, labels=["agent-work", "executor:local"], body="no directive here")
    gh_result = {"exit_code": 0, "stdout": json.dumps([issue]), "stderr": ""}
    with mock.patch.object(registry, "run_cmd", return_value=gh_result):
        assert registry.list_routable_issues("run-test", {"repo": TAU_REPO}) == []


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
