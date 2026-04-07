#!/usr/bin/env python3
"""
Behavioral evaluation runner for Embry OS skills.

Loads fixtures/eval.json from each skill, executes test cases via run.sh,
validates exit codes, stdout contents, JSON schemas, and latency budgets.
Produces structured results for reporting.
"""

import os
import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

try:
    import jsonschema
except ImportError:
    jsonschema = None

app = typer.Typer(help="Behavioral skill evaluation via fixtures")

EVAL_MANIFEST = "fixtures/eval.json"
BASELINES_FILE = ".eval-baselines.json"


# ── Data Models ──────────────────────────────────────────────────────


@dataclass
class CaseResult:
    """Result of a single eval case."""

    name: str
    passed: bool
    duration_ms: float
    exit_code: int
    expected_exit_code: int
    stdout: str
    stderr: str
    latency_budget_ms: Optional[float] = None
    baseline_ms: Optional[float] = None
    failures: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "duration_ms": round(self.duration_ms, 1),
            "exit_code": self.exit_code,
            "expected_exit_code": self.expected_exit_code,
            "latency_budget_ms": self.latency_budget_ms,
            "baseline_ms": self.baseline_ms,
            "failures": self.failures,
            "tags": self.tags,
        }


@dataclass
class SkillEvalReport:
    """Eval results for one skill."""

    skill: str
    passed: bool
    cases: list[CaseResult] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""

    @property
    def pass_count(self) -> int:
        return sum(1 for c in self.cases if c.passed)

    @property
    def fail_count(self) -> int:
        return sum(1 for c in self.cases if not c.passed)

    def to_dict(self) -> dict:
        return {
            "skill": self.skill,
            "passed": self.passed,
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "cases": [c.to_dict() for c in self.cases],
        }


@dataclass
class EvalReport:
    """Top-level eval report across all skills."""

    skills: list[SkillEvalReport] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(s.passed for s in self.skills if not s.skipped)

    @property
    def total_cases(self) -> int:
        return sum(len(s.cases) for s in self.skills)

    @property
    def total_passed(self) -> int:
        return sum(s.pass_count for s in self.skills)

    @property
    def evaluated_count(self) -> int:
        return sum(1 for s in self.skills if not s.skipped)

    @property
    def skipped_count(self) -> int:
        return sum(1 for s in self.skills if s.skipped)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "total_cases": self.total_cases,
            "total_passed": self.total_passed,
            "evaluated_skills": self.evaluated_count,
            "skipped_skills": self.skipped_count,
            "skills": [s.to_dict() for s in self.skills],
        }


# ── Manifest Loading ─────────────────────────────────────────────────


def load_eval_manifest(skill_dir: Path) -> Optional[dict]:
    """Load and validate fixtures/eval.json from a skill directory."""
    manifest_path = skill_dir / EVAL_MANIFEST
    if not manifest_path.exists():
        return None

    try:
        manifest = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Invalid eval manifest {}: {}", manifest_path, exc)
        return None

    if manifest.get("version") != 1:
        logger.warning("Unsupported eval manifest version in {}", manifest_path)
        return None

    if "cases" not in manifest or not isinstance(manifest["cases"], list):
        logger.warning("No cases array in {}", manifest_path)
        return None

    return manifest


# ── Case Execution ───────────────────────────────────────────────────


def _resolve_input(skill_dir: Path, case: dict) -> Optional[str]:
    """Resolve input text from inline or file reference."""
    if "input_inline" in case:
        return case["input_inline"]
    if "input_file" in case:
        input_path = skill_dir / "fixtures" / "inputs" / case["input_file"]
        if input_path.exists():
            return input_path.read_text()
        logger.warning("Input file not found: {}", input_path)
        return None
    return None


def _build_command(skill_dir: Path, case: dict, input_text: Optional[str]) -> list[str]:
    """Build the subprocess command for a case."""
    run_sh = skill_dir / "run.sh"
    cmd = [str(run_sh)]

    for arg in case.get("command", []):
        if arg == "{input}" and input_text is not None:
            cmd.append(input_text)
        else:
            cmd.append(arg)

    return cmd


def run_eval_case(
    skill_dir: Path,
    case: dict,
    defaults: dict,
) -> CaseResult:
    """Execute one eval case and validate results."""
    name = case.get("name", "unnamed")
    tags = case.get("tags", [])
    expected_exit = case.get("expected_exit_code", 0)
    latency_budget = case.get("latency_budget_ms", defaults.get("latency_budget_ms"))

    input_text = _resolve_input(skill_dir, case)
    cmd = _build_command(skill_dir, case, input_text)

    timeout_s = max((latency_budget or 30000) * 3, 30000) / 1000

    logger.debug("Running case '{}': {}", name, " ".join(cmd))

    failures: list[str] = []
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=str(skill_dir),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        duration_ms = (time.monotonic() - start) * 1000
        exit_code = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr
    except subprocess.TimeoutExpired:
        duration_ms = (time.monotonic() - start) * 1000
        failures.append(f"Timed out after {timeout_s:.0f}s")
        return CaseResult(
            name=name,
            passed=False,
            duration_ms=duration_ms,
            exit_code=-1,
            expected_exit_code=expected_exit,
            stdout="",
            stderr="TIMEOUT",
            latency_budget_ms=latency_budget,
            failures=failures,
            tags=tags,
        )
    except OSError as exc:
        failures.append(f"Failed to execute: {exc}")
        return CaseResult(
            name=name,
            passed=False,
            duration_ms=0,
            exit_code=-1,
            expected_exit_code=expected_exit,
            stdout="",
            stderr=str(exc),
            latency_budget_ms=latency_budget,
            failures=failures,
            tags=tags,
        )

    # Validate exit code
    if exit_code != expected_exit:
        failures.append(
            f"Exit code {exit_code} (expected {expected_exit})"
        )

    # Validate stdout contains
    failures.extend(check_stdout_contains(stdout, case.get("expected_stdout_contains", [])))

    # Validate stdout excludes
    failures.extend(check_stdout_excludes(stdout, case.get("expected_stdout_excludes", [])))

    # Validate JSON schema
    schema = case.get("expected_output_schema")
    if schema:
        failures.extend(validate_json_schema(stdout, schema))

    # Validate against golden output
    expected_file = case.get("expected_output_file")
    if expected_file:
        expected_path = skill_dir / "fixtures" / "expected" / expected_file
        failures.extend(diff_against_expected(stdout, expected_path))

    # Check latency budget
    if latency_budget and duration_ms > latency_budget:
        failures.append(
            f"Latency {duration_ms:.0f}ms exceeds budget {latency_budget:.0f}ms"
        )

    return CaseResult(
        name=name,
        passed=len(failures) == 0,
        duration_ms=duration_ms,
        exit_code=exit_code,
        expected_exit_code=expected_exit,
        stdout=stdout,
        stderr=stderr,
        latency_budget_ms=latency_budget,
        failures=failures,
        tags=tags,
    )


# ── Validators ───────────────────────────────────────────────────────


def check_stdout_contains(stdout: str, patterns: list[str]) -> list[str]:
    """Check that stdout contains all expected substrings."""
    failures = []
    for pattern in patterns:
        if pattern not in stdout:
            failures.append(f"Missing in stdout: {pattern!r}")
    return failures


def check_stdout_excludes(stdout: str, patterns: list[str]) -> list[str]:
    """Check that stdout does not contain any excluded substrings."""
    failures = []
    for pattern in patterns:
        if pattern in stdout:
            failures.append(f"Unexpected in stdout: {pattern!r}")
    return failures


def validate_json_schema(stdout: str, schema: dict) -> list[str]:
    """Validate stdout as JSON against a JSON Schema."""
    if jsonschema is None:
        return ["jsonschema not installed — schema validation skipped"]

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return [f"stdout is not valid JSON: {exc}"]

    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as exc:
        return [f"Schema validation failed: {exc.message}"]

    return []


def diff_against_expected(stdout: str, expected_path: Path) -> list[str]:
    """Compare stdout against a golden output file."""
    if not expected_path.exists():
        return [f"Expected output file not found: {expected_path}"]

    expected = expected_path.read_text()
    if stdout.strip() == expected.strip():
        return []

    # Produce a simple diff summary
    stdout_lines = stdout.strip().splitlines()
    expected_lines = expected.strip().splitlines()

    diffs = []
    max_lines = max(len(stdout_lines), len(expected_lines))
    shown = 0
    for i in range(max_lines):
        if shown >= 10:
            diffs.append(f"  ... ({max_lines - i} more lines differ)")
            break
        actual = stdout_lines[i] if i < len(stdout_lines) else "<missing>"
        exp = expected_lines[i] if i < len(expected_lines) else "<missing>"
        if actual != exp:
            diffs.append(f"  - {exp}")
            diffs.append(f"  + {actual}")
            shown += 1

    return [f"Diff vs {expected_path.name}:\n" + "\n".join(diffs)]


# ── Compose Chains ───────────────────────────────────────────────────


def run_compose_chain(
    skills_root: Path,
    chain_def: dict,
) -> CaseResult:
    """Run a multi-skill compose chain, piping stdout between steps."""
    name = chain_def.get("name", "unnamed-chain")
    steps = chain_def.get("steps", [])
    chain_skills = chain_def.get("chain", [])
    pipe_stdout = chain_def.get("pipe_stdout", True)
    latency_budget = chain_def.get("latency_budget_ms")
    tags = chain_def.get("tags", [])

    if not steps:
        return CaseResult(
            name=name, passed=False, duration_ms=0, exit_code=-1,
            expected_exit_code=0, stdout="", stderr="",
            failures=["No steps defined in chain"], tags=tags,
        )

    failures: list[str] = []
    last_stdout = ""
    total_ms = 0

    for i, step in enumerate(steps):
        skill_name = chain_skills[i] if i < len(chain_skills) else None
        if not skill_name:
            failures.append(f"Step {i}: no skill name in chain list")
            break

        skill_dir = skills_root / skill_name
        if not skill_dir.exists():
            failures.append(f"Step {i}: skill {skill_name!r} not found")
            break

        run_sh = skill_dir / "run.sh"
        cmd = [str(run_sh)] + step.get("command", [])

        stdin_data = last_stdout if pipe_stdout and i > 0 else None

        start = time.monotonic()
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=30, cwd=str(skill_dir),
                input=stdin_data,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            step_ms = (time.monotonic() - start) * 1000
            total_ms += step_ms

            if proc.returncode != 0:
                failures.append(
                    f"Step {i} ({skill_name}): exit code {proc.returncode}"
                )
                failures.append(f"  stderr: {proc.stderr[:500]}")
                break

            last_stdout = proc.stdout

        except subprocess.TimeoutExpired:
            step_ms = (time.monotonic() - start) * 1000
            total_ms += step_ms
            failures.append(f"Step {i} ({skill_name}): timed out")
            break

    if latency_budget and total_ms > latency_budget:
        failures.append(
            f"Chain latency {total_ms:.0f}ms exceeds budget {latency_budget:.0f}ms"
        )

    return CaseResult(
        name=name,
        passed=len(failures) == 0,
        duration_ms=total_ms,
        exit_code=0 if not failures else 1,
        expected_exit_code=0,
        stdout=last_stdout,
        stderr="",
        latency_budget_ms=latency_budget,
        failures=failures,
        tags=tags,
    )


# ── Skill-Level Evaluation ───────────────────────────────────────────


def eval_skill(
    skill_dir: Path,
    skills_root: Path,
    tag_filter: Optional[set[str]] = None,
) -> SkillEvalReport:
    """Run all eval cases for a single skill."""
    skill_name = skill_dir.name
    manifest = load_eval_manifest(skill_dir)

    if manifest is None:
        return SkillEvalReport(
            skill=skill_name, passed=True, skipped=True,
            skip_reason="No fixtures/eval.json",
        )

    run_sh = skill_dir / "run.sh"
    if not run_sh.exists():
        return SkillEvalReport(
            skill=skill_name, passed=False, skipped=True,
            skip_reason="No run.sh found",
        )

    defaults = manifest.get("defaults", {})
    cases = manifest.get("cases", [])
    chains = manifest.get("compose_chains", [])
    results: list[CaseResult] = []

    # Run individual cases
    for case in cases:
        case_tags = set(case.get("tags", []))
        if tag_filter and not case_tags.intersection(tag_filter):
            continue
        result = run_eval_case(skill_dir, case, defaults)
        results.append(result)
        status = "PASS" if result.passed else "FAIL"
        logger.info(
            "  {} {} ({:.0f}ms)", status, result.name, result.duration_ms
        )

    # Run compose chains
    for chain in chains:
        chain_tags = set(chain.get("tags", []))
        if tag_filter and not chain_tags.intersection(tag_filter):
            continue
        result = run_compose_chain(skills_root, chain)
        results.append(result)
        status = "PASS" if result.passed else "FAIL"
        logger.info(
            "  {} chain:{} ({:.0f}ms)", status, result.name, result.duration_ms
        )

    all_passed = all(r.passed for r in results)
    return SkillEvalReport(skill=skill_name, passed=all_passed, cases=results)


# ── Top-Level Orchestrator ───────────────────────────────────────────


def eval_all(
    root: Path,
    skill_filter: Optional[set[str]] = None,
    tag_filter: Optional[set[str]] = None,
) -> EvalReport:
    """Evaluate all skills under root that have eval fixtures."""
    report = EvalReport()

    skill_dirs = sorted(
        d for d in root.iterdir()
        if d.is_dir() and not d.name.startswith((".", "_"))
    )

    for skill_dir in skill_dirs:
        if skill_filter and skill_dir.name not in skill_filter:
            continue

        logger.info("Evaluating: {}", skill_dir.name)
        skill_report = eval_skill(skill_dir, root, tag_filter)
        report.skills.append(skill_report)

        if skill_report.skipped:
            logger.debug("  Skipped: {}", skill_report.skip_reason)
        elif skill_report.passed:
            logger.info(
                "  PASS ({}/{})", skill_report.pass_count, len(skill_report.cases)
            )
        else:
            logger.warning(
                "  FAIL ({}/{})", skill_report.pass_count, len(skill_report.cases)
            )

    return report


# ── Latency Baselines ────────────────────────────────────────────────


def load_baselines(root: Path) -> dict:
    """Load latency baselines from .eval-baselines.json."""
    path = root / BASELINES_FILE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_latency_baselines(root: Path, report: EvalReport) -> None:
    """Update latency baselines using EMA: new = 0.7 * old + 0.3 * current."""
    baselines = load_baselines(root)

    for skill_report in report.skills:
        if skill_report.skipped:
            continue
        for case in skill_report.cases:
            if not case.passed:
                continue
            key = f"{skill_report.skill}/{case.name}"
            old = baselines.get(key, case.duration_ms)
            baselines[key] = round(0.7 * old + 0.3 * case.duration_ms, 1)

    path = root / BASELINES_FILE
    path.write_text(json.dumps(baselines, indent=2, sort_keys=True) + "\n")
    logger.info("Updated latency baselines: {}", path)


def apply_baselines(report: EvalReport, baselines: dict) -> None:
    """Attach baseline_ms to each case result."""
    for skill_report in report.skills:
        for case in skill_report.cases:
            key = f"{skill_report.skill}/{case.name}"
            case.baseline_ms = baselines.get(key)


def detect_latency_regressions(
    report: EvalReport,
    baselines: dict,
    threshold: float = 1.5,
) -> list[str]:
    """Flag cases >threshold times slower than baseline."""
    regressions = []
    for skill_report in report.skills:
        for case in skill_report.cases:
            key = f"{skill_report.skill}/{case.name}"
            baseline = baselines.get(key)
            if baseline and baseline > 0 and case.duration_ms > baseline * threshold:
                pct = ((case.duration_ms / baseline) - 1) * 100
                regressions.append(
                    f"{key}: {case.duration_ms:.0f}ms vs baseline "
                    f"{baseline:.0f}ms (+{pct:.0f}%)"
                )
    return regressions


# ── Violation Bridge ─────────────────────────────────────────────────


def case_result_to_violations(skill: str, result: CaseResult) -> list[dict]:
    """Convert a failed case result to skills-ci compatible violation dicts."""
    if result.passed:
        return []
    return [
        {
            "rule": "eval.case_failure",
            "severity": "error",
            "skill": skill,
            "path": f"fixtures/eval.json#{result.name}",
            "message": failure,
            "fixable": False,
            "applied": False,
        }
        for failure in result.failures
    ]


# ── CLI ──────────────────────────────────────────────────────────────


@app.command()
def eval(
    skill: Optional[str] = typer.Option(
        None, "--skill", "-s",
        help="Comma-separated skill names to evaluate",
    ),
    tags: Optional[str] = typer.Option(
        None, "--tags", "-t",
        help="Comma-separated tags to filter cases",
    ),
    report_json: Optional[str] = typer.Option(
        None, "--report-json",
        help="Write JSON report to this path",
    ),
    report_md: Optional[str] = typer.Option(
        None, "--report-md",
        help="Write Markdown report to this path",
    ),
    update_baselines: bool = typer.Option(
        False, "--update-baselines",
        help="Update latency baselines after eval",
    ),
) -> None:
    """Run behavioral evaluation on skills with fixtures/eval.json."""
    from eval_reporting import format_markdown_report

    script_dir = Path(__file__).parent
    skills_root = script_dir.parent

    skill_filter = set(skill.split(",")) if skill else None
    tag_filter = set(tags.split(",")) if tags else None

    # Load baselines
    baselines = load_baselines(skills_root)

    # Run evaluation
    report = eval_all(skills_root, skill_filter, tag_filter)

    # Attach baselines to results
    apply_baselines(report, baselines)

    # Detect regressions
    regressions = detect_latency_regressions(report, baselines)
    if regressions:
        logger.warning("Latency regressions detected:")
        for r in regressions:
            logger.warning("  {}", r)

    # Summary
    evaluated = [s for s in report.skills if not s.skipped]
    logger.info(
        "Eval complete: {}/{} skills passed, {} skipped, {}/{} cases passed",
        sum(1 for s in evaluated if s.passed),
        len(evaluated),
        report.skipped_count,
        report.total_passed,
        report.total_cases,
    )

    # Write reports
    if report_json:
        Path(report_json).write_text(
            json.dumps(report.to_dict(), indent=2) + "\n"
        )
        logger.info("JSON report: {}", report_json)

    if report_md:
        md = format_markdown_report(report, regressions)
        Path(report_md).write_text(md)
        logger.info("Markdown report: {}", report_md)

    # Update baselines
    if update_baselines:
        save_latency_baselines(skills_root, report)

    # Exit code
    if not report.passed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
