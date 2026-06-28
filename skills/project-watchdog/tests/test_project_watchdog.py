"""Focused tests for project-watchdog Tau issue intake helpers."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "project_watchdog.py"
SPEC = importlib.util.spec_from_file_location("project_watchdog", SCRIPT)
assert SPEC and SPEC.loader
project_watchdog = importlib.util.module_from_spec(SPEC)
sys.modules["project_watchdog"] = project_watchdog
SPEC.loader.exec_module(project_watchdog)


class ProjectWatchdogTests(unittest.TestCase):
    def test_parse_issue_fields_accepts_shell_style_values(self) -> None:
        fields = project_watchdog.parse_issue_fields(
            'project-watchdog-action:tau-handoff-dispatch start="experiments/start handoff.json" '
            "max_steps=2 apply_transport=true"
        )

        self.assertEqual(fields["start"], "experiments/start handoff.json")
        self.assertEqual(fields["max_steps"], "2")
        self.assertEqual(fields["apply_transport"], "true")

    def test_parse_positive_int_rejects_zero(self) -> None:
        with self.assertRaises(ValueError):
            project_watchdog.parse_positive_int("0", field="max_steps")

    def test_parse_bool_rejects_ambiguous_values(self) -> None:
        with self.assertRaises(ValueError):
            project_watchdog.parse_bool("yes", field="apply_transport")

    def test_repo_relative_existing_path_rejects_path_traversal(self) -> None:
        with self.assertRaises(ValueError):
            project_watchdog.repo_relative_existing_path("../outside.json")

    def test_list_routable_tau_issues_selects_generic_handoff_marker(self) -> None:
        issue = {
            "number": 42,
            "title": "dispatch",
            "body": "project-watchdog-action:tau-handoff-dispatch start=experiments/foo.json",
            "labels": [
                {"name": "agent-work"},
                {"name": "next:reviewer"},
                {"name": "executor:local"},
            ],
            "url": "https://github.com/grahama1970/tau/issues/42",
        }
        gh_result = {"exit_code": 0, "stdout": project_watchdog.json.dumps([issue]), "stderr": ""}

        with mock.patch.object(project_watchdog, "run_cmd", return_value=gh_result):
            selected = project_watchdog.list_routable_tau_issues(
                "run-test",
                {"repo": "grahama1970/tau"},
            )

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["watchdog_action"], "tau_handoff_dispatch")

    def test_list_routable_tau_issues_skips_blocked_issue(self) -> None:
        issue = {
            "number": 43,
            "title": "blocked",
            "body": "project-watchdog-action:tau-handoff-dispatch start=experiments/foo.json",
            "labels": [
                {"name": "agent-work"},
                {"name": "agent-blocked"},
                {"name": "executor:local"},
            ],
            "url": "https://github.com/grahama1970/tau/issues/43",
        }
        gh_result = {"exit_code": 0, "stdout": project_watchdog.json.dumps([issue]), "stderr": ""}

        with mock.patch.object(project_watchdog, "run_cmd", return_value=gh_result):
            selected = project_watchdog.list_routable_tau_issues(
                "run-test",
                {"repo": "grahama1970/tau"},
            )

        self.assertEqual(selected, [])


if __name__ == "__main__":
    unittest.main()
