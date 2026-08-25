from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
RUN = SKILL_DIR / "run.sh"


class DagTemplatesTest(unittest.TestCase):
    def run_cmd(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(RUN), *args], cwd=SKILL_DIR, text=True, capture_output=True)

    def test_find_returns_immutable_goal_loop(self) -> None:
        result = self.run_cmd("find", "anti thrash immutable goal mvp", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema"], "dag_template_search.v1")
        self.assertEqual(payload["matches"][0]["id"], "immutable-goal-mvp-loop")
        self.assertEqual(payload["matches"][0]["template_dir"], "templates/immutable-goal-mvp-loop")

    def test_validate_registry_requires_template_artifacts(self) -> None:
        result = self.run_cmd("validate-registry", "--json")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["problems"], [])

    def test_materialize_customizes_and_preserves_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "custom.tau.dag.json"
            result = self.run_cmd(
                "materialize",
                "immutable-goal-mvp-loop",
                "--set",
                "dag_id=custom-loop",
                "--set",
                "goal_id=custom-goal",
                "--set",
                "goal_hash=sha256:2222222222222222222222222222222222222222222222222222222222222222",
                "--set",
                "immutable_goal=Deliver a custom MVP with receipts",
                "--set",
                "target_repo=local/custom",
                "--set",
                "target=issue-1",
                "--output",
                str(out),
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            doc = json.loads(out.read_text())
            self.assertEqual(doc["dag_id"], "custom-loop")
            self.assertEqual(doc["goal"]["immutable_goal"], "Deliver a custom MVP with receipts")
            self.assertEqual(doc["_template"]["source_id"], "immutable-goal-mvp-loop")
            self.assertTrue(doc["_template"]["customized"])

    def test_show_exposes_prompt_chart_eval_and_readme_paths(self) -> None:
        result = self.run_cmd("show", "immutable-goal-mvp-loop", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["template_dir"], "templates/immutable-goal-mvp-loop")
        self.assertEqual(payload["dag_path"], "templates/immutable-goal-mvp-loop/dag.tau.dag.json")
        self.assertEqual(payload["ask_prompt_path"], "templates/immutable-goal-mvp-loop/ask-prompt.md")
        self.assertEqual(payload["chart_path"], "templates/immutable-goal-mvp-loop/phart-dag-chart.txt")
        self.assertEqual(payload["eval_path"], "templates/immutable-goal-mvp-loop/agentic_eval.json")
        self.assertEqual(payload["readme_path"], "templates/immutable-goal-mvp-loop/README.md")

    def test_unknown_slot_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "bad.tau.dag.json"
            result = self.run_cmd(
                "materialize",
                "immutable-goal-mvp-loop",
                "--set",
                "unknown=value",
                "--output",
                str(out),
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unknown slot", result.stderr)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
