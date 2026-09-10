"""Run issue #1631 focused deterministic proof and persist a JSON result."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    test_paths = [
        "skills/agentic-evals/tests/test_execution_provenance.py",
        "skills/agentic-evals/tests/test_remediation.py",
        "skills/agentic-evals/tests/test_compliance_tier_gate.py",
        "skills/agentic-evals/tests/test_journeys.py",
    ]
    cmd = ["uv", "run", "--project", "skills/agentic-evals", "pytest", "-q", *test_paths]
    result = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=120, check=False)
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    payload: dict[str, Any] = {
        "schema": "agentic_evals.issue1631.deterministic_pytest_result.v1",
        "mocked": False,
        "live": False,
        "command": cmd,
        "returncode": result.returncode,
        "passed": result.returncode == 0,
        "covered_tests": test_paths,
        "required_behaviors": [
            "mode-schema",
            "frozen-hash",
            "mutation-detection",
            "protected-surface",
            "external-adapter",
            "requalification",
            "fail-before-fix-non-vacuity",
        ],
        "stdout_tail": stdout[-4000:],
        "stderr_tail": stderr[-4000:],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if payload["passed"] else 1)


if __name__ == "__main__":
    main()
