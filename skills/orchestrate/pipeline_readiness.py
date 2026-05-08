#!/usr/bin/env python3
"""Portable readiness checks for the /plan -> /code-runner pipeline."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

REQUIRED_PATHS = [
    "skills/plan/plan.py",
    "skills/plan/sanity.sh",
    "skills/plan/tests/test_code_runner_contract_validation.py",
    "skills/review-plan/review_plan.py",
    "skills/review-plan/sanity.sh",
    "skills/review-plan/tests/test_code_runner_contract_fail_closed.py",
    "skills/orchestrate/run.sh",
    "skills/orchestrate/structured_execute.py",
    "skills/orchestrate/tests/test_orchestrate.sh",
    "skills/orchestrate/tests/run_plan_review_orchestrate_code_runner_mock_e2e.sh",
    "skills/code-runner/run.sh",
    "skills/code-runner/src/code_runner",
]

CI_JOB_MARKERS = [
    "plan-review-orchestrate-pipeline",
    "plan-review-orchestrate-complete-task-soak",
    "orchestrate-live-scillm-smoke",
    "code-runner-adversarial",
    "code-runner-soak",
]

GATE_COMMANDS = [
    {
        "name": "plan_sanity",
        "cwd": "skills/plan",
        "command": ["bash", "sanity.sh"],
    },
    {
        "name": "plan_code_runner_contract_tests",
        "cwd": "skills/plan",
        "command": ["uv", "run", "--project", ".", "python", "tests/test_code_runner_contract_validation.py"],
    },
    {
        "name": "review_plan_sanity",
        "cwd": "skills/review-plan",
        "command": ["bash", "sanity.sh"],
    },
    {
        "name": "review_plan_code_runner_contract_tests",
        "cwd": "skills/review-plan",
        "command": ["uv", "run", "--project", ".", "python", "tests/test_code_runner_contract_fail_closed.py"],
    },
    {
        "name": "orchestrate_context_boundary_tests",
        "cwd": "skills/orchestrate",
        "command": [
            "uv",
            "run",
            "--project",
            ".",
            "--with",
            "pytest",
            "python",
            "-m",
            "pytest",
            "-q",
            "tests/test_code_runner_context_boundary.py",
        ],
    },
    {
        "name": "orchestrate_pipeline_gate",
        "cwd": "skills/orchestrate",
        "command": ["bash", "tests/test_orchestrate.sh"],
    },
]


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


def run_command(command: list[str], cwd: Path, timeout: int = 240) -> tuple[int, str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    proc = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout[-4000:]


def check_required_paths(root: Path) -> list[Check]:
    checks: list[Check] = []
    for rel in REQUIRED_PATHS:
        path = root / rel
        checks.append(Check(f"path:{rel}", "PASS" if path.exists() else "FAIL", str(path)))
    return checks


def check_tools() -> list[Check]:
    checks: list[Check] = []
    for tool in ("bash", "git", "python3", "uv"):
        found = shutil.which(tool)
        checks.append(Check(f"tool:{tool}", "PASS" if found else "FAIL", found or "missing"))
    return checks


def check_git(root: Path, require_clean: bool) -> list[Check]:
    checks: list[Check] = []
    rc, out = run_command(["git", "rev-parse", "--show-toplevel"], root, timeout=30)
    checks.append(Check("git:repository", "PASS" if rc == 0 else "FAIL", out.strip()))
    if rc != 0:
        return checks

    rc, out = run_command(["git", "status", "--porcelain"], root, timeout=30)
    if rc != 0:
        checks.append(Check("git:status", "FAIL", out.strip()))
        return checks
    dirty_count = len([line for line in out.splitlines() if line.strip()])
    status = "FAIL" if require_clean and dirty_count else "WARN" if dirty_count else "PASS"
    checks.append(Check("git:dirty_worktree", status, f"{dirty_count} dirty entries"))

    rc, out = run_command(["git", "worktree", "list", "--porcelain"], root, timeout=30)
    checks.append(Check("git:worktree_list", "PASS" if rc == 0 else "FAIL", out.strip()[:500]))
    return checks


def check_ci_workflow(root: Path) -> list[Check]:
    workflow = root / ".github/workflows/skills-ci.yml"
    if not workflow.exists():
        return [Check("ci:skills-ci.yml", "FAIL", str(workflow))]
    text = workflow.read_text(encoding="utf-8")
    checks = [Check("ci:skills-ci.yml", "PASS", str(workflow))]
    for marker in CI_JOB_MARKERS:
        checks.append(Check(f"ci:{marker}", "PASS" if marker in text else "FAIL", marker))
    return checks


def run_gates(root: Path, include_code_runner: bool) -> list[Check]:
    checks: list[Check] = []
    for gate in GATE_COMMANDS:
        rc, out = run_command(gate["command"], root / gate["cwd"], timeout=600)
        checks.append(Check(f"gate:{gate['name']}", "PASS" if rc == 0 else "FAIL", out.strip()))
    if include_code_runner:
        rc, out = run_command(
            [
                "uv",
                "run",
                "--project",
                ".",
                "--with",
                "pytest",
                "python",
                "-m",
                "pytest",
                "-q",
                "tests/adversarial",
                "-m",
                "not soak",
            ],
            root / "skills/code-runner",
            timeout=900,
        )
        checks.append(Check("gate:code_runner_adversarial_non_soak", "PASS" if rc == 0 else "FAIL", out.strip()))
    return checks


def summarize(checks: list[Check]) -> str:
    if any(check.status == "FAIL" for check in checks):
        return "FAIL"
    if any(check.status == "WARN" for check in checks):
        return "WARN"
    return "PASS"


def print_text(result: dict[str, Any]) -> None:
    print(f"plan-to-code-runner readiness: {result['status']}")
    for check in result["checks"]:
        detail = f" - {check['detail']}" if check["detail"] else ""
        print(f"[{check['status']}] {check['name']}{detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--profile", choices=("quick", "gates"), default="quick")
    parser.add_argument("--include-code-runner", action="store_true")
    parser.add_argument("--require-clean", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = args.repo_root.resolve()
    checks: list[Check] = []
    checks.extend(check_required_paths(root))
    checks.extend(check_tools())
    checks.extend(check_git(root, args.require_clean))
    checks.extend(check_ci_workflow(root))
    if args.profile == "gates":
        checks.extend(run_gates(root, args.include_code_runner))

    result = {
        "status": summarize(checks),
        "repo_root": str(root),
        "profile": args.profile,
        "checks": [check.as_dict() for check in checks],
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print_text(result)
    return 1 if result["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
