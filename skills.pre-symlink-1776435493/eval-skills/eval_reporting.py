#!/usr/bin/env python3
"""
Transparent Markdown and JSON reporting for eval-skills.

Produces human-readable reports with clear pass/fail evidence,
latency comparisons, and diffs for failures.
"""

from datetime import datetime, timezone


def format_markdown_report(report, regressions: list[str] | None = None) -> str:
    """Generate a transparent Markdown report from an EvalReport."""
    lines: list[str] = []

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    evaluated = [s for s in report.skills if not s.skipped]
    skipped = [s for s in report.skills if s.skipped]

    pass_count = sum(1 for s in evaluated if s.passed)
    status = "PASS" if report.passed else "FAIL"

    lines.append(f"# Eval Report — {status}")
    lines.append(f"")
    lines.append(f"**Date**: {now}")
    lines.append(
        f"**Summary**: {pass_count}/{len(evaluated)} skills passed, "
        f"{report.total_passed}/{report.total_cases} cases passed, "
        f"{len(skipped)} skipped"
    )
    lines.append("")

    # Regressions section
    if regressions:
        lines.append("## Latency Regressions")
        lines.append("")
        for r in regressions:
            lines.append(f"- {r}")
        lines.append("")

    # Per-skill sections
    for skill_report in report.skills:
        if skill_report.skipped:
            continue

        skill_status = "PASS" if skill_report.passed else "FAIL"
        total = len(skill_report.cases)
        lines.append(
            f"## {skill_report.skill} ({skill_status} — "
            f"{skill_report.pass_count}/{total} cases)"
        )
        lines.append("")

        # Summary table
        lines.append("| Case | Status | Duration | Budget | Baseline |")
        lines.append("|------|--------|----------|--------|----------|")

        for case in skill_report.cases:
            c_status = "PASS" if case.passed else "FAIL"
            duration = f"{case.duration_ms:,.0f}ms"
            budget = f"{case.latency_budget_ms:,.0f}ms" if case.latency_budget_ms else "—"
            baseline = f"{case.baseline_ms:,.0f}ms" if case.baseline_ms else "—"
            lines.append(
                f"| {case.name} | {c_status} | {duration} | {budget} | {baseline} |"
            )

        lines.append("")

        # Failure details
        for case in skill_report.cases:
            if case.passed:
                continue

            lines.append(f"### FAILURE: {case.name}")
            lines.append("")
            lines.append(
                f"Exit code: {case.exit_code} "
                f"(expected {case.expected_exit_code})"
            )

            if case.latency_budget_ms and case.duration_ms > case.latency_budget_ms:
                if case.baseline_ms and case.baseline_ms > 0:
                    pct = ((case.duration_ms / case.baseline_ms) - 1) * 100
                    lines.append(
                        f"Latency: {case.duration_ms:,.0f}ms "
                        f"(budget: {case.latency_budget_ms:,.0f}ms, "
                        f"baseline: {case.baseline_ms:,.0f}ms) "
                        f"— REGRESSION +{pct:.0f}%"
                    )
                else:
                    lines.append(
                        f"Latency: {case.duration_ms:,.0f}ms "
                        f"(budget: {case.latency_budget_ms:,.0f}ms)"
                    )

            lines.append("")
            for failure in case.failures:
                lines.append(f"- {failure}")
            lines.append("")

            # Show stderr if non-empty
            if case.stderr and case.stderr.strip():
                lines.append("```")
                lines.append(case.stderr[:1000])
                lines.append("```")
                lines.append("")

    # Skipped skills summary
    if skipped:
        lines.append("## Skipped Skills")
        lines.append("")
        for s in skipped:
            lines.append(f"- {s.skill}: {s.skip_reason}")
        lines.append("")

    return "\n".join(lines)
