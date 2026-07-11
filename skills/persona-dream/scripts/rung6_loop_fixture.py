#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LOOP = ROOT / "skills/loop/scripts/loop.py"
VALIDATE = ROOT / "skills/loop/scripts/validate_loop_receipt.py"
CONFIG = ROOT / "skills/loop/examples/agents.fixture.toml"


def run(cmd, cwd, env=None):
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True)


with tempfile.TemporaryDirectory() as d:
    repo = Path(d)
    run(["git", "init"], repo)
    run(["git", "config", "user.email", "loop@example.test"], repo)
    run(["git", "config", "user.name", "Loop Test"], repo)
    src = repo / "sample-target/src/time/parse_duration.py"
    test = repo / "sample-target/tests/test_parse_duration.py"
    src.parent.mkdir(parents=True)
    test.parent.mkdir(parents=True)
    src.write_text("def parse_duration(value: str) -> int:\n    raise NotImplementedError\n")
    test.write_text("import unittest\n\nclass T(unittest.TestCase):\n    def test_placeholder(self): self.assertTrue(True)\n")
    run(["git", "add", "."], repo)
    run(["git", "commit", "-m", "initial"], repo)

    proc = run(
        [
            sys.executable,
            str(LOOP),
            "--objective",
            "implement parse_duration",
            "--agent-config",
            str(CONFIG),
            "--allow",
            "sample-target/src/time/**",
            "--allow",
            "sample-target/tests/**",
            "--check",
            f"{sys.executable} -m unittest discover -s sample-target/tests",
            "--max-attempts",
            "3",
            "--print-json",
        ],
        repo,
        env={"PATH": __import__("os").environ["PATH"], "LOOP_FIXTURE_MODE": "pass"},
    )
    data = json.loads(proc.stdout)
    receipt = repo / data["artifacts"]["run_dir"] / "final-receipt.json"
    valid = run([sys.executable, str(VALIDATE), str(receipt), "--print-summary"], repo)
    ok = proc.returncode == 0 and data["final_verdict"] == "PASS" and valid.returncode == 0
    print(json.dumps({"rung": 6, "loop": True, "verdict": data["final_verdict"], "receipt_valid": valid.returncode == 0, "ok": ok}))
    raise SystemExit(0 if ok else 1)
