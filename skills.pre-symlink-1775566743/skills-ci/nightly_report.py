"""Generate nightly health report and store to /memory for morning agent retrieval.

Combines skills-ci scan results + monitor-codebase findings into a single
structured report. Stored in /memory so the agent can recall it with
"show me last night's skills-ci report" or "nightly health check".
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import httpx
import typer
from loguru import logger

app = typer.Typer()

REPORT_PATH = Path("/mnt/storage12tb/media/agents/shared/skills-ci/report.json")
MONITOR_ARTIFACTS = Path(__file__).resolve().parent.parent / "monitor-codebase" / "artifacts"
MEMORY_SOCK = "/run/user/1000/embry/memory.sock"


def _memory_learn(content: str, metadata: dict | None = None) -> bool:
    """Store report to /memory via Unix socket."""
    try:
        transport = httpx.HTTPTransport(uds=MEMORY_SOCK)
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
            payload = {
                "problem": f"Nightly health report {metadata.get('date', 'unknown')}",
                "solution": content,
                "collection": "nightly_reports",
                "metadata": metadata or {},
            }
            resp = client.post("/learn", json=payload)
            return resp.status_code == 200
    except Exception as e:
        logger.warning(f"Memory learn failed: {e}")
        return False


def _build_report() -> dict:
    """Build combined report from skills-ci + monitor-codebase."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    report = {
        "date": date_str,
        "timestamp": datetime.now().isoformat(),
        "skills_ci": {"errors": 0, "warnings": 0, "violations": []},
        "monitor_codebase": {"projects": []},
        "tier2_fixes_applied": 0,
        "summary": "",
    }

    # Skills-CI report
    if REPORT_PATH.exists():
        try:
            data = json.loads(REPORT_PATH.read_text())
            violations = data.get("violations", [])
            errors = sum(1 for v in violations if v.get("severity") == "error")
            warnings = len(violations) - errors
            report["skills_ci"] = {
                "errors": errors,
                "warnings": warnings,
                "violations": [
                    {
                        "rule": v["rule"],
                        "skill": v["skill"],
                        "message": v["message"][:120],
                        "severity": v.get("severity", "warn"),
                    }
                    for v in violations
                ],
            }
        except Exception as e:
            logger.warning(f"Failed to read skills-ci report: {e}")

    # Monitor-codebase latest reports
    if MONITOR_ARTIFACTS.exists():
        for report_file in sorted(MONITOR_ARTIFACTS.glob("*_2*.json"), reverse=True)[:5]:
            try:
                proj_data = json.loads(report_file.read_text())
                summary = proj_data.get("summary", {})
                report["monitor_codebase"]["projects"].append({
                    "name": proj_data.get("project", report_file.stem),
                    "total_issues": summary.get("total_issues", 0),
                    "quality_violations": summary.get("total_quality_violations", 0),
                    "best_practices": summary.get("total_best_practices", 0),
                    "file": str(report_file),
                })
            except Exception:
                continue

    # Build human-readable summary
    sci = report["skills_ci"]
    mc_total = sum(p["total_issues"] for p in report["monitor_codebase"]["projects"])
    parts = []
    if sci["errors"]:
        parts.append(f"{sci['errors']} ERRORS")
    if sci["warnings"]:
        parts.append(f"{sci['warnings']} warnings")
    if mc_total:
        parts.append(f"{mc_total} codebase issues")
    report["summary"] = ", ".join(parts) if parts else "All clean"

    return report


def _format_markdown(report: dict) -> str:
    """Format report as markdown for /memory storage."""
    lines = [
        f"# Nightly Health Report — {report['date']}",
        "",
        f"**Summary**: {report['summary']}",
        "",
    ]

    sci = report["skills_ci"]
    lines.append(f"## Skills CI: {sci['errors']} errors, {sci['warnings']} warnings")
    if sci["violations"]:
        # Group by rule
        by_rule: dict[str, list] = {}
        for v in sci["violations"]:
            by_rule.setdefault(v["rule"], []).append(v)
        for rule, vlist in sorted(by_rule.items(), key=lambda x: -len(x[1])):
            lines.append(f"- **{rule}** ({len(vlist)}): {', '.join(v['skill'] for v in vlist[:5])}")
            if len(vlist) > 5:
                lines[-1] += f" +{len(vlist)-5} more"
    else:
        lines.append("No violations.")

    lines.append("")
    lines.append("## Monitor Codebase")
    for proj in report["monitor_codebase"]["projects"]:
        status = "CLEAN" if proj["total_issues"] == 0 else f"{proj['total_issues']} issues"
        lines.append(f"- **{proj['name']}**: {status}")
    if not report["monitor_codebase"]["projects"]:
        lines.append("No project scans available.")

    lines.append("")
    lines.append("## Action Required")
    if sci["errors"] > 0:
        lines.append("- **ERRORS need immediate attention** — run `/skills-ci scan` to see details")
    if sci["warnings"] > 10:
        lines.append("- Warnings above 10 — consider a cleanup session")
    if not sci["errors"] and sci["warnings"] <= 2:
        lines.append("- Estate is healthy. No action needed.")

    return "\n".join(lines)


@app.command()
def generate(
    store: bool = typer.Option(True, "--store/--no-store", help="Store to /memory"),
    output: str = typer.Option(None, "--output", "-o", help="Write markdown to file"),
    json_output: str = typer.Option(None, "--json", help="Write JSON to file"),
) -> None:
    """Generate nightly health report and optionally store to /memory."""
    report = _build_report()
    markdown = _format_markdown(report)

    print(markdown)

    if json_output:
        Path(json_output).write_text(json.dumps(report, indent=2))
        logger.info(f"JSON report → {json_output}")

    if output:
        Path(output).write_text(markdown)
        logger.info(f"Markdown report → {output}")

    if store:
        success = _memory_learn(
            markdown,
            metadata={
                "type": "nightly_report",
                "date": report["date"],
                "errors": report["skills_ci"]["errors"],
                "warnings": report["skills_ci"]["warnings"],
                "summary": report["summary"],
            },
        )
        if success:
            logger.info("Report stored to /memory (collection: nightly_reports)")
        else:
            logger.warning("Failed to store report to /memory — check daemon")


if __name__ == "__main__":
    app()
