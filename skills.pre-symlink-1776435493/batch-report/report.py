#!/usr/bin/env python3
"""Batch Report - Post-run analysis and reporting for batch processing jobs.

Analyzes manifests, timings, and failures to generate comprehensive reports.
Optionally sends reports to agent-inbox for cross-project communication.

Usage:
    uv run python report.py analyze /path/to/batch/output
    uv run python report.py analyze /path/to/batch/output --send-to extractor
    uv run python report.py analyze /path/to/batch/output --json
    uv run python report.py summary /path/to/batch/output
    uv run python report.py failures /path/to/batch/output
    uv run python report.py state /path/to/.batch_state.json
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from batch_report.analysis import (
    analyze_failures,
    analyze_state_file,
    analyze_timings,
    evaluate_quality_gates,
)
from batch_report.config import BatchFormat
from batch_report.manifest_parser import (
    analyze_manifests,
    analyze_quality,
    find_final_reports,
    find_manifests,
    find_timings,
)
from batch_report.markdown_generator import (
    generate_generic_report,
    generate_markdown_report,
)
from batch_report.utils import detect_batch_format, send_to_agent_inbox

app = typer.Typer(help="Batch Report - Post-run analysis for batch jobs")
console = Console()


@app.command()
def analyze(
    output_dir: Path = typer.Argument(..., help="Batch output directory to analyze"),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file (default: stdout)"
    ),
    send_to: Optional[str] = typer.Option(
        None, "--send-to", "-s", help="Send report to agent-inbox project"
    ),
    priority: str = typer.Option(
        "normal", "--priority", "-p", help="Priority for agent-inbox"
    ),
    sample_count: int = typer.Option(
        5, "--sample", "-n", help="Number of samples to include"
    ),
    format: BatchFormat = typer.Option(
        BatchFormat.auto,
        "--format",
        "-f",
        help="Batch format (auto-detected if not specified)",
    ),
    as_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON for piping"),
):
    """Generate full analysis report for a batch output directory."""
    if not output_dir.exists():
        console.print(f"[red]Error: Directory not found: {output_dir}[/]", stderr=True)
        raise typer.Exit(1)

    # Auto-detect format if needed
    detected_format = (
        detect_batch_format(output_dir) if format == BatchFormat.auto else format
    )

    if not as_json:
        console.print(f"[cyan]Analyzing batch output: {output_dir}[/]")
        console.print(f"  Format: {detected_format.value}")

    # Run format-specific analysis
    if detected_format == BatchFormat.extractor:
        manifests = find_manifests(output_dir)
        timings = find_timings(output_dir)
        final_reports = find_final_reports(output_dir)

        if not as_json:
            console.print(
                f"  Found {len(manifests)} manifests, {len(timings)} timing files, "
                f"{len(final_reports)} reports"
            )

        manifest_analysis = analyze_manifests(manifests)
        timing_analysis = analyze_timings(timings)
        failure_analysis = analyze_failures(output_dir)
        quality_analysis = analyze_quality(final_reports, sample_limit=sample_count)

        if as_json:
            result = {
                "format": "extractor",
                "output_dir": str(output_dir),
                "manifest_analysis": manifest_analysis,
                "timing_analysis": timing_analysis,
                "failure_analysis": {
                    "failed_urls": failure_analysis["failed_urls"],
                    "patterns": dict(failure_analysis["patterns"]),
                    "details": failure_analysis["details"],
                },
                "quality_analysis": quality_analysis,
            }
            print(json.dumps(result, indent=2, default=str))
            return

        # Generate markdown report
        report = generate_markdown_report(
            output_dir,
            manifest_analysis,
            timing_analysis,
            failure_analysis,
            quality_analysis,
        )
    else:
        # Generic or youtube format - use state file
        state_path = output_dir / ".batch_state.json"
        if not state_path.exists():
            console.print(
                f"[red]Error: No .batch_state.json found in {output_dir}[/]",
                stderr=True,
            )
            raise typer.Exit(1)

        state_analysis = analyze_state_file(state_path)

        if as_json:
            result = {
                "format": detected_format.value,
                "output_dir": str(output_dir),
                "state_analysis": state_analysis,
            }
            print(json.dumps(result, indent=2, default=str))
            return

        # Generate simple report for generic/youtube
        report = generate_generic_report(output_dir, state_analysis)

    # Output
    if output:
        output.write_text(report, encoding="utf-8")
        console.print(f"[green]Report written to: {output}[/]")
    else:
        console.print()
        console.print(report)

    # Send to agent-inbox
    if send_to:
        msg_id = send_to_agent_inbox(send_to, report, priority)
        if msg_id:
            console.print(f"[green]Report sent to agent-inbox: {msg_id}[/]")


@app.command()
def summary(
    output_dir: Path = typer.Argument(..., help="Batch output directory"),
    format: BatchFormat = typer.Option(
        BatchFormat.auto, "--format", "-f", help="Batch format"
    ),
    as_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Show quick summary stats."""
    if not output_dir.exists():
        console.print(f"[red]Error: Directory not found: {output_dir}[/]", stderr=True)
        raise typer.Exit(1)

    detected_format = (
        detect_batch_format(output_dir) if format == BatchFormat.auto else format
    )

    if detected_format == BatchFormat.extractor:
        manifests = find_manifests(output_dir)
        analysis = analyze_manifests(manifests)
        timings = analyze_timings(find_timings(output_dir))

        run_id = (
            output_dir.name
            if output_dir.name.startswith("run-")
            else output_dir.parent.name
        )
        success_rate = analysis["successful"] / max(analysis["total"], 1) * 100
        avg_min = timings["avg_total_ms"] / 60000 if timings["avg_total_ms"] else 0

        # Find top bottleneck
        top_step_name = None
        top_pct = 0
        if timings["step_stats"]:
            top_step_name = list(timings["step_stats"].keys())[0]
            top_pct = timings["step_stats"][top_step_name]["pct_of_total"]

        if as_json:
            result = {
                "batch": run_id,
                "format": "extractor",
                "total": analysis["total"],
                "successful": analysis["successful"],
                "partial": analysis["partial"],
                "failed": analysis["failed"],
                "success_rate": success_rate,
                "avg_time_min": avg_min,
                "top_bottleneck": top_step_name,
                "top_bottleneck_pct": top_pct,
            }
            print(json.dumps(result, indent=2))
            return

        top_step = (
            f" | Slowest: {top_step_name} ({top_pct:.0f}%)" if top_step_name else ""
        )
        console.print(f"[bold]Batch:[/] {run_id}")
        console.print(
            f"[bold]Total:[/] {analysis['total']} | [green]Success:[/] "
            f"{analysis['successful']} | [yellow]Partial:[/] {analysis['partial']} | "
            f"[red]Failed:[/] {analysis['failed']}"
        )
        console.print(f"[bold]Success rate:[/] {success_rate:.1f}%")
        console.print(f"[bold]Avg time:[/] {avg_min:.1f} min{top_step}")
    else:
        # Generic/youtube - use state file
        state_path = output_dir / ".batch_state.json"
        if not state_path.exists():
            console.print("[red]Error: No .batch_state.json found[/]", stderr=True)
            raise typer.Exit(1)

        analysis = analyze_state_file(state_path)

        if as_json:
            print(json.dumps(analysis, indent=2, default=str))
            return

        console.print(f"[bold]Batch:[/] {analysis['name']}")
        console.print(f"[bold]Status:[/] {analysis['status']}")
        console.print(
            f"[bold]Total:[/] {analysis['total']} | [green]Completed:[/] "
            f"{analysis['completed']} | [red]Failed:[/] {analysis['failed']} | "
            f"Remaining: {analysis['remaining']}"
        )
        console.print(f"[bold]Progress:[/] {analysis['progress_pct']:.1f}%")
        if analysis.get("rate_per_hour"):
            eta_str = (
                f" | ETA: {analysis['eta_hours']:.1f}h"
                if analysis.get("eta_hours")
                else ""
            )
            console.print(f"[bold]Rate:[/] {analysis['rate_per_hour']:.1f}/hour{eta_str}")


@app.command()
def failures(
    output_dir: Path = typer.Argument(..., help="Batch output directory"),
    as_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """List failures with reasons."""
    if not output_dir.exists():
        console.print(f"[red]Error: Directory not found: {output_dir}[/]", stderr=True)
        raise typer.Exit(1)

    failure_analysis = analyze_failures(output_dir)

    if as_json:
        result = {
            "failed_urls": failure_analysis["failed_urls"],
            "patterns": dict(failure_analysis["patterns"]),
            "details": failure_analysis["details"],
        }
        print(json.dumps(result, indent=2))
        return

    table = Table(title="Failure Analysis")
    table.add_column("Pattern", style="red")
    table.add_column("Count", justify="right")

    for pattern, count in failure_analysis["patterns"].most_common():
        table.add_row(pattern, str(count))

    console.print(table)

    if failure_analysis["failed_urls"]:
        console.print(
            f"\n[bold]Failed URLs ({len(failure_analysis['failed_urls'])}):[/]"
        )
        for url in failure_analysis["failed_urls"][:10]:
            console.print(f"  - {url[:80]}")
        if len(failure_analysis["failed_urls"]) > 10:
            console.print(f"  ... and {len(failure_analysis['failed_urls']) - 10} more")


@app.command()
def state(
    state_path: Path = typer.Argument(..., help="Path to .batch_state.json file"),
    as_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Analyze a standalone .batch_state.json file."""
    if not state_path.exists():
        console.print(
            f"[red]Error: State file not found: {state_path}[/]", stderr=True
        )
        raise typer.Exit(1)

    analysis = analyze_state_file(state_path)

    if "error" in analysis:
        console.print(
            f"[red]Error reading state file: {analysis['error']}[/]", stderr=True
        )
        raise typer.Exit(1)

    if as_json:
        print(json.dumps(analysis, indent=2, default=str))
        return

    # Pretty print
    console.print(f"[bold cyan]Batch:[/] {analysis['name']}")
    if analysis.get("description"):
        console.print(f"  {analysis['description']}")
    console.print()

    # Progress bar
    completed = analysis["completed"]
    total = analysis["total"]
    pct = analysis["progress_pct"]

    bar_width = 40
    filled = int(bar_width * pct / 100)
    bar = "[green]" + "#" * filled + "[/]" + "-" * (bar_width - filled)

    console.print(f"  {bar} {pct:.1f}%")
    console.print()

    console.print(f"  [bold]Status:[/] {analysis['status']}")
    console.print(f"  [bold]Completed:[/] {completed}/{total}")
    console.print(f"  [bold]Failed:[/] {analysis['failed']}")
    console.print(f"  [bold]Remaining:[/] {analysis['remaining']}")

    if analysis.get("rate_per_hour"):
        console.print(f"\n  [bold]Rate:[/] {analysis['rate_per_hour']:.1f} items/hour")
        if analysis.get("eta_hours"):
            if analysis["eta_hours"] < 1:
                eta_str = f"{analysis['eta_hours'] * 60:.0f} minutes"
            else:
                eta_str = f"{analysis['eta_hours']:.1f} hours"
            console.print(f"  [bold]ETA:[/] {eta_str}")

    if analysis.get("current_item"):
        console.print(f"\n  [bold]Current:[/] {analysis['current_item']}")

    # Quality Gates
    gates_results = evaluate_quality_gates(analysis, output_dir=state_path.parent)
    if gates_results:
        console.print()
        console.print("[bold]Quality Gates:[/]")

        table = Table(box=None)
        table.add_column("Metric", style="cyan")
        table.add_column("Value")
        table.add_column("Status")
        table.add_column("Details")

        for r in gates_results:
            status = (
                "[green]PASS[/]"
                if r["passed"]
                else f"[red]FAIL ({r['severity'].upper()})[/]"
            )
            value = (
                f"{r['value']:.2f}"
                if isinstance(r["value"], float)
                else str(r["value"])
            )
            msg = r["message"] if not r["passed"] else ""
            table.add_row(r["metric"], value, status, msg)

        console.print(table)


if __name__ == "__main__":
    app()
