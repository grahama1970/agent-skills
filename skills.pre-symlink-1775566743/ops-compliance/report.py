#!/usr/bin/env python3
"""
Compliance report generation.

Generates reports in Markdown, JSON, and HTML formats.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def generate_report(
    path: Path,
    output_format: str = "markdown",
    framework: str = "all"
) -> str:
    """
    Generate a compliance report.

    Args:
        path: Directory that was scanned
        output_format: Output format (markdown, json, html)
        framework: Framework to report on (soc2, gdpr, all)

    Returns:
        Formatted report string
    """
    # Collect results
    results: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(),
        "path": str(path),
        "framework": framework,
        "checks": [],
        "summary": {"passed": 0, "failed": 0, "warnings": 0},
    }

    # Run checks based on framework
    if framework in ("soc2", "all"):
        from frameworks.soc2 import run_soc2_checks
        soc2_results = run_soc2_checks(path)
        for r in soc2_results:
            r["framework"] = "SOC2"
        results["checks"].extend(soc2_results)

    if framework in ("gdpr", "all"):
        from frameworks.gdpr import run_gdpr_checks
        gdpr_results = run_gdpr_checks(path)
        for r in gdpr_results:
            r["framework"] = "GDPR"
        results["checks"].extend(gdpr_results)

    # Calculate summary
    for check in results["checks"]:
        status = check.get("status", "unknown")
        if status == "pass":
            results["summary"]["passed"] += 1
        elif status == "fail":
            results["summary"]["failed"] += 1
        elif status == "warning":
            results["summary"]["warnings"] += 1

    # Format output
    if output_format == "json":
        return json.dumps(results, indent=2)
    elif output_format == "html":
        return _format_html(results)
    else:  # markdown
        return _format_markdown(results)


def _format_markdown(results: dict[str, Any]) -> str:
    """Format results as Markdown."""
    lines: list[str] = []

    lines.append("# Compliance Report")
    lines.append("")
    lines.append(f"**Generated**: {results['generated_at']}")
    lines.append(f"**Path**: {results['path']}")
    lines.append(f"**Framework**: {results['framework'].upper()}")
    lines.append("")

    # Executive Summary
    lines.append("## Executive Summary")
    lines.append("")
    summary = results["summary"]
    total = summary["passed"] + summary["failed"] + summary["warnings"]
    pass_rate = (summary["passed"] / total * 100) if total > 0 else 0

    lines.append(f"| Metric | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Passed | {summary['passed']} |")
    lines.append(f"| Failed | {summary['failed']} |")
    lines.append(f"| Warnings | {summary['warnings']} |")
    lines.append(f"| **Total** | {total} |")
    lines.append(f"| **Pass Rate** | {pass_rate:.1f}% |")
    lines.append("")

    if summary["failed"] > 0:
        lines.append("> **Status**: ❌ Non-compliant - action required")
    elif summary["warnings"] > 0:
        lines.append("> **Status**: ⚠️ Compliant with warnings")
    else:
        lines.append("> **Status**: ✅ Compliant")
    lines.append("")

    # Failed Checks
    failed = [c for c in results["checks"] if c.get("status") == "fail"]
    if failed:
        lines.append("## Failed Checks (Action Required)")
        lines.append("")
        for check in failed:
            lines.append(f"### {check.get('control_id', 'N/A')}: {check.get('description', 'Unknown')}")
            lines.append("")
            lines.append(f"- **Framework**: {check.get('framework', 'N/A')}")
            lines.append(f"- **Category**: {check.get('category', check.get('article', 'N/A'))}")
            lines.append(f"- **Finding**: {check.get('finding', 'N/A')}")
            if check.get("details"):
                lines.append(f"- **Details**:")
                for detail in check["details"][:5]:
                    if isinstance(detail, dict):
                        lines.append(f"  - {detail.get('file', detail)}")
                    else:
                        lines.append(f"  - {detail}")
            if check.get("remediation"):
                lines.append(f"- **Remediation**: {check['remediation']}")
            lines.append("")

    # Warnings
    warnings = [c for c in results["checks"] if c.get("status") == "warning"]
    if warnings:
        lines.append("## Warnings (Review Recommended)")
        lines.append("")
        for check in warnings:
            lines.append(f"### {check.get('control_id', 'N/A')}: {check.get('description', 'Unknown')}")
            lines.append("")
            lines.append(f"- **Framework**: {check.get('framework', 'N/A')}")
            lines.append(f"- **Finding**: {check.get('finding', 'N/A')}")
            if check.get("remediation"):
                lines.append(f"- **Remediation**: {check['remediation']}")
            lines.append("")

    # Passed Checks
    passed = [c for c in results["checks"] if c.get("status") == "pass"]
    if passed:
        lines.append("## Passed Checks")
        lines.append("")
        lines.append("| Control ID | Description | Framework |")
        lines.append("|------------|-------------|-----------|")
        for check in passed:
            lines.append(f"| {check.get('control_id', 'N/A')} | {check.get('description', 'Unknown')} | {check.get('framework', 'N/A')} |")
        lines.append("")

    return "\n".join(lines)


def _format_html(results: dict[str, Any]) -> str:
    """Format results as HTML."""
    summary = results["summary"]
    total = summary["passed"] + summary["failed"] + summary["warnings"]
    pass_rate = (summary["passed"] / total * 100) if total > 0 else 0

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Compliance Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; }}
        h1 {{ color: #333; }}
        .summary {{ background: #f5f5f5; padding: 20px; border-radius: 8px; margin: 20px 0; }}
        .pass {{ color: #28a745; }}
        .fail {{ color: #dc3545; }}
        .warning {{ color: #ffc107; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background: #f8f9fa; }}
        .check {{ margin: 20px 0; padding: 15px; border-left: 4px solid #ddd; }}
        .check.fail {{ border-color: #dc3545; background: #fff5f5; }}
        .check.warning {{ border-color: #ffc107; background: #fffbf0; }}
    </style>
</head>
<body>
    <h1>Compliance Report</h1>
    <p><strong>Generated:</strong> {results['generated_at']}</p>
    <p><strong>Path:</strong> {results['path']}</p>
    <p><strong>Framework:</strong> {results['framework'].upper()}</p>

    <div class="summary">
        <h2>Executive Summary</h2>
        <table>
            <tr><th>Metric</th><th>Count</th></tr>
            <tr><td class="pass">Passed</td><td>{summary['passed']}</td></tr>
            <tr><td class="fail">Failed</td><td>{summary['failed']}</td></tr>
            <tr><td class="warning">Warnings</td><td>{summary['warnings']}</td></tr>
            <tr><th>Total</th><td>{total}</td></tr>
            <tr><th>Pass Rate</th><td>{pass_rate:.1f}%</td></tr>
        </table>
    </div>
"""

    # Failed checks
    failed = [c for c in results["checks"] if c.get("status") == "fail"]
    if failed:
        html += "<h2>Failed Checks</h2>"
        for check in failed:
            html += f"""
    <div class="check fail">
        <h3>{check.get('control_id', 'N/A')}: {check.get('description', 'Unknown')}</h3>
        <p><strong>Framework:</strong> {check.get('framework', 'N/A')}</p>
        <p><strong>Finding:</strong> {check.get('finding', 'N/A')}</p>
        <p><strong>Remediation:</strong> {check.get('remediation', 'N/A')}</p>
    </div>
"""

    # Warnings
    warnings = [c for c in results["checks"] if c.get("status") == "warning"]
    if warnings:
        html += "<h2>Warnings</h2>"
        for check in warnings:
            html += f"""
    <div class="check warning">
        <h3>{check.get('control_id', 'N/A')}: {check.get('description', 'Unknown')}</h3>
        <p><strong>Finding:</strong> {check.get('finding', 'N/A')}</p>
        <p><strong>Remediation:</strong> {check.get('remediation', 'N/A')}</p>
    </div>
"""

    # Passed checks
    passed = [c for c in results["checks"] if c.get("status") == "pass"]
    if passed:
        html += """
    <h2>Passed Checks</h2>
    <table>
        <tr><th>Control ID</th><th>Description</th><th>Framework</th></tr>
"""
        for check in passed:
            html += f"        <tr><td>{check.get('control_id', 'N/A')}</td><td>{check.get('description', 'Unknown')}</td><td>{check.get('framework', 'N/A')}</td></tr>\n"
        html += "    </table>"

    html += """
</body>
</html>
"""
    return html


if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    fmt = sys.argv[2] if len(sys.argv) > 2 else "markdown"
    print(generate_report(target, fmt))
