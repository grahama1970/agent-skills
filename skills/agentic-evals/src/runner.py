"""Run deterministic multi-trial command evaluations from JSON fixtures.

Inputs are versioned fixture files with cases, commands, expected exit codes,
and optional stdout/stderr containment checks. Outputs are JSON readiness
reports. Failures are represented in the report; invalid fixtures fail closed
with a non-zero CLI exit.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from statistics import mean
from typing import Any

import typer
from dotenv import load_dotenv
from loguru import logger

load_dotenv(override=False)

app = typer.Typer(no_args_is_help=True)

VALID_CASE_TYPES = {"positive", "negative", "adversarial"}
EVAL_FIXTURES = ("fixtures/agentic_eval.json", "fixtures/eval.json")
EVAL_PROVIDER_SKILLS = {"agentic-evals", "eval-skills"}
TRIAL_ENV_SCRUB_KEYS = ("UV_PROJECT_ENVIRONMENT", "VIRTUAL_ENV", "PYTHONPYCACHEPREFIX")


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
    _assert_not_slop(manifest, cases, trials)
    return manifest


_TRIVIAL_PROGRAMS = frozenset({"echo", "true", ":", "printf", "test", "[", "cat", "ls", "pwd", "head"})


def _command_text(command: list[str]) -> str:
    """Effective command text, unwrapping bash/sh -c so heuristics see the real work."""
    if len(command) >= 3 and command[0] in {"bash", "sh"} and command[1] == "-c":
        return command[2]
    return " ".join(command)


def _is_trivial(command: list[str]) -> bool:
    """A case that only echoes/returns a constant proves nothing — self-serving slop."""
    text = _command_text(command).strip()
    first = text.split()[0] if text.split() else ""
    if first in _TRIVIAL_PROGRAMS and not any(tok in text for tok in ("&&", "||", ";", "|", ".sh", ".py", "curl", "http")):
        return True
    return False


def _is_real_world(case: dict[str, Any]) -> bool:
    """A real-world case is explicitly flagged AND exercises a live path, not a stub.

    It must invoke a substantive program (a skill entrypoint, script, live HTTP,
    or test runner) and must NOT feed itself canned fixture/stub inputs, which
    would make it prove plumbing rather than real behavior.
    """
    if not case.get("real_world"):
        return False
    text = _command_text(case["command"])
    if "fixtures/" in text or "/fixtures/" in text:
        return False
    return any(marker in text for marker in ("run.sh", ".py", "curl", "http://", "https://", "pytest", "nightly", "e2e"))


def _is_non_deterministic(case: dict[str, Any]) -> bool:
    """A case that samples fresh inputs each run rather than a hard-coded key.

    Non-determinism is what makes an adversarial eval bite: a fixed-key case can
    be satisfied by overfitting to that one key, and it silently rots as the
    system moves. The markers below name the sampling explicitly so the runner
    can require it, not infer it.
    """
    text = _command_text(case["command"])
    # Explicit sampling markers only. A probe SCRIPT name is not enough --
    # "analyst_probe.py resolve CWE-999999" is a fixed key. Non-determinism
    # means the case draws fresh inputs each run: a --samples/--seed sweep or a
    # shell $RANDOM. (Caught by the gate on monitor-sparta, whose fixed-key
    # probe calls were wrongly counted as non-deterministic.)
    return "--samples" in text or "--seed" in text or "RANDOM" in text


def _compliance_tier_problems(manifest: dict[str, Any], cases: list[dict[str, Any]]) -> list[str]:
    """Enforce the compliance-grade eval contract when a fixture declares it.

    Ordinary skills keep the baseline gate (>=1 adversarial, >=1 real-world). A
    fixture that sets `eval_tier: "compliance"` is asserting it guards a
    compliance pipeline stage, and the runner then MANDATES what practice alone
    does not guarantee (operator directive 2026-08-12, "this is a compliance
    pipeline and must be robustly hardened"):

      - the majority of cases are adversarial/negative, not positive controls
      - at least one case is non-deterministic (samples fresh inputs per run)
      - every non-deterministic case names a per-run sample size of >= 50, so a
        stage's nightly coverage is hundreds-to-thousands of assertions, not a
        handful

    Declaring the tier and then failing to meet it is itself a slop failure:
    the mandate cannot be satisfied by removing the declaration quietly, because
    the compliance pipeline's own fixtures set it and their conformance tests
    read it back.
    """
    if manifest.get("eval_tier") != "compliance":
        return []
    problems: list[str] = []
    adversarial = [c for c in cases if c.get("type") in {"negative", "adversarial"}]
    if len(adversarial) * 2 <= len(cases):
        problems.append(
            f"eval_tier=compliance requires a strict MAJORITY of cases to be adversarial/negative "
            f"(more than half, not exactly half); got {len(adversarial)}/{len(cases)}"
        )
    nd = [c for c in cases if _is_non_deterministic(c)]
    if not nd:
        problems.append(
            "eval_tier=compliance requires at least one non-deterministic case "
            "(--samples/--seed/random probe); a fixed-key-only fixture cannot harden a pipeline"
        )
    for c in nd:
        text = _command_text(c["command"])
        import re as _re
        sizes = [int(n) for n in _re.findall(r"--samples\s+(\d+)", text)]
        if sizes and max(sizes) < 50:
            problems.append(
                f"eval_tier=compliance case {c['name']!r} samples only {max(sizes)}; "
                "compliance stages need >= 50 assertions per run (target ~1000/stage across modes)"
            )
    return problems


def _assert_not_slop(manifest: dict[str, Any], cases: list[dict[str, Any]], trials: int) -> None:
    """Fail-closed on self-serving slop fixtures.

    Prevents the failure mode where an eval passes trivially without proving the
    skill works: it requires repeatability, an adversarial/negative check, and at
    least one real-world case that exercises a live path without stub inputs.
    """
    # Narrow, explicit exemption: fixtures that test the runner itself or serve
    # as documentation examples are not skill evaluations. They must say so.
    # This is NEVER valid for a real skill's evaluation fixture.
    if manifest.get("eval_kind") in {"runner_selftest", "scaffold"}:
        return
    problems: list[str] = []
    if trials < 2:
        problems.append("trials must be >= 2 for repeatability (a single-trial eval is not evidence)")
    trivial = [c["name"] for c in cases if _is_trivial(c["command"])]
    if trivial:
        problems.append(f"trivial echo/constant cases prove nothing: {trivial}")
    if not any(c.get("type") in {"negative", "adversarial"} for c in cases):
        problems.append("no negative or adversarial case — an all-positive fixture is self-serving")
    if not any(_is_real_world(c) for c in cases):
        problems.append(
            "no real-world case: at least one case must set \"real_world\": true and exercise a live "
            "path (skill entrypoint / script / live HTTP / test runner) WITHOUT feeding itself "
            "fixtures/ stub inputs"
        )
    problems.extend(_compliance_tier_problems(manifest, cases))
    if problems:
        raise typer.BadParameter(
            "fixture rejected as low-value ('slop'): "
            + "; ".join(problems)
            + ". An agentic eval must prove real-world behavior, not deterministic plumbing."
        )


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


def _stream_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def trial_environment() -> dict[str, str]:
    """Return an environment for evaluated commands without runner venv leakage."""
    env = os.environ.copy()
    for key in TRIAL_ENV_SCRUB_KEYS:
        env.pop(key, None)
    return env


def run_trial(command: list[str], cwd: Path, timeout_seconds: float) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            cwd=cwd,
            env=trial_environment(),
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
            "stdout": _stream_text(exc.stdout),
            "stderr": _stream_text(exc.stderr),
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
        # A case may declare its own timeout (real-world cases that run a live
        # nightly need minutes, not the 30s default that fits unit-test cases).
        case_timeout = case.get("timeout_seconds", timeout_seconds)
        try:
            case_timeout = max(0.1, float(case_timeout))
        except (TypeError, ValueError):
            case_timeout = timeout_seconds
        results = [run_trial(case["command"], cwd, case_timeout) for _ in range(trials)]
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
        eval_findings = [finding for finding in skill_findings if finding.get("rule") in {"EVAL001", "EVAL002"}]
        eval001_findings = [finding for finding in eval_findings if finding.get("rule") == "EVAL001"]
        eval002_findings = [finding for finding in eval_findings if finding.get("rule") == "EVAL002"]
        recommended_action = recommended_action_for(
            skill_dir,
            posture,
            needs_fixture=bool(eval001_findings),
            needs_composition=bool(eval002_findings),
        )
        findings.extend(skill_findings)
        skill_reports.append(
            {
                "skill": skill_dir.name,
                "eval_posture": posture,
                "eval_required": bool(eval_findings),
                "needs_agentic_evals_composition": bool(eval002_findings),
                "recommended_action": recommended_action,
                "eval_findings": eval_findings,
            }
        )

    posture_counts: dict[str, int] = {}
    for item in skill_reports:
        posture = item["eval_posture"]
        posture_counts[posture] = posture_counts.get(posture, 0) + 1
    action_counts: dict[str, int] = {}
    for item in skill_reports:
        action = item["recommended_action"]
        action_counts[action] = action_counts.get(action, 0) + 1

    eval001 = [finding for finding in findings if finding.get("rule") == "EVAL001"]
    eval002 = [finding for finding in findings if finding.get("rule") == "EVAL002"]
    return {
        "schema": "agentic_evals.skill_posture_audit.v1",
        "mocked": False,
        "live": False,
        "proof_scope": "static repository eval posture audit",
        "claims": {
            "proves": "which top-level skills currently declare eval posture and compose agentic-evals",
            "does_not_prove": "per-skill semantic behavior, live service behavior, or fixture quality",
        },
        "skills_root": str(skills_root),
        "validator": str(validator),
        "summary": {
            "skills_checked": len(skills),
            "total_findings": len(findings),
            "eval001_count": len(eval001),
            "eval002_count": len(eval002),
            "posture_counts": posture_counts,
            "recommended_action_counts": action_counts,
            "eval001_skills": sorted({finding["skill"] for finding in eval001}),
            "eval002_skills": sorted({finding["skill"] for finding in eval002}),
        },
        "skills": skill_reports,
        "findings": findings,
    }


def recommended_action_for(
    skill_dir: Path,
    posture: str,
    needs_fixture: bool,
    needs_composition: bool,
) -> str:
    if not needs_fixture and not needs_composition:
        return "none"
    if needs_composition and not needs_fixture:
        return "compose_agentic_evals"
    if needs_composition and needs_fixture:
        if (skill_dir / "sanity.sh").exists() or (skill_dir / "run.sh").exists():
            return "compose_agentic_evals_and_scaffold_fixture"
        return "compose_agentic_evals_and_scaffold_static_validation_fixture"
    if posture != "missing":
        return "strengthen_existing_eval"
    if (skill_dir / "sanity.sh").exists() or (skill_dir / "run.sh").exists():
        return "scaffold_fixture"
    return "scaffold_static_validation_fixture"


def _entrypoint_command(fixture_dir: Path, entrypoint: Path, *args: str) -> list[str]:
    rel_entrypoint = os.path.relpath(entrypoint, start=fixture_dir)
    return ["bash", rel_entrypoint, *args]


def _validator_command(fixture_dir: Path, skill_dir: Path) -> list[str]:
    validator = skill_dir.parent / "best-practices-skills" / "scripts" / "validate_skill.py"
    rel_validator = os.path.relpath(validator, start=fixture_dir)
    rel_skill = os.path.relpath(skill_dir, start=fixture_dir)
    return ["python3", rel_validator, rel_skill, "--json"]


def scaffold_manifest(skill_dir: Path, fixture_dir: Path) -> dict[str, Any]:
    skill_name = skill_dir.name
    if (skill_dir / "sanity.sh").exists():
        case = {
            "name": "sanity",
            "type": "positive",
            "command": _entrypoint_command(fixture_dir, skill_dir / "sanity.sh"),
            "expected": {"exit_code": 0},
        }
    elif (skill_dir / "run.sh").exists():
        case = {
            "name": "run-help",
            "type": "positive",
            "command": _entrypoint_command(fixture_dir, skill_dir / "run.sh", "--help"),
            "expected": {"exit_code": 0},
        }
    else:
        case = {
            "name": "skill-contract-validation",
            "type": "positive",
            "command": _validator_command(fixture_dir, skill_dir),
            "expected": {"exit_code": 0},
        }

    entrypoint_backed = case["name"] in {"sanity", "run-help"}
    return {
        "version": 2,
        "skill": skill_name,
        "eval_kind": "scaffold",
        "trials": 3,
        "proof_scope": "fixture wiring smoke" if entrypoint_backed else "static skill contract validation",
        "claims": {
            "proves": (
                "the existing skill entrypoint exits with the expected status"
                if entrypoint_backed
                else "the skill contract can be parsed and checked by the best-practices-skills validator"
            ),
            "does_not_prove": "semantic correctness, live service behavior, or full skill readiness",
        },
        "cases": [case],
    }


def write_scaffold_fixture(skill_dir: Path, force: bool) -> dict[str, Any]:
    target = skill_dir / "fixtures" / "agentic_eval.json"
    if target.exists() and not force:
        return {
            "skill": skill_dir.name,
            "status": "skipped",
            "reason": "fixture_exists",
            "path": str(target),
        }
    manifest = scaffold_manifest(skill_dir.resolve(), target.resolve().parent)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {
        "skill": skill_dir.name,
        "status": "created",
        "path": str(target),
        "case": manifest["cases"][0]["name"],
        "proof_scope": manifest["proof_scope"],
    }


def apply_scaffolds_report(
    skills_root: Path,
    validator: Path,
    timeout_seconds: float,
    write: bool,
    force: bool,
    limit: int | None,
) -> dict[str, Any]:
    audit = audit_skills_report(skills_root, validator, timeout_seconds)
    eligible = [
        item
        for item in audit["skills"]
        if item["recommended_action"]
        in {
            "scaffold_fixture",
            "scaffold_static_validation_fixture",
            "compose_agentic_evals_and_scaffold_fixture",
            "compose_agentic_evals_and_scaffold_static_validation_fixture",
        }
    ]
    selected = eligible[:limit] if limit is not None else eligible
    results = []
    for item in selected:
        skill_dir = skills_root / item["skill"]
        if not write:
            results.append(
                {
                    "skill": item["skill"],
                    "status": "dry_run",
                    "path": str(skill_dir / "fixtures" / "agentic_eval.json"),
                }
            )
            continue
        try:
            results.append(write_scaffold_fixture(skill_dir, force))
        except Exception as exc:
            logger.error("failed to scaffold {}: {}", item["skill"], exc)
            results.append(
                {
                    "skill": item["skill"],
                    "status": "error",
                    "message": str(exc),
                }
            )

    status_counts: dict[str, int] = {}
    for result in results:
        status = result["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "schema": "agentic_evals.scaffold_apply_report.v1",
        "mocked": False,
        "live": False,
        "proof_scope": "fixture wiring scaffold application",
        "claims": {
            "proves": "which missing eval-posture skills had wiring fixtures created or would be created",
            "does_not_prove": "semantic correctness, fixture pass status, live service behavior, or release readiness",
        },
        "skills_root": str(skills_root),
        "write": write,
        "force": force,
        "limit": limit,
        "summary": {
            "eligible": len(eligible),
            "selected": len(selected),
            "created": status_counts.get("created", 0),
            "skipped": status_counts.get("skipped", 0),
            "dry_run": status_counts.get("dry_run", 0),
            "errors": status_counts.get("error", 0),
            "status_counts": status_counts,
        },
        "results": results,
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


@app.command("apply-scaffolds")
def apply_scaffolds(
    skills_root: Path = typer.Argument(..., exists=True, file_okay=False, readable=True),
    output: Path | None = typer.Option(None, "--output", "-o", help="Optional path for the JSON report."),
    validator: Path | None = typer.Option(None, "--validator", help="Path to validate_skill.py."),
    timeout_seconds: float = typer.Option(10.0, "--timeout-seconds", min=0.1),
    write: bool = typer.Option(False, "--write", help="Create missing fixtures. Default is dry-run."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing generated fixtures."),
    limit: int | None = typer.Option(None, "--limit", min=1, help="Maximum scaffoldable skills to process."),
) -> None:
    """Create first-pass fixtures for skills whose audit action is scaffold_fixture."""
    resolved_root = skills_root.resolve()
    resolved_validator = (
        validator.resolve()
        if validator is not None
        else (Path(__file__).resolve().parents[2] / "best-practices-skills" / "scripts" / "validate_skill.py")
    )
    report = apply_scaffolds_report(resolved_root, resolved_validator, timeout_seconds, write, force, limit)
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
    target = output or (skill_dir / "fixtures" / "agentic_eval.json")
    manifest = scaffold_manifest(skill_dir.resolve(), target.resolve().parent)
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
