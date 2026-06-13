from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
NODE_RUNNER = REPO_ROOT / "skills/loop/scripts/scillm_loop_node.py"
FIXTURES = REPO_ROOT / "skills/loop/tests/fixtures"


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(cmd, cwd=cwd, env=merged, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


class ScillmLoopNodeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        run(["git", "init"], self.repo)
        run(["git", "config", "user.email", "loop-node@example.test"], self.repo)
        run(["git", "config", "user.name", "Loop Node Test"], self.repo)
        self._write_initial_sample()
        self.config = self.repo / "agents.fixture.toml"
        self.config.write_text(
            textwrap.dedent(
                f"""
                [explorer]
                cmd = ["{sys.executable}", "{FIXTURES / 'explorer_agent.py'}"]
                writes = false
                timeout_seconds = 60

                [coder]
                cmd = ["{sys.executable}", "{FIXTURES / 'coder_agent.py'}"]
                writes = true
                timeout_seconds = 60

                [code-reviewer]
                cmd = ["{sys.executable}", "{FIXTURES / 'code_reviewer_agent.py'}"]
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
            "import unittest\n\n\nclass PlaceholderTests(unittest.TestCase):\n"
            "    def test_placeholder(self):\n        self.assertTrue(True)\n",
            encoding="utf-8",
        )

    def _write_node(self, **overrides: object) -> Path:
        data: dict[str, object] = {
            "node_id": "implement_parse_duration",
            "objective": "implement parse_duration",
            "agent_config": str(self.config),
            "allowed_globs": ["sample-target/src/time/**", "sample-target/tests/**"],
            "checks": [f"{sys.executable} -m unittest discover -s sample-target/tests"],
            "max_attempts": 3,
            "worktree": {"mode": "existing"},
        }
        data.update(overrides)
        path = self.repo / ".loop/node.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    def _run_node(self, node: Path, mode: str = "pass") -> tuple[subprocess.CompletedProcess[str], dict]:
        proc = run(
            [sys.executable, str(NODE_RUNNER), "--node", str(node), "--repo", str(self.repo), "--print-json"],
            self.repo,
            {"LOOP_FIXTURE_MODE": mode},
        )
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"node runner stdout was not JSON: {proc.stdout}\nstderr={proc.stderr}\nerror={exc}")
        return proc, data

    def test_node_runner_passes_with_valid_receipt(self) -> None:
        node = self._write_node(required_changed_globs=["sample-target/src/time/parse_duration.py"])

        proc, data = self._run_node(node)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(data["schema"], "loop.scillm_node_result.v1")
        self.assertEqual(data["node_id"], "implement_parse_duration")
        self.assertEqual(data["status"], "PASS")
        self.assertEqual(data["loop_final_verdict"], "PASS")
        self.assertTrue(data["receipt_valid"])
        self.assertTrue(data["required_changed_globs_satisfied"])
        self.assertIn("sample-target/src/time/parse_duration.py", data["changed_files"])
        self.assertTrue(Path(data["final_receipt"]).is_file())

    def test_node_runner_blocks_when_required_changed_glob_missing(self) -> None:
        node = self._write_node(required_changed_globs=["sample-target/src/time/__init__.py"])

        proc, data = self._run_node(node)

        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["status"], "BLOCKED")
        self.assertEqual(data["loop_final_verdict"], "PASS")
        self.assertEqual(data["stop_reason"], "REQUIRED_CHANGED_GLOB_MISSING")
        self.assertTrue(data["receipt_valid"])
        self.assertFalse(data["required_changed_globs_satisfied"])
        self.assertEqual(data["missing_required_changed_globs"], ["sample-target/src/time/__init__.py"])

    def test_node_runner_rejects_missing_required_node_fields(self) -> None:
        node = self.repo / ".loop/bad-node.json"
        node.parent.mkdir(parents=True, exist_ok=True)
        node.write_text(json.dumps({"node_id": "bad"}), encoding="utf-8")

        proc, data = self._run_node(node)

        self.assertEqual(proc.returncode, 2)
        self.assertEqual(data["status"], "BLOCKED")
        self.assertEqual(data["stop_reason"], "INFRASTRUCTURE_FAILURE")
        self.assertIn("node.objective", data["stderr"])


if __name__ == "__main__":
    unittest.main()
