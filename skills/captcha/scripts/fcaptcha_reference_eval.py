#!/usr/bin/env python3
"""Run pinned FCaptcha defensive reference tests and emit a receipt.

This script uses FCaptcha only as a local defensive reference fixture. It runs
upstream bot-detection and input-forensics tests from a pinned Git commit. It
does not solve CAPTCHA challenges, contact public CAPTCHA providers, use
stealth browsers, or send traffic to public targets.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


FCAPTCHA_REPO = "https://github.com/WebDecoy/FCaptcha.git"
FCAPTCHA_COMMIT = "dbe52eab975bb39161dd2a54d69924de51f63000"
TESTS = ["detection.test.js", "inputforensics.test.js"]


def run(command: list[str], *, cwd: Path | None = None, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"stdout={completed.stdout}\nstderr={completed.stderr}"
        )
    return completed


def clone_fcaptcha(dest: Path) -> str:
    run(["git", "clone", "--no-checkout", "--depth", "1", FCAPTCHA_REPO, str(dest)], timeout=120)
    run(["git", "fetch", "--depth", "1", "origin", FCAPTCHA_COMMIT], cwd=dest, timeout=120)
    run(["git", "checkout", "--detach", FCAPTCHA_COMMIT], cwd=dest, timeout=60)
    return run(["git", "rev-parse", "HEAD"], cwd=dest).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/tmp/captcha-fcaptcha-reference-eval.json"))
    args = parser.parse_args()

    if shutil.which("node") is None:
        raise RuntimeError("node executable is required for FCaptcha reference tests")

    tmp = Path(tempfile.mkdtemp(prefix="captcha-fcaptcha-reference-"))
    source_dir = tmp / "FCaptcha"
    source_commit = clone_fcaptcha(source_dir)
    server_node = source_dir / "server-node"

    tests: list[dict[str, Any]] = []
    for test_file in TESTS:
        completed = run(["node", test_file], cwd=server_node, timeout=60)
        stdout = completed.stdout
        tests.append(
            {
                "name": test_file,
                "exit_code": completed.returncode,
                "stdout_tail": stdout.strip().splitlines()[-8:],
                "passed_line": next((line for line in stdout.splitlines() if " passed" in line), ""),
            }
        )

    checks = {
        "source_commit_pinned": source_commit == FCAPTCHA_COMMIT,
        "detection_test_passed": any(
            item["name"] == "detection.test.js" and item["exit_code"] == 0 and "6/6 passed" in item["passed_line"]
            for item in tests
        ),
        "input_forensics_test_passed": any(
            item["name"] == "inputforensics.test.js" and item["exit_code"] == 0 and "17/17 passed" in item["passed_line"]
            for item in tests
        ),
    }
    errors = [name for name, ok in checks.items() if not ok]
    receipt = {
        "schema_version": "captcha.fcaptcha_reference_eval.v1",
        "success": not errors,
        "mocked": False,
        "live": True,
        "real_example": True,
        "local_source_tests": True,
        "local_loopback": False,
        "public_captcha_provider": False,
        "solver_or_bypass": False,
        "source_repo": FCAPTCHA_REPO,
        "source_commit": source_commit,
        "checks": checks,
        "errors": errors,
        "tests": tests,
        "proof_boundary": {
            "proves": "The captcha skill eval is grounded in a pinned real defensive CAPTCHA/bot-detection project with local detection and input-forensics tests.",
            "does_not_prove": "CAPTCHA solving, public-site bypass, provider behavior, browser stealth, or challenge success.",
        },
    }
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
