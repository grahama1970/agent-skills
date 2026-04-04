#!/usr/bin/env python3
"""Skills CI: scan and optionally fix skills against best-practices rules.

This is the main entry point and CLI. Business logic lives in submodules:
- models.py: Violation, Report dataclasses
- scanners.py: All scan rules (skills, python, memory, naming)
- fixers.py: Auto-fix logic (docstrings, requests alias)
- reporting.py: Markdown/JSON report generation and persistence
- integrations.py: Task-monitor, memory, analytics, agent-inbox, lint
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import typer
from loguru import logger

# Ensure submodules in this directory are importable by name
_THIS_DIR = str(Path(__file__).resolve().parent)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

# Re-export all public symbols so existing importers (tests, other skills)
# continue to work with ``from skills_ci import Violation, scan_skills, ...``
from models import Report, Violation, summarize_violations
from scanners import (
    ALLOWED_REQUESTS_METHODS,
    EXCLUDE_DIRS,
    FIX_EXCLUDE_SEGMENTS,
    has_module_docstring,
    iter_python_files,
    list_skill_dirs,
    parse_frontmatter,
    requests_safe_to_alias,
    scan_best_practices_python,
    scan_best_practices_skills,
    scan_memory_integration,
    scan_model_routing,
    scan_naming_convention,
    scan_subprocess_hygiene,
    should_fix_path,
    should_skip_path,
    uses_requests,
)
from runtime_scanners import scan_runtime_readiness
from dep_scanner import scan_dependency_completeness
from style_scanners import scan_style_thin_init_py
from quality_scanners import (
    scan_blind_test_enforcement,
    scan_hardcoded_skill_paths,
    scan_mock_only_tests,
    scan_prompt_hygiene,
    scan_regex_classifier,
    scan_shell_aql,
    scan_skill_md_length,
)
from fixers import alias_requests_to_httpx, apply_safe_fixes, insert_module_docstring
from reporting import (
    ARTIFACTS_DIR,
    render_markdown,
    render_markdown_for_skill,
    write_per_skill_reports,
    write_reports,
)
from integrations import (
    TaskMonitorIntegration,
    default_state_file,
    discover_best_practices,
    find_git_root,
    generate_figures,
    learn_report,
    sync_skill_actions,
    resolve_agent_inbox_binary,
    resolve_task_monitor_root,
    resolve_task_monitor_run,
    run_analytics,
    run_lint,
    run_sanity_and_tests,
    scan_systemd_hardening,
    send_agent_inbox_message,
    write_task_state,
)

# Keep _SKILLS_DIR for CLI default
_SKILLS_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Core scan orchestrator
# ---------------------------------------------------------------------------

def scan_skills(
    root: Path,
    best_practices: List[str],
    mode: str,
    apply: bool,
    max_fix_loc: int,
    monitor: Optional[TaskMonitorIntegration] = None,
) -> Tuple[Report, List[str]]:
    violations: List[Violation] = []
    applied_fixes: List[str] = []
    skipped_fixes: List[str] = []
    changed_skills: List[str] = []

    skills = list_skill_dirs(root)
    all_skill_names = {s.name for s in skills}

    for idx, skill_dir in enumerate(skills, start=1):
        if monitor:
            monitor.update(completed=idx - 1, current_item=skill_dir.name)
        if "best-practices-skills" in best_practices:
            violations.extend(scan_best_practices_skills(skill_dir))

        if "best-practices-python" in best_practices:
            v, _ = scan_best_practices_python(skill_dir)
            violations.extend(v)

        violations.extend(scan_memory_integration(skill_dir))
        violations.extend(scan_naming_convention(skill_dir))
        violations.extend(scan_model_routing(skill_dir, all_skill_names))
        violations.extend(scan_subprocess_hygiene(skill_dir))
        violations.extend(scan_runtime_readiness(skill_dir))
        violations.extend(scan_dependency_completeness(skill_dir))
        violations.extend(scan_style_thin_init_py(skill_dir))
        violations.extend(scan_prompt_hygiene(skill_dir))
        violations.extend(scan_blind_test_enforcement(skill_dir))
        violations.extend(scan_regex_classifier(skill_dir))
        violations.extend(scan_shell_aql(skill_dir))
        violations.extend(scan_skill_md_length(skill_dir))
        violations.extend(scan_hardcoded_skill_paths(skill_dir))
        violations.extend(scan_mock_only_tests(skill_dir))

    # Project-level scans (not per-skill)
    try:
        project_root = find_git_root(root)
        violations.extend(scan_systemd_hardening(project_root))
    except RuntimeError:
        pass  # Not in a git repo — skip systemd scan

    if apply:
        applied, skipped = apply_safe_fixes(violations, max_fix_loc=max_fix_loc)
        applied_fixes.extend(applied)
        skipped_fixes.extend(skipped)
        for path_str in applied:
            path = Path(path_str)
            try:
                skill_name = path.relative_to(root).parts[0]
                changed_skills.append(skill_name)
            except Exception:
                continue

    report = Report(
        root=str(root),
        best_practices=best_practices,
        mode=mode,
        timestamp=datetime.now(timezone.utc).isoformat(),
        violations=violations,
        applied_fixes=applied_fixes,
        skipped_fixes=skipped_fixes,
    )
    return report, changed_skills


# ---------------------------------------------------------------------------
# Stdout summary — agents need this to see results without reading files
# ---------------------------------------------------------------------------

_MAX_VIOLATIONS_PRINTED = 50


def _print_summary(report: Report) -> None:
    """Print scan summary and violations to stdout for agent consumption."""
    summary = report.summary()
    total_skills = len(list_skill_dirs(Path(report.root)))
    print(f"\n=== skills-ci {report.mode} ===")
    print(f"Scanned: {total_skills} skills")
    print(f"Violations: {summary['error']} errors, {summary['warn']} warnings ({summary['total']} total)")

    if not report.violations:
        print("PASS: No violations found")
        return

    # Group by skill for compact output
    by_skill: Dict[str, List[Violation]] = {}
    for v in report.violations:
        by_skill.setdefault(v.skill, []).append(v)

    printed = 0
    for skill in sorted(by_skill):
        for v in by_skill[skill]:
            if printed >= _MAX_VIOLATIONS_PRINTED:
                remaining = summary["total"] - printed
                print(f"  ... and {remaining} more (see report files)")
                return
            severity_tag = "ERROR" if v.severity == "error" else "WARN"
            print(f"  {severity_tag}: [{v.skill}] {v.rule}: {v.message}")
            printed += 1

    if report.applied_fixes:
        print(f"\nApplied fixes: {len(report.applied_fixes)}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

app = typer.Typer(help="Skills CI: scan and optionally fix skills against best-practices rules.")


@app.command()
def main(
    mode: str = typer.Option(..., "--mode", help="Mode: scan or apply"),
    root: str = typer.Option(str(_SKILLS_DIR), "--root", help="Skills root directory"),
    best_practices: str = typer.Option(None, "--best-practices", help="Comma-separated best-practices to check"),
    report_json: str = typer.Option(None, "--report-json", help="Output JSON report path"),
    report_md: str = typer.Option(None, "--report-md", help="Output markdown report path"),
    learn: bool = typer.Option(False, "--learn", help="Store report summary in /memory for drift detection"),
    analytics: bool = typer.Option(False, "--analytics", help="Run /analytics on violation data"),
    figure: bool = typer.Option(False, "--figure", help="Generate coverage figures via /create-figure"),
    worktree_base: str = typer.Option(
        str(_SKILLS_DIR.parent / ".worktrees" / "skills-ci"),
        "--worktree-base", help="Base path for git worktrees",
    ),
    copy_root: bool = typer.Option(False, "--copy-root", help="Copy root into worktree if missing (for fixtures)"),
    branch: str = typer.Option(None, "--branch", help="Git branch name for apply mode"),
    max_fix_loc: int = typer.Option(400, "--max-fix-loc", help="Max lines of code for auto-fix"),
    fail_on: str = typer.Option("error", "--fail-on", help="Fail on severity level: error or warn"),
    lint: bool = typer.Option(False, "--lint", help="Run lint.sh when present"),
    lint_scope: str = typer.Option("changed", "--lint-scope", help="Lint scope: changed or all"),
    per_skill: bool = typer.Option(False, "--per-skill", help="Write per-skill reports"),
    per_skill_dir: str = typer.Option(None, "--per-skill-dir", help="Directory for per-skill reports"),
    notify: str = typer.Option(None, "--notify", help="Send summary via agent-inbox to project"),
) -> None:
    """Scan and optionally fix skills against best-practices rules."""
    root_path = Path(root).resolve()
    bp_list = discover_best_practices(root_path, best_practices)

    rj = Path(report_json).resolve() if report_json else None
    rm = Path(report_md).resolve() if report_md else None

    if mode == "scan":
        monitor_name = "skills-ci-scan"
        total = len(list_skill_dirs(root_path))
        monitor = TaskMonitorIntegration(
            skills_root=root_path,
            name=monitor_name,
            project="pi-mono",
            state_file=default_state_file(rj, monitor_name),
            total=total,
            description="Skills CI scan",
        )
        monitor.start()
        report, _ = scan_skills(root_path, bp_list, mode="scan", apply=False, max_fix_loc=max_fix_loc, monitor=monitor)
        if lint and lint_scope == "all":
            run_lint(root_path, [p.name for p in list_skill_dirs(root_path)])
        write_reports(report, rj, rm)
        _print_summary(report)
        if per_skill:
            out_dir = Path(per_skill_dir) if per_skill_dir else (Path(report_json).parent / "skills" if report_json else ARTIFACTS_DIR / "skills")
            write_per_skill_reports(report, out_dir.resolve())
        if notify:
            summary = report.summary()
            msg = (
                f"skills-ci scan complete for {report.root}. "
                f"{summary['error']} errors, {summary['warn']} warnings, {summary['total']} total. "
                f"Per-skill reports: {per_skill_dir or str(ARTIFACTS_DIR / 'skills')}."
            )
            send_agent_inbox_message(root_path, notify, msg, rj)
        # Post-scan integrations
        default_rj = rj or (ARTIFACTS_DIR / "report.json")
        if learn:
            learn_report(root_path, report)
            sync_skill_actions(root_path)
        if analytics:
            run_analytics(root_path, default_rj)
        if figure:
            generate_figures(root_path, report)
        monitor.finish(report.summary())
        summary = report.summary()
        if fail_on == "warn" and summary["warn"] > 0:
            raise typer.Exit(2)
        if summary["error"] > 0:
            raise typer.Exit(1)
        return

    if mode == "autofix":
        # Direct apply: scan canonical dir, fix in-place, no worktree.
        # Designed for nightly /monitor-skills runs.
        monitor_name = "skills-ci-autofix"
        total = len(list_skill_dirs(root_path))
        monitor = TaskMonitorIntegration(
            skills_root=root_path,
            name=monitor_name,
            project="pi-mono",
            state_file=default_state_file(rj, monitor_name),
            total=total,
            description="Skills CI autofix",
        )
        monitor.start()
        report, changed_skills = scan_skills(
            root_path, bp_list, mode="autofix", apply=True,
            max_fix_loc=max_fix_loc, monitor=monitor,
        )
        write_reports(report, rj, rm)
        if per_skill:
            out_dir = Path(per_skill_dir) if per_skill_dir else (
                Path(report_json).parent / "skills" if report_json else ARTIFACTS_DIR / "skills"
            )
            write_per_skill_reports(report, out_dir.resolve())

        _print_summary(report)
        summary = report.summary()
        applied_count = len(report.applied_fixes)
        skipped_count = len(report.skipped_fixes)
        logger.info(
            f"Autofix complete: {applied_count} files fixed, "
            f"{skipped_count} skipped, {summary['total']} violations remain"
        )
        if notify:
            msg = (
                f"skills-ci autofix complete for {report.root}. "
                f"{applied_count} files fixed, {skipped_count} skipped. "
                f"{summary['error']} errors, {summary['warn']} warnings remain."
            )
            send_agent_inbox_message(root_path, notify, msg, rj)
        if learn:
            learn_report(root_path, report)
            sync_skill_actions(root_path)
        monitor.finish(summary)
        return

    # apply mode (worktree-based, for human review)
    import shutil as _shutil
    from integrations import _run as _subprocess_run

    repo_root = find_git_root(root_path)
    branch_name = branch or f"skills-ci-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    wt_base = Path(worktree_base).resolve()
    worktree_path = wt_base / branch_name

    if worktree_path.exists():
        raise SystemExit(f"Worktree path already exists: {worktree_path}")

    wt_base.mkdir(parents=True, exist_ok=True)

    _subprocess_run(["git", "-C", str(repo_root), "worktree", "add", "-b", branch_name, str(worktree_path)])

    try:
        relative_root = root_path.relative_to(repo_root)
    except ValueError as exc:
        raise SystemExit(f"Root must be inside git repo: {root_path}") from exc

    worktree_root = worktree_path / relative_root
    if copy_root and not worktree_root.exists():
        worktree_root.parent.mkdir(parents=True, exist_ok=True)
        _shutil.copytree(root_path, worktree_root)
    monitor_name = "skills-ci-apply"
    total = len(list_skill_dirs(worktree_root))
    monitor = TaskMonitorIntegration(
        skills_root=root_path,
        name=monitor_name,
        project="pi-mono",
        state_file=default_state_file(rj, monitor_name),
        total=total,
        description="Skills CI apply",
    )
    monitor.start()
    report, changed_skills = scan_skills(worktree_root, bp_list, mode="apply", apply=True, max_fix_loc=max_fix_loc, monitor=monitor)
    report.worktree = str(worktree_path)

    write_reports(report, rj, rm)
    _print_summary(report)
    if per_skill:
        out_dir = Path(per_skill_dir) if per_skill_dir else (Path(report_json).parent / "skills" if report_json else ARTIFACTS_DIR / "skills")
        write_per_skill_reports(report, out_dir.resolve())
    if notify:
        summary = report.summary()
        msg = (
            f"skills-ci apply complete for {report.root}. "
            f"{summary['error']} errors, {summary['warn']} warnings, {summary['total']} total. "
            f"Worktree: {report.worktree}. "
            f"Per-skill reports: {per_skill_dir or str(ARTIFACTS_DIR / 'skills')}."
        )
        send_agent_inbox_message(root_path, notify, msg, rj)
    monitor.finish(report.summary())

    if changed_skills:
        run_sanity_and_tests(worktree_root, changed_skills)
        # Post-hook: update skill registry in /memory for changed skills
        try:
            import subprocess as _sp
            _skill_names = ",".join(changed_skills)
            _sp.run(
                ["memory-agent", "ingest-skills", str(worktree_root), "--skill", _skill_names],
                check=False, timeout=120, capture_output=True,
            )
        except Exception:
            pass  # Best-effort — don't block CI on memory failures
    if lint:
        lint_targets = changed_skills
        if lint_scope == "all":
            lint_targets = [p.name for p in list_skill_dirs(worktree_root)]
        if lint_targets:
            run_lint(worktree_root, lint_targets)

    summary = report.summary()
    if fail_on == "warn" and summary["warn"] > 0:
        raise typer.Exit(2)
    if summary["error"] > 0:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
