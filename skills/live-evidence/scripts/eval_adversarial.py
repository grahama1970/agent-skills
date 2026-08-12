#!/usr/bin/env python3
"""Agentic-eval adversarial cases for Live Evidence.

The script creates a deliberately malformed skill contract in a temporary
directory, runs the production validator against it, and succeeds only when the
validator fails closed with the expected missing-composition finding.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


BAD_SKILL = """---
name: bad-live-evidence
description: >
  Deliberately incomplete Live Evidence fixture used to prove validator
  rejection paths.
triggers:
  - bad live evidence
provides:
  - live-transcription
composes:
  - memory
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-react
---

# Bad Live Evidence

This fixture is invalid because it omits the required agentic-evals composition.
"""


def main() -> int:
    """Run the validator against the malformed contract and check its failure."""

    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    validator = root / "scripts" / "verify_skill.py"
    with tempfile.TemporaryDirectory(prefix="live-evidence-adversarial-") as temp_name:
        temp = Path(temp_name)
        (temp / "src").mkdir()
        (temp / "SKILL.md").write_text(BAD_SKILL, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(validator), str(temp)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    combined = f"{result.stdout}\n{result.stderr}"
    if result.returncode == 0:
        print("validator accepted invalid skill", file=sys.stderr)
        return 1
    if "composes missing: ['agentic-evals']" not in combined:
        print("validator failed without expected missing-composition finding", file=sys.stderr)
        print(combined, file=sys.stderr)
        return 1
    print("invalid skill rejected: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
