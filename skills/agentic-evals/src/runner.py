"""Run deterministic multi-trial command evaluations from JSON fixtures.

Inputs are versioned fixture files with cases, commands, expected exit codes,
and optional stdout/stderr containment checks. Outputs are JSON readiness
reports. Failures are represented in the report; invalid fixtures fail closed
with a non-zero CLI exit.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from statistics import mean
from typing import Any

import typer
from loguru import logger

app = typer.Typer(no_args_is_help=True)

VALID_CASE_TYPES = {"positive", "negative", "adversarial"}
EVAL_FIXTURES = ("fixtures/agentic_eval.json", "fixtures/eval.json")
EVAL_PROVIDER_SKILLS = {"agentic-evals", "eval-skills"}


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
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(part, str) for part in command)
    ):
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


def classify_eval_posture(skill_dir: Path) -> str:
    skill_md = skill_dir / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8", errors="ignore") if skill_md.exists() else ""
    if skill_dir.name in EVAL_PROVIDER_SKILLS:
        return "eval_provider"
    if (skill_dir / "fixtures" / "agentic_eval.json").exists():
        return "agentic_fixture"
    if (skill_dir / "fixtures" / "eval.json").exists():
        return "legacy_eval_fixture"
    if "agentic-evals" in text or "eval-skills" in text:
        return "delegates_to_eval_skill"
    if "eval_not_required" in text:
        return "eval_not_required"
    return "missing"


def run_validator(skill_dir: Path, skills_root: Path, validator: Path, timeout_seconds: float) -> list[dict[str, Any]]:
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(validator),
                str(skill_dir),
                "--json",
                "--skills-root",
                str(skills_root),
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        logger.error("validator timed out for {}: {}", skill_dir.name, exc)
        return [
            {
                "rule": "VALIDATOR_TIMEOUT",
                "severity": "error",
                "skill": skill_dir.name,
                "message": f"validator exceeded {timeout_seconds} seconds",
            }
        ]
    if result.returncode != 0:
        return [
            {
                "rule": "VALIDATOR_RUNNER",
                "severity": "error",
                "skill": skill_dir.name,
                "message": result.stderr.strip() or result.stdout.strip() or "validator failed",
            }
        ]
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        logger.error("validator returned invalid JSON for {}: {}", skill_dir.name, exc)
        return [
            {
                "rule": "VALIDATOR_JSON",
                "severity": "error",
                "skill": skill_dir.name,
                "message": "validator returned invalid JSON",
            }
        ]
    return parsed if isinstance(parsed, list) else []


def audit_skills_report(skills_root: Path, validator: Path, timeout_seconds: float) -> dict[str, Any]:
    skills = sorted(path for path in skills_root.iterdir() if (path / "SKILL.md").exists())
    skill_reports = []
    findings: list[dict[str, Any]] = []
    for skill_dir in skills:
        posture = classify_eval_posture(skill_dir)
        skill_findings = run_validator(skill_dir, skills_root, validator, timeout_seconds)
        eval_findings = [finding for finding in skill_findings if finding.get("rule") == "EVAL001"]
        findings.extend(skill_findings)
        skill_reports.append(
            {
                "skill": skill_dir.name,
                "eval_posture": posture,
                "eval_required": bool(eval_findings),
                "eval_findings": eval_findings,
            }
        )

    posture_counts: dict[str, int] = {}
    for item in skill_reports:
        posture = item["eval_posture"]
        posture_counts[posture] = posture_counts.get(posture, 0) + 1

    eval001 = [finding for finding in findings if finding.get("rule") == "EVAL001"]
    return {
        "schema": "agentic_evals.skill_posture_audit.v1",
        "mocked": False,
        "live": False,
        "proof_scope": "static repository eval posture audit",
        "claims": {
            "proves": "which top-level skills currently declare an eval posture or emit EVAL001",
            "does_not_prove": "per-skill semantic behavior, live service behavior, or fixture quality",
        },
        "skills_root": str(skills_root),
        "validator": str(validator),
        "summary": {
            "skills_checked": len(skills),
            "total_findings": len(findings),
            "eval001_count": len(eval001),
            "posture_counts": posture_counts,
            "eval001_skills": sorted({finding["skill"] for finding in eval001}),
        },
        "skills": skill_reports,
        "findings": findings,
    }


def scaffold_manifest(skill_dir: Path) -> dict[str, Any]:
    skill_name = skill_dir.name
    if (skill_dir / "sanity.sh").exists():
        case = {
            "name": "sanity",
            "type": "positive",
            "command": ["bash", "../sanity.sh"],
            "expected": {"exit_code": 0},
        }
    elif (skill_dir / "run.sh").exists():
        case = {
            "name": "run-help",
            "type": "positive",
            "command": ["bash", "../run.sh", "--help"],
            "expected": {"exit_code": 0},
        }
    else:
        raise typer.BadParameter("skill needs sanity.sh or run.sh to scaffold a fixture")

    return {
        "version": 2,
        "skill": skill_name,
        "trials": 3,
        "proof_scope": "fixture wiring smoke",
        "claims": {
            "proves": "the existing skill entrypoint exits with the expected status",
            "does_not_prove": "semantic correctness, live service behavior, or full skill readiness",
        },
        "cases": [case],
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


@app.command("scaffold-fixture")
def scaffold_fixture(
    skill_dir: Path = typer.Argument(..., exists=True, file_okay=False, readable=True),
    output: Path | None = typer.Option(None, "--output", "-o", help="Path for the generated fixture."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing fixture."),
) -> None:
    """Create a first-pass agentic eval fixture from a skill entrypoint."""
    manifest = scaffold_manifest(skill_dir.resolve())
    target = output or (skill_dir / "fixtures" / "agentic_eval.json")
    if target.exists() and not force:
        raise typer.BadParameter(f"{target} already exists; pass --force to overwrite")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2) + "\n"
    target.write_text(payload, encoding="utf-8")
    typer.echo(payload)


@app.command("audit-skills")
def audit_skills(
    skills_root: Path = typer.Argument(..., exists=True, file_okay=False, readable=True),
    output: Path | None = typer.Option(None, "--output", "-o", help="Optional path for the JSON report."),
    validator: Path | None = typer.Option(None, "--validator", help="Path to validate_skill.py."),
    timeout_seconds: float = typer.Option(10.0, "--timeout-seconds", min=0.1),
) -> None:
    """Audit top-level skills for an explicit agentic eval posture."""
    resolved_root = skills_root.resolve()
    resolved_validator = (
        validator.resolve()
        if validator is not None
        else (Path(__file__).resolve().parents[2] / "best-practices-skills" / "scripts" / "validate_skill.py")
    )
    report = audit_skills_report(resolved_root, resolved_validator, timeout_seconds)
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
