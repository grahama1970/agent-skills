"""Run deterministic multi-trial command evaluations from JSON fixtures.

Inputs are versioned fixture files with cases, commands, expected exit codes,
and optional stdout/stderr containment checks. Outputs are JSON readiness
reports. Failures are represented in the report; invalid fixtures fail closed
with a non-zero CLI exit.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from statistics import mean
from typing import Any

import typer

app = typer.Typer(no_args_is_help=True)

VALID_CASE_TYPES = {"positive", "negative", "adversarial"}


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("version") != 2:
        raise typer.BadParameter("fixture version must be 2")
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        raise typer.BadParameter("fixture must contain a cases list")
    trials = manifest.get("trials", 3)
    if not isinstance(trials, int) or trials < 1:
        raise typer.BadParameter("trials must be a positive integer")
    for case in cases:
        validate_case(case)
    return manifest


def validate_case(case: dict[str, Any]) -> None:
    if not isinstance(case.get("name"), str) or not case["name"]:
        raise typer.BadParameter("each case needs a non-empty name")
    if case.get("type") not in VALID_CASE_TYPES:
        raise typer.BadParameter(f"case {case['name']} has invalid type")
    command = case.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(part, str) for part in command):
        raise typer.BadParameter(f"case {case['name']} command must be a non-empty argv list")
    expected = case.get("expected")
    if not isinstance(expected, dict) or not isinstance(expected.get("exit_code"), int):
        raise typer.BadParameter(f"case {case['name']} expected.exit_code must be an integer")


def run_trial(command: list[str], cwd: Path, timeout_seconds: float) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            cwd=cwd,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "exit_code": None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
            "timed_out": True,
        }


def trial_passed(case: dict[str, Any], trial: dict[str, Any]) -> bool:
    expected = case["expected"]
    if trial["exit_code"] != expected["exit_code"]:
        return False
    for needle in expected.get("stdout_contains", []):
        if needle not in trial["stdout"]:
            return False
    for needle in expected.get("stderr_contains", []):
        if needle not in trial["stderr"]:
            return False
    return not trial["timed_out"]


def readiness_for(case_reports: list[dict[str, Any]]) -> str:
    if not case_reports:
        return "NOT_ESTABLISHED"
    fully_passed = [case["pass_rate"] == 1.0 for case in case_reports]
    any_passed = any(case["passed_trials"] > 0 for case in case_reports)
    if all(fully_passed):
        return "READY"
    if any_passed:
        return "USABLE_WITH_GAPS"
    return "NOT_READY"


def evaluate_manifest(path: Path, timeout_seconds: float) -> dict[str, Any]:
    manifest = load_manifest(path)
    trials = manifest.get("trials", 3)
    cwd = path.parent
    cases = []
    for case in manifest["cases"]:
        results = [run_trial(case["command"], cwd, timeout_seconds) for _ in range(trials)]
        passed = [trial_passed(case, result) for result in results]
        passed_trials = sum(passed)
        cases.append(
            {
                "name": case["name"],
                "type": case["type"],
                "passed_trials": passed_trials,
                "total_trials": trials,
                "pass_rate": round(passed_trials / trials, 4),
                "avg_latency_ms": round(mean(result["duration_ms"] for result in results), 3),
                "trials": results,
            }
        )
    return {
        "schema": "agentic_evals.report.v1",
        "source": str(path),
        "mocked": False,
        "fixture_backed": True,
        "live": False,
        "proof_scope": "fixture wiring smoke",
        "claims": {
            "proves": "declared local commands met explicit fixture expectations across repeated trials",
            "does_not_prove": "semantic correctness, live services, LLM judge behavior, or release readiness",
        },
        "what_was_exercised": "local commands declared in the fixture manifest",
        "what_remains_unverified": "semantic correctness, live services, LLM judge behavior, and release readiness",
        "readiness": readiness_for(cases),
        "case_count": len(cases),
        "trial_count": sum(case["total_trials"] for case in cases),
        "cases": cases,
    }


@app.command("run")
def run(
    manifest: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    output: Path | None = typer.Option(None, "--output", "-o", help="Optional path for the JSON report."),
    timeout_seconds: float = typer.Option(30.0, "--timeout-seconds", min=0.1),
) -> None:
    """Run an agentic evaluation manifest."""
    report = evaluate_manifest(manifest, timeout_seconds)
    payload = json.dumps(report, indent=2)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload + "\n", encoding="utf-8")
    typer.echo(payload)


@app.command("schema")
def schema() -> None:
    """Print the report schema identifier."""
    typer.echo("agentic_evals.report.v1")


if __name__ == "__main__":
    app()
