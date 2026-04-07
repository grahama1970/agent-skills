"""Report generation and persistence for skills-ci.

Renders scan results as Markdown and JSON, writes full reports and
per-skill breakdowns to the artifacts directory or user-specified paths.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

_THIS_DIR = str(Path(__file__).resolve().parent)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from models import Report, Violation, summarize_violations

# Heavy artifacts live on 12TB -- never on NVMe boot drive
_EMBRY_STORAGE = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb"))
ARTIFACTS_DIR = Path(os.environ.get("SKILLS_CI_ARTIFACTS", str(_EMBRY_STORAGE / "media/agents/shared/skills-ci")))


def render_markdown(report: Report) -> str:
    """Render a full scan report as a Markdown string."""
    summary = report.summary()
    lines = [
        f"# Skills CI Report",
        "",
        f"Root: `{report.root}`",
        f"Mode: `{report.mode}`",
        f"Timestamp: `{report.timestamp}`",
        "",
        f"Best practices: {', '.join(report.best_practices) if report.best_practices else 'none'}",
        "",
        f"Summary: {summary['error']} errors, {summary['warn']} warnings, {summary['total']} total",
        "",
        "## Violations",
        "",
        "| Severity | Rule | Skill | Path | Message | Fixable | Applied |",
        "|---------|------|-------|------|---------|---------|---------|",
    ]
    for v in report.violations:
        lines.append(
            f"| {v.severity} | {v.rule} | {v.skill} | {v.path} | {v.message} | {str(v.fixable).lower()} | {str(v.applied).lower()} |"
        )
    lines.append("")

    if report.applied_fixes:
        lines.append("## Applied fixes")
        lines.append("")
        for item in report.applied_fixes:
            lines.append(f"- {item}")
        lines.append("")

    if report.skipped_fixes:
        lines.append("## Skipped fixes")
        lines.append("")
        for item in report.skipped_fixes:
            lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines)


def render_markdown_for_skill(skill: str, report: Report, violations: List[Violation]) -> str:
    """Render a per-skill scan report as a Markdown string."""
    summary = summarize_violations(violations)
    lines = [
        f"# Skills CI Report: {skill}",
        "",
        f"Root: `{report.root}`",
        f"Mode: `{report.mode}`",
        f"Timestamp: `{report.timestamp}`",
        "",
        f"Best practices: {', '.join(report.best_practices) if report.best_practices else 'none'}",
        "",
        f"Summary: {summary['error']} errors, {summary['warn']} warnings, {summary['total']} total",
        "",
        "## Violations",
        "",
        "| Severity | Rule | Path | Message | Fixable | Applied |",
        "|---------|------|------|---------|---------|---------|",
    ]
    for v in violations:
        lines.append(
            f"| {v.severity} | {v.rule} | {v.path} | {v.message} | {str(v.fixable).lower()} | {str(v.applied).lower()} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_reports(report: Report, report_json: Optional[Path], report_md: Optional[Path]) -> None:
    """Write JSON and Markdown report files."""
    payload = {
        "root": report.root,
        "best_practices": report.best_practices,
        "mode": report.mode,
        "timestamp": report.timestamp,
        "summary": report.summary(),
        "worktree": report.worktree,
        "violations": [asdict(v) for v in report.violations],
        "applied_fixes": report.applied_fixes,
        "skipped_fixes": report.skipped_fixes,
    }
    # Always write to 12TB artifacts dir if no explicit paths given
    rj = report_json or (ARTIFACTS_DIR / "report.json")
    rm = report_md or (ARTIFACTS_DIR / "report.md")

    rj.parent.mkdir(parents=True, exist_ok=True)
    rj.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    rm.parent.mkdir(parents=True, exist_ok=True)
    rm.write_text(render_markdown(report), encoding="utf-8")


def write_per_skill_reports(report: Report, output_dir: Path) -> None:
    """Write individual JSON and Markdown reports per skill."""
    output_dir.mkdir(parents=True, exist_ok=True)
    by_skill: Dict[str, List[Violation]] = {}
    for v in report.violations:
        by_skill.setdefault(v.skill, []).append(v)

    for skill, violations in by_skill.items():
        skill_dir = output_dir / skill
        skill_dir.mkdir(parents=True, exist_ok=True)
        summary = summarize_violations(violations)
        payload = {
            "root": report.root,
            "best_practices": report.best_practices,
            "mode": report.mode,
            "timestamp": report.timestamp,
            "summary": summary,
            "worktree": report.worktree,
            "skill": skill,
            "violations": [asdict(v) for v in violations],
        }
        (skill_dir / "report.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        (skill_dir / "report.md").write_text(render_markdown_for_skill(skill, report, violations), encoding="utf-8")
