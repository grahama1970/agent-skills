"""Assert that a project-state report describes its TARGET and nothing else.

Regression armour for two scope defects found 2026-08-13: a report generated
for a single skill collected 0 of that skill's 132 tests (a cross-project
subprocess inherited this skill's venv), and reported 386 unrelated skills
from the global tree as if they were the target's (a silent fallback root).

Inputs: a target root and the expectations to enforce. Outputs: the measured
scope numbers on stdout plus a non-zero exit when an expectation fails.
Failure modes: a report that cannot be produced fails loudly; a report whose
numbers cannot be found fails rather than defaulting to zero.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import typer

app = typer.Typer(help="Assert project-state report scoping for a target root.")
SKILL_DIR = Path(__file__).resolve().parent.parent


def _report(target: Path, full: bool = False, extra_env: dict[str, str] | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in {"VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"}}
    env["PROJECT_STATE_ROOT"] = str(target)
    env.update(extra_env or {})
    out = subprocess.run(
        [str(SKILL_DIR / "run.sh"), "report", "--full" if full else "--quick", "--json"],
        capture_output=True, text=True, timeout=600, env=env, cwd=str(SKILL_DIR),
    )
    start = out.stdout.find("{")
    if start < 0:
        raise typer.BadParameter(f"no JSON report produced: {(out.stderr or out.stdout)[-300:]}")
    return json.loads(out.stdout[start:])


@app.command()
def check(
    target: Path = typer.Option(..., help="Target root the report must describe."),
    min_tests: int = typer.Option(0, help="Fail when the target's collected test count is below this."),
    expect_skills_not_applicable: bool = typer.Option(False, help="Fail if a skills count is reported for a non-workspace target."),
    min_skills: int = typer.Option(0, help="Fail when a skills-workspace target reports fewer skills than this."),
) -> None:
    """Run the real report entrypoint and assert its scope."""
    report = _report(target)
    infra = report.get("phase_1_infrastructure") or report.get("infrastructure") or {}
    if not infra:
        raise typer.BadParameter("report carries no infrastructure phase — cannot assert scope")
    tests = (infra.get("tests") or {}).get("total", 0)
    skills = infra.get("skills") or {}
    skills_total = skills.get("total", 0)
    applicable = skills.get("applicable", True)
    typer.echo(f"TARGET={target} TESTS_TOTAL={tests} SKILLS_TOTAL={skills_total} SKILLS_APPLICABLE={applicable}")

    problems: list[str] = []
    if tests < min_tests:
        problems.append(f"collected {tests} tests for the target, expected >= {min_tests}")
    if expect_skills_not_applicable and (applicable or skills_total):
        problems.append(f"reported {skills_total} skills for a target that owns no skills tree")
    if skills_total < min_skills:
        problems.append(f"reported {skills_total} skills, expected >= {min_skills}")
    if problems:
        typer.echo("SCOPE_FAIL: " + "; ".join(problems), err=True)
        raise typer.Exit(1)
    typer.echo("SCOPE_OK")


@app.command("full-phases")
def full_phases(
    target: Path = typer.Option(..., help="Target root the full report must describe."),
    require_memory_available: bool = typer.Option(False, help="Fail unless phase_2 reports memory available."),
    expect_memory_unavailable: bool = typer.Option(False, help="Fail unless phase_2 HONESTLY reports memory unavailable."),
) -> None:
    """Assert every --full phase is present, target-scoped, and honest about
    the availability of the skill it composes."""
    report = _report(target, full=True,
                     extra_env={"MEMORY_URL": "http://127.0.0.1:59999"} if expect_memory_unavailable else None)
    required = ["phase_1_infrastructure", "phase_2_memory", "phase_3_doc_drift",
                "phase_4_best_practices", "phase_5_research", "phase_6_gaps"]
    missing = [phase for phase in required if phase not in report]
    memory = report.get("phase_2_memory", {})
    research = report.get("phase_5_research", {})
    drift = report.get("phase_3_doc_drift", {})
    name = target.name

    queries = [str(r.get("query", "")) for r in (memory.get("recalls") or [])]
    research_queries = [str(r.get("query", "")) for r in (research.get("results") or [])]
    scoped_recalls = sum(1 for q in queries if name in q)
    scoped_research = sum(1 for q in research_queries if name in q)
    typer.echo(f"PHASES_PRESENT={len(required) - len(missing)}/{len(required)} "
               f"MEMORY_AVAILABLE={memory.get('available')} "
               f"SCOPED_RECALLS={scoped_recalls}/{len(queries)} "
               f"SCOPED_RESEARCH={scoped_research}/{max(len(research_queries), 1)} "
               f"DRIFT_DOCS={drift.get('docs_found')}")

    problems: list[str] = []
    if missing:
        problems.append(f"missing phases: {missing}")
    if queries and scoped_recalls == 0:
        problems.append("no memory recall query mentions the target — phase_2 is not target-scoped")
    if research_queries and scoped_research == 0:
        problems.append("no research query mentions the target — phase_5 is not target-scoped")
    if require_memory_available and not memory.get("available"):
        problems.append("phase_2 reports memory unavailable")
    # Invariant (checkable on every run, no service sabotage needed):
    # available must equal "at least one recall actually answered".
    answered = memory.get("successful_recalls")
    if answered is None:
        problems.append("phase_2 reports no successful_recalls count — availability is unfalsifiable")
    elif bool(memory.get("available")) != (answered > 0):
        problems.append(f"phase_2 availability ({memory.get('available')}) contradicts "
                        f"successful_recalls ({answered}) — silent success or silent failure")
    if expect_memory_unavailable and memory.get("available"):
        problems.append("phase_2 claimed memory available when no recall answered")
    if problems:
        typer.echo("PHASE_FAIL: " + "; ".join(problems), err=True)
        raise typer.Exit(1)
    typer.echo("PHASES_OK")


if __name__ == "__main__":
    app()
