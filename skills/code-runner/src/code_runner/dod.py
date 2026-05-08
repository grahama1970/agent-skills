"""Definition-of-Done execution for code-runner.

Commands run in the target worktree and produce structured evidence. Green
status is based on explicit exit-code/assertion checks, never absence of errors.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path


class DodResult:
    """Structured DoD command result."""

    def __init__(self, command: str, assertion: str, exit_code: int, stdout: str, stderr: str, passed: bool) -> None:
        self.command = command
        self.assertion = assertion
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.passed = passed
        self.score = 1.0 if passed else 0.49

    def to_dict(self) -> dict[str, object]:
        """Return JSON-safe evidence."""

        return {
            "command": self.command,
            "assertion": self.assertion,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "dod_passed": self.passed,
            "score": self.score,
        }


def assertion_passed(assertion: str, stdout: str, stderr: str, exit_code: int) -> bool:
    """Evaluate supported DoD assertion forms."""

    text = f"{stdout}\n{stderr}"
    stripped = assertion.strip()
    if stripped in {"", "exit_code == 0"}:
        return exit_code == 0
    if stripped == "exit_code != 0":
        return exit_code != 0
    match = re.fullmatch(r"exit_code\s*==\s*(-?\d+)", stripped)
    if match:
        return exit_code == int(match.group(1))
    match = re.fullmatch(r"exit_code\s*!=\s*(-?\d+)", stripped)
    if match:
        return exit_code != int(match.group(1))
    if stripped.startswith("contains:"):
        return exit_code == 0 and stripped.split(":", 1)[1] in text
    if stripped.startswith("stdout_regex:"):
        return exit_code == 0 and re.search(stripped.split(":", 1)[1], stdout, re.MULTILINE) is not None
    if stripped.startswith("stderr_regex:"):
        return exit_code == 0 and re.search(stripped.split(":", 1)[1], stderr, re.MULTILINE) is not None
    if stripped.startswith("json_has_keys:"):
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return False
        keys = [key.strip() for key in stripped.split(":", 1)[1].split(",") if key.strip()]
        return exit_code == 0 and all(key in data for key in keys)
    return exit_code == 0 and stripped.lower() in text.lower()


def run_dod(cwd: str | Path, command: str, assertion: str, timeout: int = 120) -> DodResult:
    """Run the DoD command and evaluate the assertion."""

    try:
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        proc = subprocess.run(
            ["bash", "-lc", command],
            cwd=Path(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
            env=env,
        )
        stdout = proc.stdout
        stderr = proc.stderr
        exit_code = proc.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = f"DoD timed out after {timeout}s"
        exit_code = 124
    passed = assertion_passed(assertion, stdout, stderr, exit_code)
    return DodResult(command, assertion, exit_code, stdout, stderr, passed)
