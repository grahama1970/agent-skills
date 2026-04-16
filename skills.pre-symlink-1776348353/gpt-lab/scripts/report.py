#!/usr/bin/env python3
"""JSON + Markdown report generation for benchmark results.

Usage:
    python report.py generate --task qra-validator --format markdown
    python report.py history --task qra-validator
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

SKILL_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = SKILL_DIR / "results"

app = typer.Typer(add_completion=False)


def _find_latest_report(task_name: str) -> Optional[Path]:
    """Find the latest benchmark report for a task."""
    task_dir = RESULTS_DIR / task_name
    if not task_dir.exists():
        return None

    reports = sorted(task_dir.glob("benchmark_*.json"), reverse=True)
    return reports[0] if reports else None


def _format_markdown(report: dict) -> str:
    """Convert benchmark report to Markdown format."""
    lines = []
    lines.append(f"# Benchmark Report: {report.get('task', 'unknown')}")
    lines.append(f"\nGenerated: {datetime.now().isoformat()}")
    lines.append(f"\nEval examples: {report.get('eval_examples', '?')}")

    # Winner
    if report.get("selected_model"):
        lines.append(f"\n## Selected Model: {report['selected_model']}")
        metrics = report.get("selected_metrics", {})
        lines.append(f"- Accuracy: {metrics.get('accuracy', 0):.4f}")
        lines.append(f"- Latency P50: {metrics.get('latency_p50_ms', 0):.0f}ms")

    # Results table
    results = report.get("results", [])
    if results:
        lines.append("\n## Results")
        lines.append("")
        lines.append("| Model | Status | Accuracy | Format Valid | P50 (ms) | P95 (ms) | VRAM (MB) |")
        lines.append("|-------|--------|----------|-------------|----------|----------|-----------|")

        for r in results:
            model = r.get("model", "?")
            status = r.get("status", "?")
            accuracy = f"{r.get('accuracy', 0):.4f}" if status == "ok" else "N/A"
            fmt = f"{r.get('format_valid', 0):.4f}" if status == "ok" else "N/A"
            p50 = f"{r.get('latency_p50_ms', 0):.0f}" if status == "ok" else "N/A"
            p95 = f"{r.get('latency_p95_ms', 0):.0f}" if status == "ok" else "N/A"
            vram = f"{r.get('vram_mb', 0)}" if status == "ok" else "N/A"
            lines.append(f"| {model} | {status} | {accuracy} | {fmt} | {p50} | {p95} | {vram} |")

    # Comparison
    comparison = report.get("comparison")
    if comparison:
        lines.append("\n## Fine-Tuned vs Prompted Comparison")
        lines.append(f"- Verdict: **{comparison.get('finetuning_verdict', '?')}**")
        lines.append(f"- Accuracy delta: {comparison.get('accuracy_delta', '?')}")
        lines.append(f"- Speedup: {comparison.get('speedup', '?')}")
        lines.append(f"- Cost savings: {comparison.get('cost_savings', '?')}")

    return "\n".join(lines)


@app.command("generate")
def generate(
    task: str = typer.Option(..., "--task", "-t", help="Task name"),
    format: str = typer.Option("json", "--format", "-f", help="Output format: json or markdown"),
    input_file: Optional[Path] = typer.Option(None, "--input", "-i"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o"),
):
    """Generate a report from benchmark results."""
    if input_file and input_file.exists():
        report = json.loads(input_file.read_text())
    else:
        latest = _find_latest_report(task)
        if latest:
            report = json.loads(latest.read_text())
        else:
            logger.error(f"No benchmark results found for task: {task}")
            raise typer.Exit(code=1)

    if format == "markdown":
        output = _format_markdown(report)
    else:
        output = json.dumps(report, indent=2)

    print(output)

    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(output)
        logger.info(f"Report saved to: {output_file}")


@app.command("history")
def history(
    task: str = typer.Option(..., "--task", "-t", help="Task name"),
):
    """Show benchmark history for a task."""
    task_dir = RESULTS_DIR / task
    if not task_dir.exists():
        logger.info(f"No benchmark history for: {task}")
        return

    reports = sorted(task_dir.glob("benchmark_*.json"))
    if not reports:
        logger.info(f"No benchmark history for: {task}")
        return

    print(f"\nBenchmark history for: {task}")
    print(f"{'=' * 60}")

    for report_path in reports:
        try:
            report = json.loads(report_path.read_text())
            selected = report.get("selected_model", "?")
            metrics = report.get("selected_metrics", {})
            acc = metrics.get("accuracy", 0)
            print(f"  {report_path.name}: {selected} (acc={acc:.4f})")
        except Exception:
            print(f"  {report_path.name}: (parse error)")


if __name__ == "__main__":
    app()
