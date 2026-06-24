from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
RUNNER = SKILL_DIR / "run.sh"


class InterfaceDesignTest(unittest.TestCase):
    def test_init_validate_and_ready_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            brief = root / "brief.md"
            brief.write_text("# Test\nA chat-first operator interface.\n", encoding="utf-8")
            run_dir = root / "run"
            subprocess.run(
                [
                    str(RUNNER), "init", "--brief", str(brief),
                    "--surface", "test-chat",
                    "--target-repo", "/tmp/test-target",
                    "--output", str(run_dir),
                    "--mockup-lanes", "one,two",
                    "--implementation-lanes", "reuse-first,accessibility-first",
                ],
                check=True, capture_output=True, text=True,
            )
            validation = subprocess.run(
                [str(RUNNER), "validate", "--run", str(run_dir)],
                check=True, capture_output=True, text=True,
            )
            self.assertTrue(json.loads(validation.stdout)["ok"])
            subprocess.run(
                [
                    str(RUNNER), "record", "--run", str(run_dir),
                    "--node", "brief.normalize", "--state", "PASS",
                ],
                check=True, capture_output=True, text=True,
            )
            status = subprocess.run(
                [str(RUNNER), "status", "--run", str(run_dir)],
                check=True, capture_output=True, text=True,
            )
            ready = set(json.loads(status.stdout)["ready_nodes"])
            self.assertEqual(ready, {"research.github", "research.brave"})


if __name__ == "__main__":
    unittest.main()
