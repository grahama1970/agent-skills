"""Markdown report generation for batch-report skill.

This module handles generating markdown-formatted reports from analysis data,
including summary tables, timing analysis, failure patterns, and quality gates.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path


def generate_markdown_report(
    output_dir: Path,
    manifest_analysis: dict,
    timing_analysis: dict,
    failure_analysis: dict,
    quality_analysis: dict,
) -> str:
    """Generate markdown report for extractor batch output.

    Args:
        output_dir: Path to the batch output directory.
        manifest_analysis: Result from analyze_manifests().
        timing_analysis: Result from analyze_timings().
        failure_analysis: Result from analyze_failures().
        quality_analysis: Result from analyze_quality().

    Returns:
        Formatted markdown report string.
    """
    run_id = (
        output_dir.name
        if output_dir.name.startswith("run-")
        else output_dir.parent.name
    )
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"# Batch Report: {run_id}",
        "",
        f"Generated: {now}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total items | {manifest_analysis['total']} |",
        f"| Successful | {manifest_analysis['successful']} "
        f"({manifest_analysis['successful']/max(manifest_analysis['total'],1)*100:.1f}%) |",
        f"| Partial | {manifest_analysis['partial']} "
        f"({manifest_analysis['partial']/max(manifest_analysis['total'],1)*100:.1f}%) |",
        f"| Failed | {manifest_analysis['failed']} "
        f"({manifest_analysis['failed']/max(manifest_analysis['total'],1)*100:.1f}%) |",
        f"| Failed URLs | {len(failure_analysis['failed_urls'])} |",
        "",
    ]

    # Timing analysis
    if timing_analysis["step_stats"]:
        avg_min = timing_analysis["avg_total_ms"] / 60000
        max_min = timing_analysis["max_total_ms"] / 60000

        lines.extend(
            [
                "## Timing Analysis",
                "",
                f"- **Average time per item:** {avg_min:.1f} min",
                f"- **Max time:** {max_min:.1f} min",
                "",
                "### Bottlenecks (by total time)",
                "",
                "| Step | Avg (s) | Max (s) | % of Total |",
                "|------|---------|---------|------------|",
            ]
        )

        for step, stats in list(timing_analysis["step_stats"].items())[:10]:
            lines.append(
                f"| {step} | {stats['avg_ms']/1000:.1f} | "
                f"{stats['max_ms']/1000:.1f} | {stats['pct_of_total']:.1f}% |"
            )
        lines.append("")

    # Failure patterns
    if failure_analysis["patterns"]:
        lines.extend(
            [
                "## Failure Patterns",
                "",
                "| Pattern | Count |",
                "|---------|-------|",
            ]
        )
        for pattern, count in failure_analysis["patterns"].most_common():
            lines.append(f"| {pattern} | {count} |")
        lines.append("")

    # Quality issues
    if quality_analysis["no_sections"] > 0 or quality_analysis["empty_toc"] > 0:
        lines.extend(
            [
                "## Quality Issues",
                "",
                "| Issue | Count |",
                "|-------|-------|",
                f"| Zero sections extracted | {quality_analysis['no_sections']} |",
                f"| Empty table of contents | {quality_analysis['empty_toc']} |",
                f"| Zero metrics (false PASS) | {len(manifest_analysis['zero_metrics'])} |",
                "",
            ]
        )

    # Sample outputs
    if quality_analysis["samples"]:
        lines.extend(
            [
                "## Sample Outputs",
                "",
                "| ID | Status | Sections | Tables | Requirements |",
                "|----|--------|----------|--------|--------------|",
            ]
        )
        for sample in quality_analysis["samples"][:10]:
            lines.append(
                f"| {sample['id'][:16]} | {sample['status']} | "
                f"{sample['sections']} | {sample['tables']} | {sample['requirements']} |"
            )
        lines.append("")

    # Recommendations
    lines.extend(
        [
            "## Recommendations",
            "",
        ]
    )

    # Generate recommendations based on analysis
    if timing_analysis["step_stats"]:
        top_bottleneck = (
            list(timing_analysis["step_stats"].keys())[0]
            if timing_analysis["step_stats"]
            else None
        )
        if top_bottleneck and "summarizer" in top_bottleneck.lower():
            lines.append(
                "1. **Section summarizer bottleneck:** Consider batch "
                "summarization or `--skip-summaries` flag"
            )
        if top_bottleneck and "table" in top_bottleneck.lower():
            lines.append(
                "1. **Table processing bottleneck:** Add confidence "
                "threshold before VLM description"
            )

    if len(manifest_analysis["zero_metrics"]) > 0:
        lines.append(
            "2. **False PASS on zero content:** Add validation that "
            "blocks > 0 before marking PASS"
        )

    if quality_analysis["no_sections"] > manifest_analysis["total"] * 0.1:
        lines.append(
            "3. **High empty section rate:** Review PDF parsing for "
            "problematic document types"
        )

    if failure_analysis["patterns"].get("CUDA OOM", 0) > 0:
        lines.append(
            "4. **CUDA OOM errors:** Consider reducing batch size or model quantization"
        )

    lines.append("")
    lines.append("---")
    lines.append("*Report generated by batch-report skill*")

    return "\n".join(lines)


def generate_generic_report(output_dir: Path, state_analysis: dict) -> str:
    """Generate a simple report from state file analysis.

    Args:
        output_dir: Path to the batch output directory (unused but kept for API).
        state_analysis: Result from analyze_state_file().

    Returns:
        Formatted markdown report string.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"# Batch Report: {state_analysis['name']}",
        "",
        f"Generated: {now}",
        "",
    ]

    if state_analysis.get("description"):
        lines.extend([f"*{state_analysis['description']}*", ""])

    lines.extend(
        [
            "## Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Status | {state_analysis['status']} |",
            f"| Total items | {state_analysis['total']} |",
            f"| Completed | {state_analysis['completed']} "
            f"({state_analysis['progress_pct']:.1f}%) |",
            f"| Failed | {state_analysis['failed']} |",
            f"| Remaining | {state_analysis['remaining']} |",
            "",
        ]
    )

    if state_analysis.get("rate_per_hour"):
        lines.extend(
            [
                "## Progress",
                "",
                f"- **Rate:** {state_analysis['rate_per_hour']:.1f} items/hour",
            ]
        )
        if state_analysis.get("eta_hours"):
            if state_analysis["eta_hours"] < 1:
                eta_str = f"{state_analysis['eta_hours'] * 60:.0f} minutes"
            else:
                eta_str = f"{state_analysis['eta_hours']:.1f} hours"
            lines.append(f"- **ETA:** {eta_str}")
        lines.append("")

    if state_analysis.get("current_item"):
        lines.extend(
            [
                "## Current",
                "",
                f"Processing: `{state_analysis['current_item']}`",
                "",
            ]
        )

    lines.append("---")
    lines.append("*Report generated by batch-report skill*")

    return "\n".join(lines)


def format_quality_gates_report(gate_results: list[dict]) -> str:
    """Format quality gate results as markdown.

    Args:
        gate_results: List of gate result dicts from evaluate_quality_gates().

    Returns:
        Formatted markdown section string.
    """
    if not gate_results:
        return ""

    all_passed = all(r["passed"] for r in gate_results)

    lines = [
        "## Quality Gates",
        "",
        f"**Status:** {'PASS - ALL PASSED' if all_passed else 'FAIL - GATES FAILED'}",
        "",
        "| Gate | Value | Status | Severity |",
        "|------|-------|--------|----------|",
    ]

    for r in gate_results:
        status = "PASS" if r["passed"] else "FAIL"
        severity = r["severity"].upper() if not r["passed"] else "-"
        value = f"{r['value']:.2f}" if isinstance(r["value"], float) else str(r["value"])
        lines.append(f"| {r['metric']} | {value} | {status} | {severity} |")

    # Add failure messages
    failures = [r for r in gate_results if not r["passed"]]
    if failures:
        lines.extend(["", "### Issues", ""])
        for r in failures:
            lines.append(f"- **[{r['severity'].upper()}]** {r['message']}")

    lines.append("")
    return "\n".join(lines)
