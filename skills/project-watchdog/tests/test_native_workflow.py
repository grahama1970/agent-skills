"""Native Pi workflow handoff and fail-closed result checks."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "watchdog_v2.py"
SPEC = importlib.util.spec_from_file_location("watchdog_v2", SOURCE)
assert SPEC and SPEC.loader
watchdog = importlib.util.module_from_spec(SPEC)
import sys
sys.modules[SPEC.name] = watchdog
SPEC.loader.exec_module(watchdog)


def event_stream(fixer_status: str = "COMPLETE", reviewer_verdict: str = "PASS", *, exact_call: bool = True) -> str:
    path = "/tmp/watchdog-workflow/ticket.js"
    cwd = "/tmp/watchdog-target"
    args = {"workflowScriptPath": path, "cwd": cwd, "async": False}
    if not exact_call:
        args["workflowScriptPath"] = "/tmp/other.js"
    call = {"type": "message_end", "message": {"role": "assistant", "content": [{"type": "toolCall", "id": "call-1", "name": "subagent", "arguments": args}]}}
    fixer = {"ok": True, "runId": "fixer-run", "output": json.dumps({"status": fixer_status, "summary": "done", "checks": []})}
    reviewer = {"ok": True, "runId": "reviewer-run", "output": json.dumps({"verdict": reviewer_verdict, "findings": []})}
    result = {
        "type": "message_end",
        "message": {
            "role": "toolResult",
            "toolName": "subagent",
            "toolCallId": "call-1",
            "isError": False,
            "details": {
                "mode": "workflow",
                "runId": "workflow-run",
                "workflow": {"value": {"schema": "project_watchdog.v2.workflow", "fixer": fixer, "reviewer": reviewer}},
                "workflowChildren": {
                    "inventoryComplete": True,
                    "workflowState": "completed",
                    "children": [{"childId": "fixer", "state": "completed"}, {"childId": "reviewer", "state": "completed"}],
                },
            },
        },
    }
    return "\n".join(json.dumps(event) for event in (call, result))


class NativeWorkflowTests(unittest.TestCase):
    def test_maintainer_active_ticket_is_not_eligible(self) -> None:
        project = watchdog.Project(
            project_id="sample", repo="owner/repo", cwd="/tmp",
            ready_label="agent-work", active_label="agent-active", done_label="agent-done",
            target_prefixes=(), target_excludes=(), default_state="active", proof_command=("true",),
        )
        issue = {"title": "work", "body": "", "labels": [{"name": "agent-work"}, {"name": "maintainer-active"}]}
        self.assertFalse(watchdog.eligible(issue, project))

    def test_registry_runner_command_is_the_default_proof_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "projects.json"
            path.write_text(json.dumps({
                "projects": [{
                    "project_id": "sample",
                    "repo": "owner/repo",
                    "runner": {"cwd": directory, "command": "bash sanity.sh"},
                }],
            }), encoding="utf-8")
            project = watchdog.load_projects(path)[0]
            self.assertEqual(project.proof_command, ("bash", "sanity.sh"))

    def parse(self, stream: str) -> dict:
        return watchdog.parse_workflow_events(stream, Path("/tmp/watchdog-workflow/ticket.js"), "/tmp/watchdog-target")

    def test_global_pi_is_not_shadowed_by_workspace_binary(self) -> None:
        with patch.dict(os.environ, {"PATH": "/workspace/node_modules/.bin:/global/bin", "PROJECT_WATCHDOG_PI_BIN": ""}, clear=False):
            with patch.object(watchdog.shutil, "which", return_value="/global/bin/pi") as lookup:
                self.assertEqual(watchdog.pi_executable(), "/global/bin/pi")
        lookup.assert_called_once_with("pi", path="/global/bin")

    def test_invalid_pi_override_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            with patch.dict(os.environ, {"PROJECT_WATCHDOG_PI_BIN": str(Path(root) / "missing")}, clear=False):
                with self.assertRaisesRegex(OSError, "executable absolute path"):
                    watchdog.pi_executable()

    def test_nested_pi_is_pinned_to_selected_binary(self) -> None:
        with patch.dict(os.environ, {"PATH": "/workspace/node_modules/.bin:/global/bin", "PROJECT_WATCHDOG_PI_BIN": ""}, clear=False):
            with patch.object(watchdog.shutil, "which", return_value="/global/bin/pi"):
                child = watchdog.pi_environment()
        self.assertEqual(child["PI_SUBAGENT_PI_BINARY"], "/global/bin/pi")
        self.assertEqual(child["PATH"], "/global/bin")

    def test_complete_native_workflow_passes(self) -> None:
        result = self.parse(event_stream())
        self.assertTrue(result["ok"])
        self.assertTrue(watchdog.reviewer_passed(result))

    def test_blocked_fixer_cannot_pass(self) -> None:
        result = self.parse(event_stream(fixer_status="BLOCKED"))
        self.assertFalse(result["ok"])
        self.assertEqual(result["failed_role"], "fixer")
        self.assertFalse(watchdog.reviewer_passed(result))

    def test_failed_reviewer_cannot_pass(self) -> None:
        result = self.parse(event_stream(reviewer_verdict="FAIL"))
        self.assertFalse(result["ok"])
        self.assertEqual(result["failed_role"], "reviewer")

    def test_wrong_tool_call_cannot_pass(self) -> None:
        result = self.parse(event_stream(exact_call=False))
        self.assertFalse(result["ok"])
        self.assertEqual(result["failed_role"], "workflow")

    def test_parent_prose_cannot_replace_tool_result(self) -> None:
        text = json.dumps({"type": "message_end", "message": {"role": "assistant", "content": [{"type": "text", "text": '{"verdict":"PASS"}'}]}})
        self.assertFalse(self.parse(text)["ok"])

    def test_failed_extra_node_cannot_be_ignored(self) -> None:
        events = [json.loads(line) for line in event_stream().splitlines()]
        result = events[1]["message"]["details"]
        value = result["workflow"]["value"]
        value["results"] = {
            "scout": {"ok": False, "output": "blocked"},
            "fixer": value["fixer"],
            "reviewer": value["reviewer"],
        }
        result["workflowChildren"]["children"].append({"childId": "scout", "state": "failed"})
        parsed = self.parse("\n".join(json.dumps(event) for event in events))
        self.assertFalse(parsed["ok"])
        self.assertEqual(parsed["failed_role"], "scout")


if __name__ == "__main__":
    unittest.main()
