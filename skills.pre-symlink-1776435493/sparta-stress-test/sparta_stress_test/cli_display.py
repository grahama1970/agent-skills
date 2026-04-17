"""Rich display helpers for SPARTA stress test CLI.

Contains all Rich table rendering functions extracted from cli.py.
"""

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

console = Console()


def display_evidence_case_summary(
    passed: int, failed: int, errors: int, total: int,
    classifications: dict, difficulty_stats: dict, elapsed: float,
):
    """Display evidence case stress test results with Rich tables."""
    table = Table(title="Evidence Case Stress Test")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    pass_rate = passed / total if total else 0
    style = "green" if pass_rate >= 0.85 else "yellow" if pass_rate >= 0.70 else "red"
    table.add_row("Total Questions", str(total))
    table.add_row("Passed", f"[{style}]{passed}[/{style}]")
    table.add_row("Failed", f"[red]{failed}[/red]" if failed else "0")
    if errors:
        table.add_row("Errors", f"[red]{errors}[/red]")
    table.add_row("Pass Rate", f"[{style}]{pass_rate:.1%}[/{style}]")
    table.add_row("Elapsed", f"{elapsed:.1f}s")
    if total > 0:
        table.add_row("Avg/question", f"{elapsed/total:.1f}s")
    console.print(table)

    # Classification distribution
    cls_table = Table(title="Classification Distribution")
    cls_table.add_column("Classification", style="bold")
    cls_table.add_column("Count", justify="right")
    cls_table.add_column("% of Total", justify="right")
    for cls, cnt in sorted(classifications.items(), key=lambda x: -x[1]):
        pct = cnt / total * 100 if total else 0
        cls_table.add_row(cls, str(cnt), f"{pct:.0f}%")
    console.print(cls_table)

    # By difficulty
    diff_table = Table(title="By Difficulty")
    diff_table.add_column("Difficulty")
    diff_table.add_column("Total", justify="right")
    diff_table.add_column("Passed", justify="right")
    diff_table.add_column("Failed", justify="right")
    diff_table.add_column("Pass Rate", justify="right")
    diff_table.add_column("Top Classification")
    for diff in ["simple", "medium", "complex", "ambiguous", "flawed"]:
        data = difficulty_stats.get(diff)
        if not data:
            continue
        rate = data["passed"] / data["total"] if data["total"] else 0
        style = "green" if rate >= 0.85 else "yellow" if rate >= 0.70 else "red"
        top_cls = max(data["classifications"], key=data["classifications"].get) if data["classifications"] else "-"
        diff_table.add_row(
            diff,
            str(data["total"]),
            str(data["passed"]),
            str(data["failed"]),
            f"[{style}]{rate:.0%}[/{style}]",
            top_cls,
        )
    console.print(diff_table)


def display_session_summary(summary: dict, elapsed: float):
    """Display session summary with Rich tables."""
    table = Table(title="Conversation Stress Test Results")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Total Sessions", str(summary["total"]))
    table.add_row("Pass Rate (A+/A/B)", f"{summary.get('pass_rate', 0):.1%}")
    table.add_row("Avg Turns", str(summary.get("avg_turns", 0)))
    table.add_row("Archived", str(summary.get("archived_count", 0)))
    table.add_row("Adversarial", str(summary.get("adversarial_count", 0)))

    grades = summary.get("overall_grades", {})
    grade_str = " | ".join(f"{g}: {grades.get(g, 0)}" for g in ["A+", "A", "B", "C", "F"])
    table.add_row("Grades", grade_str)

    table.add_row("Elapsed", f"{elapsed:.1f}s")
    if summary["total"] > 0 and elapsed > 0:
        table.add_row("Sessions/min", f"{summary['total'] / elapsed * 60:.1f}")

    console.print(table)

    # By persona
    by_persona = summary.get("by_persona", {})
    if by_persona:
        p_table = Table(title="By Persona")
        p_table.add_column("Persona")
        p_table.add_column("Count", justify="right")
        p_table.add_column("Avg Score", justify="right")
        for p, data in by_persona.items():
            p_table.add_row(p, str(data["total"]), f"{data['avg_composite']:.0%}")
        console.print(p_table)

    # Persona evaluations
    by_eval = summary.get("by_evaluation", {})
    if by_eval:
        e_table = Table(title="Persona Evaluations (Turn 3)")
        e_table.add_column("Evaluation")
        e_table.add_column("Count", justify="right")
        for ev, count in sorted(by_eval.items(), key=lambda x: -x[1]):
            style = "green" if ev == "satisfactory" else "yellow" if ev in ("flaw_caught", "incomplete") else "red"
            e_table.add_row(ev, str(count), style=style)
        console.print(e_table)

    # Dimension averages
    dims = summary.get("dimension_averages", {})
    if dims:
        dim_table = Table(title="Dimension Averages")
        dim_table.add_column("Dimension")
        dim_table.add_column("Score", justify="right")
        for dim, score in sorted(dims.items()):
            style = "green" if score >= 0.8 else "yellow" if score >= 0.6 else "red"
            dim_table.add_row(dim, f"{score:.0%}", style=style)
        console.print(dim_table)


def display_blame_report(blame_report: dict):
    """Display blame attribution summary."""
    primary = blame_report.get("primary_blame_distribution", {})
    if not primary:
        return

    typer.echo()
    table = Table(title="Blame Attribution (Failing Sessions)")
    table.add_column("Skill/Component", style="bold")
    table.add_column("Failures", justify="right")

    for component, count in primary.items():
        style = "red" if count > 5 else "yellow" if count > 2 else ""
        table.add_row(component, str(count), style=style)

    console.print(table)

    fixes = blame_report.get("top_fix_suggestions", [])
    if fixes:
        typer.echo("\nTop Fix Suggestions:")
        seen = set()
        for fs in fixes[:10]:
            key = fs["fix"][:80]
            if key not in seen:
                seen.add(key)
                typer.echo(f"  [{fs['blame']}] {fs['fix']}")


def display_summary(summary: dict, elapsed: Optional[float]):
    """Display summary table with Rich."""
    table = Table(title="SPARTA Stress Test Results")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Total Questions", str(summary["total"]))
    table.add_row("Pass Rate (A+/A/B)", f"{summary['pass_rate']:.1%}")
    table.add_row("A+ Rate", f"{summary['a_plus_rate']:.1%}")

    grades = summary["overall_grades"]
    grade_str = " | ".join(f"{g}: {grades.get(g, 0)}" for g in ["A+", "A", "B", "C", "F"])
    table.add_row("Grades", grade_str)

    if elapsed:
        table.add_row("Elapsed", f"{elapsed:.1f}s")
        table.add_row("QPS", f"{summary['total'] / elapsed:.1f}")

    console.print(table)

    # Per-difficulty breakdown
    diff_table = Table(title="By Difficulty")
    diff_table.add_column("Difficulty")
    diff_table.add_column("Count", justify="right")
    diff_table.add_column("Avg Score", justify="right")
    diff_table.add_column("A+", justify="right")
    diff_table.add_column("A", justify="right")
    diff_table.add_column("B", justify="right")
    diff_table.add_column("C", justify="right")
    diff_table.add_column("F", justify="right")

    for diff in ["simple", "medium", "complex", "ambiguous", "flawed"]:
        data = summary["by_difficulty"].get(diff, {})
        if not data:
            continue
        g = data.get("grades", {})
        diff_table.add_row(
            diff,
            str(data.get("total", 0)),
            f"{data.get('avg_composite', 0):.0%}",
            str(g.get("A+", 0)),
            str(g.get("A", 0)),
            str(g.get("B", 0)),
            str(g.get("C", 0)),
            str(g.get("F", 0)),
        )

    console.print(diff_table)

    # Per-dimension averages
    dims = summary.get("dimension_averages", {})
    if dims:
        dim_table = Table(title="Dimension Averages")
        dim_table.add_column("Dimension")
        dim_table.add_column("Score", justify="right")
        for dim, score in sorted(dims.items()):
            style = "green" if score >= 0.8 else "yellow" if score >= 0.6 else "red"
            dim_table.add_row(dim, f"{score:.0%}", style=style)
        console.print(dim_table)
