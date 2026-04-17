"""
Persona quality management: diagnose, validate, improve, simulacrum, audit.
"""
import json
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from loguru import logger as log

from .cli_app import app, console

from .persona import (
    Persona,
    get_persona,
    list_personas,
    create_persona,
    run_skill,
)
from .quality import (
    diagnose_persona,
    validate_persona,
    validate_simulacrum,
    validate_and_improve_batch,
    improve_persona,
    audit_personas,
    ValidationTest,
)

# =============================================================================
# Diagnose Command
# =============================================================================

@app.command()
def diagnose(
    name: str = typer.Argument(..., help="Persona name"),
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Memory scope"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Diagnose a persona's quality and identify gaps.

    Checks completeness, connectivity, bridges, and freshness.
    Outputs a quality score and list of actionable gaps.

    Example:
        ./run.sh diagnose "Hayao Miyazaki"
    """
    # Search multiple scopes if not specified
    scopes_to_search = [scope] if scope else ["personas", "behavioral", "clients"]

    result = None
    for s in scopes_to_search:
        result = diagnose_persona(name, s)
        if result.completeness > 0 or not result.gaps or "not found" not in str(result.gaps):
            break

    if not result or (result.gaps and "not found" in str(result.gaps)):
        console.print(f"[red]Persona '{name}' not found[/red]")
        raise typer.Exit(1)

    if as_json:
        console.print(json.dumps(result.to_dict(), indent=2))
        return

    # Rich output
    console.print(f"\n[bold]Diagnosis: {result.name}[/bold]")
    console.print(f"  Scope: {result.scope}")
    console.print()

    # Score bars
    console.print("[bold]Quality Scores:[/bold]")
    for metric, score in [
        ("Completeness", result.completeness),
        ("Connectivity", result.connectivity),
        ("Accuracy", result.accuracy),
        ("Freshness", result.freshness),
    ]:
        bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
        color = "green" if score >= 0.7 else "yellow" if score >= 0.4 else "red"
        console.print(f"  {metric:12} [{bar}] [{color}]{score:.1f}[/{color}]")

    console.print()
    console.print(f"  [bold]Overall: {result.overall_score:.2f} (Grade: {result.grade})[/bold]")

    # Details
    console.print()
    console.print("[bold]Details:[/bold]")
    console.print(f"  Sources: {result.sources_count}")
    console.print(f"  QRA pairs: {result.qra_count}")
    console.print(f"  Colleagues: {result.colleague_count}")
    console.print(f"  Bridges: {result.bridge_count}")
    console.print(f"  Days since update: {result.days_since_update}")

    # Gaps
    if result.gaps:
        console.print()
        console.print("[bold red]Gaps Identified:[/bold red]")
        for gap in result.gaps:
            console.print(f"  [red]•[/red] {gap}")

        console.print()
        console.print("[dim]Run: ./run.sh improve \"{}\" to fix gaps[/dim]".format(name))
    else:
        console.print()
        console.print("[green]No gaps identified - persona is healthy![/green]")


# =============================================================================
# Validate Command
# =============================================================================

@app.command()
def validate(
    name: str = typer.Argument(..., help="Persona name"),
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Memory scope"),
    question: Optional[str] = typer.Option(None, "--question", "-q", help="Test question"),
    expected: Optional[str] = typer.Option(None, "--expected", "-e", help="Expected content (comma-separated)"),
    ground_truth: Optional[Path] = typer.Option(None, "--ground-truth", "-g", help="YAML/JSON file with tests"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Validate a persona by testing Q&A responses.

    Tests persona knowledge against expected answers.

    Examples:
        ./run.sh validate "Hayao Miyazaki" --question "What is Nausicaä about?" --expected "environmental,princess"
        ./run.sh validate "Hayao Miyazaki" --ground-truth tests/miyazaki.yaml
    """
    scope = scope or "personas"

    # Build tests
    tests = None
    if question:
        expected_list = [e.strip() for e in expected.split(",")] if expected else []
        tests = [ValidationTest(question=question, expected_contains=expected_list)]

    result = validate_persona(
        name=name,
        scope=scope,
        tests=tests,
        ground_truth_file=ground_truth,
    )

    if as_json:
        console.print(json.dumps(result.to_dict(), indent=2))
        return

    # Rich output
    console.print(f"\n[bold]Validation: {result.name}[/bold]")
    console.print(f"  Scope: {result.scope}")
    console.print()

    # Overall grade
    color = "green" if result.grade in ("A", "B") else "yellow" if result.grade == "C" else "red"
    console.print(f"  [bold]Grade: [{color}]{result.grade}[/{color}] ({result.overall_score:.2f})[/bold]")
    console.print()

    # Test results
    if result.test_details:
        console.print("[bold]Test Results:[/bold]")
        for i, test in enumerate(result.test_details, 1):
            status = "[green]✓[/green]" if test["passed"] else "[red]✗[/red]"
            console.print(f"  {status} {test['question'][:60]}...")

            if test["failures"]:
                for failure in test["failures"]:
                    console.print(f"      [red]{failure}[/red]")

        console.print()
        console.print(f"  Passed: {result.tests_passed}/{result.tests_passed + result.tests_failed}")
    else:
        console.print("[dim]No tests run. Use --question or --ground-truth[/dim]")

    # Gaps
    if result.gaps:
        console.print()
        console.print("[bold]Gaps:[/bold]")
        for gap in result.gaps[:5]:
            console.print(f"  [yellow]•[/yellow] {gap}")


# =============================================================================
# Improve Command
# =============================================================================

@app.command()
def improve(
    name: str = typer.Argument(..., help="Persona name"),
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Memory scope"),
    threshold: float = typer.Option(0.7, "--threshold", "-t", help="Quality threshold (0.0-1.0)"),
    max_iterations: int = typer.Option(3, "--max-iterations", "-m", help="Max improvement iterations"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview actions without executing"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Iteratively improve a persona until quality threshold is met.

    Runs improvement actions in a convergence loop:
    - Re-run /dogpile for missing sources
    - Discover books if none
    - Ingest YouTube if none
    - Enrich colleague graph

    Examples:
        ./run.sh improve "Hayao Miyazaki" --threshold 0.8
        ./run.sh improve "Hayao Miyazaki" --dry-run
    """
    scope = scope or "personas"

    console.print(f"\n[bold]Improving: {name}[/bold]")
    console.print(f"  Target quality: {threshold}")
    console.print(f"  Max iterations: {max_iterations}")
    if dry_run:
        console.print("  [dim][dry-run mode][/dim]")
    console.print()

    result = improve_persona(
        name=name,
        scope=scope,
        quality_threshold=threshold,
        max_iterations=max_iterations,
        dry_run=dry_run,
    )

    if as_json:
        console.print(json.dumps(result.to_dict(), indent=2))
        return

    # Actions taken
    console.print("[bold]Actions:[/bold]")
    for action in result.actions_taken:
        console.print(f"  • {action}")

    console.print()

    # Score improvement
    improvement = result.final_score - result.initial_score
    improvement_color = "green" if improvement > 0 else "yellow" if improvement == 0 else "red"

    console.print(f"  Initial score: {result.initial_score:.2f}")
    console.print(f"  Final score: {result.final_score:.2f}")
    console.print(f"  Improvement: [{improvement_color}]{improvement:+.2f}[/{improvement_color}]")
    console.print(f"  Iterations: {result.iterations}")

    if result.converged:
        console.print(f"\n[green]✓ Converged at quality {result.final_score:.2f}[/green]")
    else:
        console.print(f"\n[yellow]Did not converge. Run again or adjust threshold.[/yellow]")


# =============================================================================
# Simulacrum Command (Deep Validation)
# =============================================================================

@app.command()
def simulacrum(
    name: str = typer.Argument(..., help="Persona name"),
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Memory scope"),
    probes: Optional[str] = typer.Option(
        "philosophy,technique,motivation",
        "--probes", "-p",
        help="Probe types (comma-separated: philosophy,technique,motivation,criticism,hypothetical)"
    ),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Deep simulacrum validation - test if persona can REASON like the real person.

    Unlike basic validation, this asks philosophy and reasoning questions,
    not trivia. A persona is not complete until it passes simulacrum tests.

    Examples:
        ./run.sh simulacrum "Hayao Miyazaki"
        ./run.sh simulacrum "Hayao Miyazaki" --probes "philosophy,criticism"
    """
    scope = scope or "personas"
    probe_types = [p.strip() for p in probes.split(",")]

    console.print(f"\n[bold]Simulacrum Validation: {name}[/bold]")
    console.print(f"  Probes: {', '.join(probe_types)}")
    console.print()

    result = validate_simulacrum(name, scope, probe_types)

    if as_json:
        console.print(json.dumps(result.to_dict(), indent=2))
        return

    # Grade
    color = "green" if result.grade in ("A", "B") else "yellow" if result.grade == "C" else "red"
    console.print(f"  [bold]Grade: [{color}]{result.grade}[/{color}] (Accuracy: {result.accuracy:.2f})[/bold]")
    console.print()

    # Test results
    console.print("[bold]Simulacrum Probes:[/bold]")
    for test in result.test_details:
        status = "[green]✓[/green]" if test["passed"] else "[red]✗[/red]"
        question = test["question"][:70] + "..." if len(test["question"]) > 70 else test["question"]
        console.print(f"  {status} {question}")

        # Show quality notes
        for note in test.get("quality_notes", []):
            console.print(f"      [dim]{note}[/dim]")

        # Show failures
        for failure in test.get("failures", []):
            console.print(f"      [red]{failure}[/red]")

    console.print()
    console.print(f"  Passed: {result.tests_passed}/{result.tests_passed + result.tests_failed}")

    if result.accuracy < 0.7:
        console.print()
        console.print("[yellow]Persona is NOT a valid simulacrum yet.[/yellow]")
        console.print("[dim]Run: ./run.sh simulacrum-improve \"{}\" to enhance[/dim]".format(name))


# =============================================================================
# Simulacrum Improve Command (Batch with Convergence)
# =============================================================================

@app.command("simulacrum-improve")
def simulacrum_improve(
    name: Optional[str] = typer.Argument(None, help="Persona name (omit for all)"),
    scope: Optional[str] = typer.Option("personas", "--scope", "-s", help="Memory scope"),
    threshold: float = typer.Option(0.7, "--threshold", "-t", help="Pass threshold (0.0-1.0)"),
    max_iterations: int = typer.Option(3, "--max-iterations", "-m", help="Max iterations per persona"),
    probes: Optional[str] = typer.Option(
        "philosophy,technique,motivation",
        "--probes", "-p",
        help="Probe types"
    ),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Max personas to process"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without changes"),
    resume: bool = typer.Option(False, "--resume", help="Resume from checkpoint"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Iterative simulacrum improvement loop.

    For each persona that fails simulacrum validation:
    1. Identify knowledge gaps (philosophy, reasoning, technique)
    2. Run targeted improvements (deep dogpile, YouTube lectures, books)
    3. Re-validate until passing or max iterations

    A persona is NOT complete until it passes simulacrum tests.

    Examples:
        # Improve single persona
        ./run.sh simulacrum-improve "Hayao Miyazaki"

        # Improve all failing personas in scope
        ./run.sh simulacrum-improve --scope personas --threshold 0.7

        # Dry run to see what would happen
        ./run.sh simulacrum-improve --scope personas --dry-run
    """
    from pathlib import Path

    probe_types = [p.strip() for p in probes.split(",")]

    checkpoint_file = None
    if resume:
        checkpoint_file = Path(f".simulacrum_checkpoint_{scope}.json")

    if name:
        # Single persona improvement
        console.print(f"\n[bold]Simulacrum Improvement: {name}[/bold]")
        console.print(f"  Threshold: {threshold}")
        console.print(f"  Max iterations: {max_iterations}")
        if dry_run:
            console.print("  [dim](dry-run mode)[/dim]")
        console.print()

        # Run single improvement
        from .quality import improve_persona
        result = improve_persona(
            name=name,
            scope=scope,
            quality_threshold=threshold,
            max_iterations=max_iterations,
            dry_run=dry_run,
        )

        if as_json:
            console.print(json.dumps(result.to_dict(), indent=2))
            return

        # Show result
        for action in result.actions_taken:
            console.print(f"  • {action}")

        console.print()
        improvement = result.final_score - result.initial_score
        color = "green" if improvement > 0 else "yellow"
        console.print(f"  Initial: {result.initial_score:.2f} → Final: {result.final_score:.2f} ([{color}]{improvement:+.2f}[/{color}])")

        if result.converged:
            console.print(f"\n[green]✓ Persona is now a valid simulacrum![/green]")
        else:
            console.print(f"\n[yellow]Did not converge. May need more source material.[/yellow]")

    else:
        # Batch improvement
        console.print(f"\n[bold]Batch Simulacrum Improvement[/bold]")
        console.print(f"  Scope: {scope}")
        console.print(f"  Threshold: {threshold}")
        console.print(f"  Max iterations per persona: {max_iterations}")
        if limit:
            console.print(f"  Limit: {limit} personas")
        if dry_run:
            console.print("  [dim](dry-run mode)[/dim]")
        if resume and checkpoint_file and checkpoint_file.exists():
            console.print("  [dim](resuming from checkpoint)[/dim]")
        console.print()

        result = validate_and_improve_batch(
            scope=scope,
            convergence_threshold=threshold,
            max_iterations=max_iterations,
            probe_types=probe_types,
            limit=limit,
            dry_run=dry_run,
            checkpoint_file=checkpoint_file,
        )

        if as_json:
            console.print(json.dumps(result.to_dict(), indent=2))
            return

        # Summary
        console.print("[bold]Results:[/bold]")
        console.print(f"  Total personas: {result.total_personas}")
        console.print(f"  Initially passing: {result.initial_passing}")
        console.print(f"  Finally passing: {result.final_passing}")
        console.print(f"  Pass rate: {result.pass_rate:.1%}")
        console.print(f"  Tests run: {result.total_tests_run}")
        console.print(f"  Improvements made: {result.total_improvements_made}")

        # Show failures
        failures = [p for p in result.persona_results if not p["passed"]]
        if failures:
            console.print()
            console.print(f"[bold red]Still Failing ({len(failures)}):[/bold red]")
            for p in failures[:10]:
                console.print(f"  [red]✗[/red] {p['name']} ({p['final_accuracy']:.2f})")
            if len(failures) > 10:
                console.print(f"  ... and {len(failures) - 10} more")

        # Show successes
        successes = [p for p in result.persona_results if p["passed"] and p["iterations"] > 0]
        if successes:
            console.print()
            console.print(f"[bold green]Improved to Passing ({len(successes)}):[/bold green]")
            for p in successes[:5]:
                console.print(f"  [green]✓[/green] {p['name']} ({p['initial_accuracy']:.2f} → {p['final_accuracy']:.2f})")


# =============================================================================
# Audit Command
# =============================================================================

@app.command()
def audit(
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Scope to audit"),
    min_quality: float = typer.Option(0.0, "--min-quality", help="Only show below threshold"),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Max personas to audit"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    report: bool = typer.Option(False, "--report", help="Generate markdown report"),
):
    """
    Audit quality of all personas in a scope.

    Generates a quality report with grade distribution and common gaps.

    Examples:
        ./run.sh audit --scope personas
        ./run.sh audit --min-quality 0.6 --report > quality_report.md
    """
    console.print(f"\n[bold]Auditing personas...[/bold]")
    if scope:
        console.print(f"  Scope: {scope}")
    if min_quality > 0:
        console.print(f"  Filtering: below {min_quality}")
    console.print()

    result = audit_personas(
        scope=scope,
        min_quality=min_quality,
        limit=limit,
    )

    if as_json:
        console.print(json.dumps(result.to_dict(), indent=2))
        return

    if report:
        # Markdown report
        print(f"# Persona Quality Audit Report\n")
        print(f"**Scope:** {result.scope}")
        print(f"**Total Personas:** {result.total_personas}")
        print(f"**Average Score:** {result.average_score:.2f}\n")

        print("## Grade Distribution\n")
        print("| Grade | Count |")
        print("|-------|-------|")
        for grade, count in result.grade_distribution.items():
            print(f"| {grade} | {count} |")
        print()

        print("## Common Gaps\n")
        for gap, count in result.common_gaps.items():
            print(f"- {gap}: {count} personas")
        print()

        if result.failing_personas:
            print("## Failing Personas (Grade F)\n")
            for name in result.failing_personas:
                print(f"- {name}")
        return

    # Rich output
    console.print(f"[bold]Audit Results:[/bold]")
    console.print(f"  Total personas: {result.total_personas}")
    console.print(f"  Average score: {result.average_score:.2f}")
    console.print()

    # Grade distribution
    console.print("[bold]Grade Distribution:[/bold]")
    for grade in ["A", "B", "C", "D", "F"]:
        count = result.grade_distribution[grade]
        bar = "█" * count
        color = "green" if grade in ("A", "B") else "yellow" if grade == "C" else "red"
        console.print(f"  {grade}: [{color}]{bar}[/{color}] {count}")

    # Common gaps
    if result.common_gaps:
        console.print()
        console.print("[bold]Common Gaps:[/bold]")
        for gap, count in list(result.common_gaps.items())[:5]:
            console.print(f"  • {gap} ({count} personas)")

    # Failing personas
    if result.failing_personas:
        console.print()
        console.print("[bold red]Failing Personas (Grade F):[/bold red]")
        for name in result.failing_personas[:10]:
            console.print(f"  [red]•[/red] {name}")

        if len(result.failing_personas) > 10:
            console.print(f"  ... and {len(result.failing_personas) - 10} more")

        console.print()
        console.print("[dim]Run: ./run.sh improve NAME to fix failing personas[/dim]")

