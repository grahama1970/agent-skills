from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
LOOP = REPO_ROOT / "skills/loop/scripts/loop.py"
VALIDATOR = REPO_ROOT / "skills/loop/scripts/validate_loop_receipt.py"
FINAL_RECEIPT_SCHEMA = REPO_ROOT / "skills/loop/schemas/final-receipt.schema.json"
FIXTURES = REPO_ROOT / "skills/loop/tests/fixtures"


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(cmd, cwd=cwd, env=merged, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


class LoopFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        run(["git", "init"], self.repo)
        run(["git", "config", "user.email", "loop@example.test"], self.repo)
        run(["git", "config", "user.name", "Loop Test"], self.repo)
        self._write_initial_sample()
        self.config = self.repo / "agents.fixture.toml"
        self.config.write_text(
            textwrap.dedent(
                f"""
                [explorer]
                cmd = "{sys.executable} {FIXTURES / 'explorer_agent.py'}"
                writes = false
                timeout_seconds = 60

                [coder]
                cmd = "{sys.executable} {FIXTURES / 'coder_agent.py'}"
                writes = true
                timeout_seconds = 60

                [code-reviewer]
                cmd = "{sys.executable} {FIXTURES / 'code_reviewer_agent.py'}"
                writes = false
                timeout_seconds = 60
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        run(["git", "add", "."], self.repo)
        run(["git", "commit", "-m", "initial"], self.repo)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_initial_sample(self) -> None:
        src = self.repo / "sample-target/src/time/parse_duration.py"
        tests = self.repo / "sample-target/tests/test_parse_duration.py"
        src.parent.mkdir(parents=True, exist_ok=True)
        tests.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("def parse_duration(value: str) -> int:\n    raise NotImplementedError\n", encoding="utf-8")
        tests.write_text(
            """import unittest\n\n\nclass PlaceholderTests(unittest.TestCase):\n    def test_placeholder(self):\n        self.assertTrue(True)\n\n\nif __name__ == '__main__':\n    unittest.main()\n""",
            encoding="utf-8",
        )

    def _loop_cmd(
        self,
        max_attempts: int = 3,
        checks: list[str] | None = None,
        agent_config: Path | None = None,
        check_timeout: int | None = None,
    ) -> list[str]:
        selected_checks = [f"{sys.executable} -m unittest discover -s sample-target/tests"] if checks is None else checks
        cmd = [
            sys.executable,
            str(LOOP),
            "--objective",
            "implement parse_duration",
            "--agent-config",
            str(agent_config or self.config),
            "--allow",
            "sample-target/src/time/**",
            "--allow",
            "sample-target/tests/**",
            "--max-attempts",
            str(max_attempts),
            "--print-json",
        ]
        if check_timeout is not None:
            cmd.extend(["--check-timeout", str(check_timeout)])
        for check in selected_checks:
            cmd.extend(["--check", check])
        return cmd

    def _run_loop(self, mode: str = "pass", max_attempts: int = 3) -> tuple[subprocess.CompletedProcess[str], dict]:
        proc = run(self._loop_cmd(max_attempts=max_attempts), self.repo, {"LOOP_FIXTURE_MODE": mode})
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"loop stdout was not JSON: {proc.stdout}\nstderr={proc.stderr}\nerror={exc}")
        return proc, data

    def _latest_receipt(self, data: dict) -> Path:
        return self.repo / data["artifacts"]["run_dir"] / "final-receipt.json"

    def test_fixture_loop_passes(self) -> None:
        proc, data = self._run_loop("pass")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(data["final_verdict"], "PASS")
        self.assertEqual(data["attempts_used"], 1)
        receipt = self._latest_receipt(data)
        self.assertTrue(receipt.is_file())
        diff = self.repo / data["artifacts"]["final_diff"]
        self.assertIn("sample-target/tests/sample_target_import.py", diff.read_text(encoding="utf-8"))
        self.assertIn("parse_duration_module", diff.read_text(encoding="utf-8"))
        valid = run([sys.executable, str(VALIDATOR), str(receipt), "--print-summary"], self.repo)
        self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_final_receipt_schema_stop_reasons_match_validator(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("validate_loop_receipt", VALIDATOR)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        spec.loader.exec_module(module)
        schema = json.loads(FINAL_RECEIPT_SCHEMA.read_text(encoding="utf-8"))
        schema_reasons = set(schema["properties"]["stop_reason"]["enum"])
        self.assertEqual(schema_reasons, module.FINAL_RECEIPT_STOP_REASONS)
        self.assertIn("TIMEOUT", schema_reasons)

    def test_committed_fixture_config_array_commands_pass(self) -> None:
        config = REPO_ROOT / "skills/loop/examples/agents.fixture.toml"
        proc = run(self._loop_cmd(agent_config=config), self.repo, {"LOOP_FIXTURE_MODE": "pass"})
        data = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(data["final_verdict"], "PASS")

    def test_reviewer_pass_but_check_fails_does_not_pass(self) -> None:
        proc, data = self._run_loop("check_fail", max_attempts=1)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["final_verdict"], "NEEDS_CHANGES")
        self.assertEqual(data["stop_reason"], "MAX_ATTEMPTS")

    def test_disallowed_file_change_blocks(self) -> None:
        proc, data = self._run_loop("disallowed")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["final_verdict"], "BLOCKED")
        self.assertEqual(data["stop_reason"], "DISALLOWED_FILE_CHANGE")

    def test_disallowed_explorer_failure_dominates_with_valid_receipt(self) -> None:
        proc, data = self._run_loop("explorer_write_disallowed_fail")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["final_verdict"], "BLOCKED")
        self.assertEqual(data["stop_reason"], "DISALLOWED_FILE_CHANGE")
        self.assertEqual(data["attempts_used"], 0)
        self.assertIn("outside.txt", data["changed_files"])
        self.assertIn("explorer failed", data["reviewer"]["findings"])
        self.assertIn("explorer edited files", data["reviewer"]["findings"])
        valid = run([sys.executable, str(VALIDATOR), str(self._latest_receipt(data)), "--print-summary"], self.repo)
        self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_read_only_explorer_allowed_edit_blocks_with_valid_receipt(self) -> None:
        proc, data = self._run_loop("explorer_write_allowed_success")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["final_verdict"], "BLOCKED")
        self.assertEqual(data["stop_reason"], "AGENT_FAILED")
        self.assertEqual(data["attempts_used"], 0)
        self.assertIn("sample-target/src/time/parse_duration.py", data["changed_files"])
        self.assertIn("explorer edited files", data["reviewer"]["findings"])
        valid = run([sys.executable, str(VALIDATOR), str(self._latest_receipt(data)), "--print-summary"], self.repo)
        self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_disallowed_explorer_timeout_dominates_with_valid_receipt(self) -> None:
        timeout_config = self.repo / "explorer-timeout-agents.toml"
        timeout_config.write_text(
            textwrap.dedent(
                f"""
                [explorer]
                cmd = "{sys.executable} {FIXTURES / 'explorer_agent.py'}"
                writes = false
                timeout_seconds = 1

                [coder]
                cmd = "{sys.executable} {FIXTURES / 'coder_agent.py'}"
                writes = true
                timeout_seconds = 60

                [code-reviewer]
                cmd = "{sys.executable} {FIXTURES / 'code_reviewer_agent.py'}"
                writes = false
                timeout_seconds = 60
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        run(["git", "add", str(timeout_config.relative_to(self.repo))], self.repo)
        run(["git", "commit", "-m", "add explorer timeout config"], self.repo)
        proc = run(self._loop_cmd(agent_config=timeout_config), self.repo, {"LOOP_FIXTURE_MODE": "explorer_timeout_disallowed"})
        data = json.loads(proc.stdout)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["final_verdict"], "BLOCKED")
        self.assertEqual(data["stop_reason"], "DISALLOWED_FILE_CHANGE")
        self.assertEqual(data["attempts_used"], 0)
        self.assertIn("outside.txt", data["changed_files"])
        self.assertIn("explorer timed out", data["reviewer"]["findings"])
        self.assertIn("explorer edited files", data["reviewer"]["findings"])
        valid = run([sys.executable, str(VALIDATOR), str(self._latest_receipt(data)), "--print-summary"], self.repo)
        self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_disallowed_coder_failure_dominates_with_valid_receipt(self) -> None:
        proc, data = self._run_loop("disallowed_fail")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["final_verdict"], "BLOCKED")
        self.assertEqual(data["stop_reason"], "DISALLOWED_FILE_CHANGE")
        self.assertIn("outside.txt", data["changed_files"])
        self.assertIn("coder failed", data["reviewer"]["findings"])
        valid = run([sys.executable, str(VALIDATOR), str(self._latest_receipt(data)), "--print-summary"], self.repo)
        self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_disallowed_coder_timeout_dominates_with_valid_receipt(self) -> None:
        timeout_config = self.repo / "coder-timeout-agents.toml"
        timeout_config.write_text(
            textwrap.dedent(
                f"""
                [explorer]
                cmd = "{sys.executable} {FIXTURES / 'explorer_agent.py'}"
                writes = false
                timeout_seconds = 60

                [coder]
                cmd = "{sys.executable} {FIXTURES / 'coder_agent.py'}"
                writes = true
                timeout_seconds = 1

                [code-reviewer]
                cmd = "{sys.executable} {FIXTURES / 'code_reviewer_agent.py'}"
                writes = false
                timeout_seconds = 60
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        run(["git", "add", str(timeout_config.relative_to(self.repo))], self.repo)
        run(["git", "commit", "-m", "add coder timeout config"], self.repo)
        proc = run(self._loop_cmd(agent_config=timeout_config), self.repo, {"LOOP_FIXTURE_MODE": "disallowed_timeout"})
        data = json.loads(proc.stdout)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["final_verdict"], "BLOCKED")
        self.assertEqual(data["stop_reason"], "DISALLOWED_FILE_CHANGE")
        self.assertIn("outside.txt", data["changed_files"])
        self.assertIn("coder timed out", data["reviewer"]["findings"])
        valid = run([sys.executable, str(VALIDATOR), str(self._latest_receipt(data)), "--print-summary"], self.repo)
        self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_check_side_effect_out_of_scope_blocks_final_pass(self) -> None:
        check = (
            f"{sys.executable} -c "
            "\"from pathlib import Path; Path('outside-from-check.txt').write_text('bad')\""
        )
        proc = run(self._loop_cmd(max_attempts=1, checks=[check]), self.repo, {"LOOP_FIXTURE_MODE": "pass"})
        data = json.loads(proc.stdout)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["final_verdict"], "BLOCKED")
        self.assertEqual(data["stop_reason"], "DISALLOWED_FILE_CHANGE")
        self.assertIn("outside-from-check.txt", data["changed_files"])

    def test_failing_check_side_effect_out_of_scope_blocks_with_valid_receipt(self) -> None:
        check = (
            f"{sys.executable} -c "
            "\"from pathlib import Path; Path('outside-from-check.txt').write_text('bad'); raise SystemExit(1)\""
        )
        proc = run(self._loop_cmd(max_attempts=1, checks=[check]), self.repo, {"LOOP_FIXTURE_MODE": "pass"})
        data = json.loads(proc.stdout)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["final_verdict"], "BLOCKED")
        self.assertEqual(data["stop_reason"], "DISALLOWED_FILE_CHANGE")
        self.assertIn("outside-from-check.txt", data["changed_files"])
        valid = run([sys.executable, str(VALIDATOR), str(self._latest_receipt(data)), "--print-summary"], self.repo)
        self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_reviewer_edit_blocks(self) -> None:
        proc, data = self._run_loop("reviewer_edit")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["final_verdict"], "BLOCKED")
        self.assertEqual(data["stop_reason"], "REVIEWER_EDITED_FILES")

    def test_disallowed_reviewer_edit_dominates_with_valid_receipt(self) -> None:
        proc, data = self._run_loop("reviewer_edit_disallowed")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["final_verdict"], "BLOCKED")
        self.assertEqual(data["stop_reason"], "DISALLOWED_FILE_CHANGE")
        self.assertIn("outside.txt", data["changed_files"])
        self.assertIn("code-reviewer edited files", data["reviewer"]["findings"])
        valid = run([sys.executable, str(VALIDATOR), str(self._latest_receipt(data)), "--print-summary"], self.repo)
        self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_agents_do_not_receive_artifact_paths(self) -> None:
        proc = run(
            self._loop_cmd(),
            self.repo,
            {
                "LOOP_FIXTURE_MODE": "assert_no_artifact_access",
                "LOOP_RUN_DIR": "/tmp/leaked-run-dir",
                "LOOP_CHECKS_JSON": "[]",
                "LOOP_DIFF_PATH": "/tmp/leaked.diff",
                "LOOP_RANDOM_PARENT_VALUE": "should-not-leak",
            },
        )
        data = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(data["final_verdict"], "PASS")
        diff = self.repo / data["artifacts"]["final_diff"]
        diff_text = diff.read_text(encoding="utf-8")
        self.assertIn("sample-target/tests/sample_target_import.py", diff_text)
        self.assertIn("parse_duration_module", diff_text)
        valid = run([sys.executable, str(VALIDATOR), str(self._latest_receipt(data)), "--print-summary"], self.repo)
        self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_check_timeout_writes_final_receipt(self) -> None:
        check = f"{sys.executable} -c \"import time; time.sleep(5)\""
        proc = run(
            self._loop_cmd(max_attempts=1, checks=[check], check_timeout=1),
            self.repo,
            {"LOOP_FIXTURE_MODE": "pass"},
        )
        data = json.loads(proc.stdout)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["final_verdict"], "BLOCKED")
        self.assertEqual(data["stop_reason"], "TIMEOUT")
        self.assertEqual(data["checks"][0]["returncode"], -125)
        self.assertTrue(data["checks"][0]["timed_out"])
        self.assertIn("deterministic check timed out", data["reviewer"]["findings"])
        valid = run([sys.executable, str(VALIDATOR), str(self._latest_receipt(data)), "--print-summary"], self.repo)
        self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_array_command_spawn_failure_writes_blocked_receipt(self) -> None:
        missing_config = self.repo / "missing-agent.toml"
        missing_config.write_text(
            textwrap.dedent(
                f"""
                [explorer]
                cmd = ["/tmp/definitely-missing-loop-agent"]
                writes = false
                timeout_seconds = 60

                [coder]
                cmd = "{sys.executable} {FIXTURES / 'coder_agent.py'}"
                writes = true
                timeout_seconds = 60

                [code-reviewer]
                cmd = "{sys.executable} {FIXTURES / 'code_reviewer_agent.py'}"
                writes = false
                timeout_seconds = 60
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        run(["git", "add", str(missing_config.relative_to(self.repo))], self.repo)
        run(["git", "commit", "-m", "add missing agent config"], self.repo)
        proc = run(self._loop_cmd(agent_config=missing_config), self.repo)
        data = json.loads(proc.stdout)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["final_verdict"], "BLOCKED")
        self.assertEqual(data["stop_reason"], "AGENT_FAILED")
        self.assertEqual(data["attempts_used"], 0)
        self.assertIn("explorer start failed", data["reviewer"]["findings"])
        valid = run([sys.executable, str(VALIDATOR), str(self._latest_receipt(data)), "--print-summary"], self.repo)
        self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_invalid_reviewer_json_blocks(self) -> None:
        proc, data = self._run_loop("invalid_review")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["final_verdict"], "BLOCKED")
        self.assertEqual(data["stop_reason"], "INVALID_REVIEWER_OUTPUT")

    def test_invalid_reviewer_findings_blocks_with_valid_receipt(self) -> None:
        proc, data = self._run_loop("invalid_findings")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["final_verdict"], "BLOCKED")
        self.assertEqual(data["stop_reason"], "INVALID_REVIEWER_OUTPUT")
        valid = run([sys.executable, str(VALIDATOR), str(self._latest_receipt(data)), "--print-summary"], self.repo)
        self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_max_attempts_returns_needs_changes(self) -> None:
        proc, data = self._run_loop("max_attempts", max_attempts=2)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["final_verdict"], "NEEDS_CHANGES")
        self.assertEqual(data["attempts_used"], 2)

    def test_no_check_cannot_return_pass(self) -> None:
        proc = run(self._loop_cmd(max_attempts=1, checks=[]), self.repo, {"LOOP_FIXTURE_MODE": "pass"})
        data = json.loads(proc.stdout)
        self.assertNotEqual(proc.returncode, 0)
        self.assertNotEqual(data["final_verdict"], "PASS")

    def test_agent_timeout_writes_blocked_receipt(self) -> None:
        timeout_config = self.repo / "timeout-agents.toml"
        timeout_config.write_text(
            textwrap.dedent(
                f"""
                [explorer]
                cmd = ["{sys.executable}", "-c", "import time; time.sleep(2)"]
                writes = false
                timeout_seconds = 1

                [coder]
                cmd = "{sys.executable} {FIXTURES / 'coder_agent.py'}"
                writes = true
                timeout_seconds = 60

                [code-reviewer]
                cmd = "{sys.executable} {FIXTURES / 'code_reviewer_agent.py'}"
                writes = false
                timeout_seconds = 60
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        run(["git", "add", str(timeout_config.relative_to(self.repo))], self.repo)
        run(["git", "commit", "-m", "add timeout config"], self.repo)
        proc = run(self._loop_cmd(agent_config=timeout_config), self.repo)
        data = json.loads(proc.stdout)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["final_verdict"], "BLOCKED")
        self.assertEqual(data["stop_reason"], "TIMEOUT")
        self.assertTrue(self._latest_receipt(data).is_file())

    def _timeout_child_code(self) -> str:
        return (
            "import pathlib, time; "
            "time.sleep(2); "
            "pathlib.Path('late-after-timeout.txt').write_text('late')"
        )

    def _timeout_parent_code(self) -> str:
        return (
            "import subprocess, sys, time; "
            f"subprocess.Popen([sys.executable, '-c', {self._timeout_child_code()!r}]); "
            "time.sleep(5)"
        )

    def _write_timeout_tree_config(self, cmd_line: str, timeout_seconds: int = 1) -> Path:
        timeout_config = self.repo / f"timeout-tree-{len(list(self.repo.glob('timeout-tree-*.toml')))}.toml"
        timeout_config.write_text(
            textwrap.dedent(
                f"""
                [explorer]
                cmd = {json.dumps(cmd_line)}
                writes = false
                timeout_seconds = {timeout_seconds}

                [coder]
                cmd = "{sys.executable} {FIXTURES / 'coder_agent.py'}"
                writes = true
                timeout_seconds = 60

                [code-reviewer]
                cmd = "{sys.executable} {FIXTURES / 'code_reviewer_agent.py'}"
                writes = false
                timeout_seconds = 60
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        run(["git", "add", str(timeout_config.relative_to(self.repo))], self.repo)
        run(["git", "commit", "-m", "add timeout tree config"], self.repo)
        return timeout_config

    def _write_timeout_tree_array_config(self, cmd: list[str], timeout_seconds: int = 1) -> Path:
        timeout_config = self.repo / f"timeout-tree-array-{len(list(self.repo.glob('timeout-tree-array-*.toml')))}.toml"
        cmd_items = ", ".join(json.dumps(part) for part in cmd)
        timeout_config.write_text(
            textwrap.dedent(
                f"""
                [explorer]
                cmd = [{cmd_items}]
                writes = false
                timeout_seconds = {timeout_seconds}

                [coder]
                cmd = "{sys.executable} {FIXTURES / 'coder_agent.py'}"
                writes = true
                timeout_seconds = 60

                [code-reviewer]
                cmd = "{sys.executable} {FIXTURES / 'code_reviewer_agent.py'}"
                writes = false
                timeout_seconds = 60
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        run(["git", "add", str(timeout_config.relative_to(self.repo))], self.repo)
        run(["git", "commit", "-m", "add timeout tree array config"], self.repo)
        return timeout_config

    def test_timeout_kills_string_command_child_process(self) -> None:
        parent_command = f"{sys.executable} -c {shlex.quote(self._timeout_parent_code())}"
        timeout_config = self._write_timeout_tree_config(parent_command)

        proc = run(self._loop_cmd(agent_config=timeout_config), self.repo)
        data = json.loads(proc.stdout)
        time.sleep(2.5)

        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["final_verdict"], "BLOCKED")
        self.assertEqual(data["stop_reason"], "TIMEOUT")
        self.assertFalse((self.repo / "late-after-timeout.txt").exists())

    def test_timeout_kills_array_command_child_process(self) -> None:
        timeout_config = self._write_timeout_tree_array_config([sys.executable, "-c", self._timeout_parent_code()])

        proc = run(self._loop_cmd(agent_config=timeout_config), self.repo)
        data = json.loads(proc.stdout)
        time.sleep(2.5)

        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["final_verdict"], "BLOCKED")
        self.assertEqual(data["stop_reason"], "TIMEOUT")
        self.assertFalse((self.repo / "late-after-timeout.txt").exists())

    def test_final_receipt_validator_rejects_fake_pass(self) -> None:
        fake = self.repo / "fake-receipt.json"
        fake.write_text(
            json.dumps(
                {
                    "schema": "loop.final_receipt.v1",
                    "run_id": "fake",
                    "objective": "fake",
                    "final_verdict": "PASS",
                    "stop_reason": "CODE_REVIEWER_PASS",
                    "attempts_used": 1,
                    "max_attempts": 3,
                    "allowed_globs": ["sample-target/src/time/**"],
                    "changed_files": ["sample-target/src/time/parse_duration.py"],
                    "checks": [{"command": "false", "returncode": 1}],
                    "reviewer": {"verdict": "PASS", "edited_files": False, "findings": []},
                    "artifacts": {"run_dir": ".loop/runs/fake", "final_diff": ".loop/runs/fake/attempts/01/diff.patch"},
                }
            ),
            encoding="utf-8",
        )
        proc = run([sys.executable, str(VALIDATOR), str(fake), "--print-summary"], self.repo)
        self.assertNotEqual(proc.returncode, 0)

    def test_final_receipt_validator_rejects_pass_without_checks(self) -> None:
        fake = self.repo / "fake-empty-checks-receipt.json"
        run_dir = self.repo / ".loop/runs/fake"
        (run_dir / "attempts/01").mkdir(parents=True)
        (run_dir / "attempts/01/diff.patch").write_text("", encoding="utf-8")
        fake.write_text(
            json.dumps(
                {
                    "schema": "loop.final_receipt.v1",
                    "run_id": "fake",
                    "objective": "fake",
                    "final_verdict": "PASS",
                    "stop_reason": "CODE_REVIEWER_PASS",
                    "attempts_used": 1,
                    "max_attempts": 3,
                    "allowed_globs": ["sample-target/src/time/**"],
                    "changed_files": ["sample-target/src/time/parse_duration.py"],
                    "checks": [],
                    "reviewer": {"verdict": "PASS", "edited_files": False, "findings": []},
                    "artifacts": {"run_dir": ".loop/runs/fake", "final_diff": ".loop/runs/fake/attempts/01/diff.patch"},
                }
            ),
            encoding="utf-8",
        )
        proc = run([sys.executable, str(VALIDATOR), str(fake), "--print-summary"], self.repo)
        self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
