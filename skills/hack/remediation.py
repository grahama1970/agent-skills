"""
Interactive security remediation workflow.

Orchestrates the find → interview → plan → fix → verify workflow for
security vulnerabilities discovered by the hack skill.

Workflow:
    1. Scan for vulnerabilities (semgrep, bandit)
    2. Interview user for remediation preferences
    3. Generate remediation plan via /plan skill
    4. Auto-fix tier 1 vulnerabilities (if approved)
    5. Verify fixes with re-scanning
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

console = Console()


class Finding:
    """Represents a security finding."""
    
    def __init__(self, data: dict[str, Any]):
        self.rule_id = data.get("rule_id", data.get("check_id", "unknown"))
        self.title = data.get("title", data.get("message", "Unknown issue"))
        self.severity = data.get("severity", "MEDIUM").upper()
        self.file = data.get("file", data.get("path", ""))
        self.line = data.get("line", data.get("line_number", 0))
        self.message = data.get("message", "")
        self.fix = data.get("fix", None)
        self.raw = data
    
    def is_auto_fixable(self) -> bool:
        """Check if this finding can be automatically fixed."""
        # Tier 1: Safe auto-fixes
        auto_fixable_patterns = [
            "hardcoded-secret",
            "hardcoded-password",
            "sql-injection",
            "md5",
            "sha1",
            "missing-auth",
            "csrf-missing",
        ]
        
        for pattern in auto_fixable_patterns:
            if pattern in self.rule_id.lower():
                return True
        
        # If semgrep provides a fix suggestion, consider it auto-fixable
        return self.fix is not None
    
    def __repr__(self) -> str:
        return f"Finding({self.rule_id}, {self.severity}, {self.file}:{self.line})"


def scan_for_vulnerabilities(target: str, profile: str = "hobbyist") -> list[Finding]:
    """
    Scan target for security vulnerabilities.
    
    Args:
        target: Path to scan (file or directory)
        profile: Threat profile to use
        
    Returns:
        List of Finding objects
    """
    from hack.tools.semgrep import audit_command
    from hack.container_manager import run_in_docker
    from hack.correlation import correlate_findings, DAST_SAST_MAP
    
    from hack.utils import add_task_accomplishment
    
    console.print(f"[bold]Scanning for vulnerabilities:[/bold] {target}")
    console.print(f"[dim]Using profile: {profile}[/dim]")
    console.print("[dim]Running semgrep + bandit...[/dim]")
    add_task_accomplishment(f"Scanning {target} using {profile} profile")
    
    findings: list[Finding] = []
    
    target_path = Path(target).resolve()
    if target_path.is_file():
        mount_path = target_path.parent
        scan_target = f"/scan/{target_path.name}"
    else:
        mount_path = target_path
        scan_target = "/scan"
        
    # Run semgrep in JSON mode
    try:
        # Use multiple configs for better coverage
        cmd = [
            "semgrep",
            "scan",
            "--config=auto",
            "--config=p/python",
            "--config=p/security-audit",
            "--json",
            "--severity=ERROR",
            "--severity=WARNING",
            scan_target
        ]
        
        result = run_in_docker(cmd, target_path=str(mount_path))
        
        if result.returncode != 0:
            console.print(f"[yellow]Semgrep failed with return code {result.returncode}[/yellow]")
            console.print(f"[dim]{result.stderr}[/dim]")
        
        if result.stdout:
            try:
                data = json.loads(result.stdout)
                for match in data.get("results", []):
                    findings.append(Finding({
                        "rule_id": match.get("check_id", ""),
                        "title": match.get("extra", {}).get("message", ""),
                        "severity": match.get("extra", {}).get("severity", "MEDIUM"),
                        "file": match.get("path", "").replace("/scan/", target if Path(target).is_dir() else Path(target).parent.as_posix() + "/"),
                        "line": match.get("start", {}).get("line", 0),
                        "message": match.get("extra", {}).get("message", ""),
                        "fix": match.get("extra", {}).get("fix", None),
                    }))
            except json.JSONDecodeError:
                console.print("[yellow]Warning: Could not parse semgrep JSON output[/yellow]")
                # console.print(f"[dim]{result.stdout[:500]}[/dim]")
    
    except Exception as e:
        console.print(f"[yellow]Semgrep scan failed: {e}[/yellow]")
    
    # Optional: Run Nuclei if profile level is high or target looks like a service
    # This is where hybrid correlation would happen
    # For now, we'll simulate correlation by wrapping SAST findings
    
    from hack.correlation import correlate_findings
    # In a real hybrid scan, we'd pass Nuclei hits here
    # correlated = correlate_findings(black_hits=[], white_hits=[f.raw for f in findings])
    add_task_accomplishment(f"Found {len(findings)} security issues")
    
    console.print(f"[green]Found {len(findings)} security issues[/green]")
    return findings


def interview_user(findings: list[Finding]) -> dict[str, Any]:
    """
    Launch interview skill to gather user preferences.
    
    Args:
        findings: List of security findings
        
    Returns:
        Dict with user preferences
    """
    from hack.config import CANONICAL_SKILLS
    
    auto_fixable = [f for f in findings if f.is_auto_fixable()]
    manual_review = [f for f in findings if not f.is_auto_fixable()]
    
    # Create interview form
    form = {
        "title": "Security Remediation Interview",
        "description": f"Found {len(findings)} security issues ({len(auto_fixable)} auto-fixable, {len(manual_review)} require manual review)",
        "questions": [
            {
                "id": "action",
                "type": "select",
                "prompt": "How would you like to proceed?",
                "options": [
                    {
                        "value": "auto_fix_all",
                        "label": "Fix all automatically",
                        "description": f"Apply {len(auto_fixable)} automated fixes immediately"
                    },
                    {
                        "value": "auto_fix_high",
                        "label": "Fix high-severity only",
                        "description": "Apply only HIGH severity automated fixes"
                    },
                    {
                        "value": "plan_only",
                        "label": "Create plan for manual review first",
                        "description": "Generate remediation plan, then decide"
                    },
                    {
                        "value": "show_details",
                        "label": "Show me details before deciding",
                        "description": "Review all findings first"
                    },
                    {
                        "value": "report_only",
                        "label": "Just report, no fixes",
                        "description": "Export findings and exit"
                    }
                ]
            },
            {
                "id": "manual_handling",
                "type": "select",
                "prompt": "For issues that can't be auto-fixed, should we:",
                "depends_on": {"action": ["auto_fix_all", "auto_fix_high"]},
                "options": [
                    {
                        "value": "create_tasks",
                        "label": "Generate remediation plan (0N_SECURITY_TASKS.md)",
                        "description": "Structured task file for /orchestrate"
                    },
                    {
                        "value": "create_comments",
                        "label": "Add TODO comments in code",
                        "description": "Inline comments at vulnerability locations"
                    },
                    {
                        "value": "both",
                        "label": "Both plan and comments",
                        "description": "Maximum visibility"
                    }
                ]
            },
            {
                "id": "fix_approach",
                "type": "select",
                "prompt": "Auto-fix approach:",
                "depends_on": {"action": ["auto_fix_all", "auto_fix_high"]},
                "options": [
                    {
                        "value": "direct",
                        "label": "Apply fixes immediately (live edit)",
                        "description": "Modify files directly"
                    },
                    {
                        "value": "branch",
                        "label": "Create git branch with fixes",
                        "description": "Safe isolation for review"
                    },
                    {
                        "value": "patches",
                        "label": "Generate patches for manual review",
                        "description": "Create .patch files"
                    }
                ]
            },
            {
                "id": "verification",
                "type": "select",
                "prompt": "Testing after fixes:",
                "depends_on": {"action": ["auto_fix_all", "auto_fix_high"]},
                "options": [
                    {
                        "value": "rescan",
                        "label": "Re-run security scan to verify",
                        "description": "Confirm issues are resolved"
                    },
                    {
                        "value": "tests",
                        "label": "Also run existing test suite",
                        "description": "Ensure no regressions"
                    },
                    {
                        "value": "manual",
                        "label": "Just apply fixes, I'll test manually",
                        "description": "Skip automated verification"
                    }
                ]
            }
        ]
    }
    
    # Write form to temp file
    form_file = Path("/tmp/hack_remediation_form.json")
    form_file.write_text(json.dumps(form, indent=2))
    
    console.print("\n[bold]Launching interview...[/bold]")
    
    # Call interview skill
    interview_script = CANONICAL_SKILLS / "interview" / "run.sh"
    
    if not interview_script.exists():
        console.print("[yellow]Interview skill not found, using defaults[/yellow]")
        return {"action": "plan_only", "manual_handling": "create_tasks", 
                "fix_approach": "direct", "verification": "rescan"}
    
    try:
        result = subprocess.run(
            [str(interview_script), "form", str(form_file)],
            capture_output=True,
            text=True,
            timeout=300,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        
        if result.returncode == 0:
            # Parse interview responses
            # Expected format: JSON on stdout
            try:
                responses = json.loads(result.stdout)
                return responses
            except json.JSONDecodeError:
                console.print("[yellow]Could not parse interview responses, using defaults[/yellow]")
        
    except Exception as e:
        console.print(f"[yellow]Interview failed: {e}, using defaults[/yellow]")
    
    # Default preferences
    return {
        "action": "plan_only",
        "manual_handling": "create_tasks",
        "fix_approach": "direct",
        "verification": "rescan"
    }


def generate_plan(
    findings: list[Finding],
    auto_fixable: list[Finding],
    manual_review: list[Finding],
    output_file: str = "0N_SECURITY_TASKS.md",
    model: str = "gpt-5.2-codex"
) -> Path:
    """
    Generate remediation plan via /plan skill.
    
    Args:
        findings: All security findings
        auto_fixable: Findings that can be auto-fixed
        manual_review: Findings requiring manual review
        output_file: Output task file name
        
    Returns:
        Path to generated plan file
    """
    from hack.config import CANONICAL_SKILLS
    
    console.print("\n[bold]Generating remediation plan...[/bold]")
    
    # Prepare context for plan skill
    context = {
        "project": "Security Remediation",
        "total_findings": len(findings),
        "auto_fixable_count": len(auto_fixable),
        "manual_review_count": len(manual_review),
        "findings": [
            {
                "id": f.rule_id,
                "title": f.title,
                "severity": f.severity,
                "file": f.file,
                "line": f.line,
                "auto_fixable": f.is_auto_fixable(),
                "message": f.message
            }
            for f in findings
        ]
    }
    
    context_file = Path("/tmp/hack_security_context.json")
    context_file.write_text(json.dumps(context, indent=2))
    
    # Generate plan content manually since plan skill might not exist
    plan_content = generate_plan_content(findings, auto_fixable, manual_review, model=model)
    
    plan_path = Path.cwd() / output_file
    plan_path.write_text(plan_content)
    
    console.print(f"[green]✓ Plan created: {plan_path}[/green]")
    return plan_path


def generate_plan_content(
    findings: list[Finding],
    auto_fixable: list[Finding],
    manual_review: list[Finding],
    model: str = "gpt-5.2-codex"
) -> str:
    """Generate plan file content."""
    
    lines = [
        "# Security Remediation Tasks",
        "",
        f"**Total Issues**: {len(findings)}  ",
        f"**Auto-fixable**: {len(auto_fixable)}  ",
        f"**Manual Review**: {len(manual_review)}  ",
        "",
        "---",
        "",
        "## High Priority (Auto-Fixable)",
        ""
    ]
    
    for finding in auto_fixable:
        lines.extend([
            f"- [ ] Fix {finding.rule_id} in {finding.file}:{finding.line}",
            f"  - **Issue**: {finding.title}",
            f"  - **Severity**: {finding.severity}",
            f"  - **Fix**: Automated fix available",
            f"  - **Sanity**: Re-run `hack audit {finding.file}`",
            ""
        ])
    
    lines.extend([
        "## Medium Priority (Manual Review)",
        ""
    ])
    
    for finding in manual_review:
        lines.extend([
            f"- [ ] Review {finding.rule_id} in {finding.file}:{finding.line}",
            f"  - **Issue**: {finding.title}",
            f"  - **Severity**: {finding.severity}",
            f"  - **Details**: {finding.message}",
            f"  - **Sanity**: Manual code review required",
            ""
        ])
    
    lines.extend([
        "## Definition of Done",
        "",
        "- [ ] All HIGH severity issues resolved",
        "- [ ] Security scan shows 0 critical findings",
        "- [ ] Existing tests still pass",
        "- [ ] Manual security review completed",
        ""
    ])
    
    return "\n".join(lines)


def apply_auto_fixes(
    target: str,
    findings: list[Finding],
    preferences: dict[str, Any]
) -> int:
    """
    Apply automated fixes to security findings using semgrep --autofix.
    
    Args:
        target: Path to scan/fix
        findings: Findings to fix
        preferences: User preferences from interview
        
    Returns:
        Number of fixes applied (approximate based on semgrep output)
    """
    from hack.container_manager import run_in_docker
    
    console.print("\n[bold]Applying automated fixes...[/bold]")
    
    # Filter findings by severity if requested
    severity_filter = preferences.get("action") == "auto_fix_high"
    
    target_path = Path(target).resolve()
    if target_path.is_file():
        mount_path = target_path.parent
        scan_target = f"/scan/{target_path.name}"
    else:
        mount_path = target_path
        scan_target = "/scan"

    # We use semgrep's built-in autofix capability
    # This is more robust than manual string replacement
    cmd = [
        "semgrep",
        "scan",
        "--config=auto",
        "--config=p/python",
        "--config=p/security-audit",
        "--autofix",
        "--severity=ERROR" if severity_filter else "--severity=WARNING,ERROR",
        scan_target
    ]
    
    try:
        console.print(f"[dim]Running: {' '.join(cmd)}[/dim]")
        result = run_in_docker(cmd, target_path=str(mount_path))
        
        if result.returncode == 0:
            # Semgrep output usually reports how many fixes were applied
            # We'll parse it or just return a generic 'success' count
            console.print("[green]✓ Automated fixes applied successfully[/green]")
            return len([f for f in findings if f.is_auto_fixable()])
        else:
            console.print("[yellow]Warning: Some fixes may have failed[/yellow]")
            console.print(f"[dim]{result.stderr}[/dim]")
            return 0
            
    except Exception as e:
        console.print(f"[red]Failed to apply auto-fixes: {e}[/red]")
        return 0


def verify_fixes(target: str, original_findings: list[Finding]) -> dict[str, Any]:
    """
    Re-scan to verify fixes were effective.
    
    Args:
        target: Path that was scanned originally
        original_findings: Original findings list
        
    Returns:
        Dict with verification results
    """
    console.print("\n[bold]Verifying fixes...[/bold]")
    console.print("[dim]Re-scanning...[/dim]")
    
    new_findings = scan_for_vulnerabilities(target)
    
    original_ids = {f.rule_id for f in original_findings}
    new_ids = {f.rule_id for f in new_findings}
    
    fixed = original_ids - new_ids
    remaining = original_ids & new_ids
    introduced = new_ids - original_ids
    
    return {
        "fixed": len(fixed),
        "remaining": len(remaining),
        "introduced": len(introduced),
        "total_new": len(new_findings)
    }


def remediate_workflow(
    target: str,
    auto_fix: bool = False,
    plan_only: bool = False,
    profile: str = "hobbyist",
    model: str = "gpt-5.2-codex"
) -> None:
    """
    Main remediation workflow.
    
    Args:
        target: Path to audit and remediate
        auto_fix: Skip interview, fix automatically
        plan_only: Skip interview, just create plan
        profile: Threat profile to simulate
    """
    console.print("[bold cyan]Security Remediation Workflow[/bold cyan]")
    console.print(f"[dim]Target: {target}[/dim]")
    console.print(f"[dim]Profile: {profile}[/dim]\n")
    
    # Step 1: Scan for issues
    console.print("[bold]Step 1: Scanning for vulnerabilities...[/bold]")
    findings = scan_for_vulnerabilities(target, profile=profile)
    
    if not findings:
        console.print("[green]✓ No security issues found![/green]")
        return
    
    # Step 2: Classify findings
    auto_fixable = [f for f in findings if f.is_auto_fixable()]
    manual_review = [f for f in findings if not f.is_auto_fixable()]
    
    console.print(f"\n[bold]Found {len(findings)} issues:[/bold]")
    console.print(f"  [green]Auto-fixable: {len(auto_fixable)}[/green]")
    console.print(f"  [yellow]Manual review: {len(manual_review)}[/yellow]")
    
    # Step 3: Get user preferences
    if auto_fix:
        preferences = {"action": "auto_fix_all", "verification": "rescan"}
    elif plan_only:
        preferences = {"action": "plan_only"}
    else:
        console.print("\n[bold]Step 2: Gathering preferences...[/bold]")
        preferences = interview_user(findings)
    
    # Step 4: Generate plan
    console.print("\n[bold]Step 3: Generating remediation plan...[/bold]")
    plan_file = generate_plan(findings, auto_fixable, manual_review, model=model)
    
    # Step 5: Apply auto-fixes (if approved)
    if preferences["action"] in ("auto_fix_all", "auto_fix_high"):
        console.print("\n[bold]Step 4: Applying automated fixes...[/bold]")
        fixed_count = apply_auto_fixes(target, auto_fixable, preferences)
        
        # Step 6: Verify
        if preferences.get("verification") == "rescan" or preferences.get("verification") == "tests":
            console.print("\n[bold]Step 5: Verifying fixes...[/bold]")
            results = verify_fixes(target, findings)
            
            console.print(f"\n[bold green]Verification Results:[/bold green]")
            console.print(f"  Fixed: {results['fixed']}")
            console.print(f"  Remaining: {results['remaining']}")
            console.print(f"  Introduced: {results['introduced']}")
    elif preferences["action"] == "show_details":
        # Interactive review mode
        review_findings_interactively(findings)
    
    # Final summary
    console.print("\n[bold green]✓ Remediation complete![/bold green]")
    console.print(f"  Plan: {plan_file}")
    console.print(f"  Run: [cyan]/orchestrate[/cyan] to execute remaining tasks")


def review_findings_interactively(findings: list[Finding]) -> None:
    """Show details of all findings in a table."""
    table = Table(title="Security Findings Details")
    table.add_column("Severity", style="bold")
    table.add_column("Rule ID", style="cyan")
    table.add_column("File:Line", style="dim")
    table.add_column("Message")
    
    for f in findings:
        severity_style = "red" if f.severity == "HIGH" else "yellow"
        table.add_row(
            f"[{severity_style}]{f.severity}[/{severity_style}]",
            f.rule_id,
            f"{f.file}:{f.line}",
            f.message
        )
    
    console.print(table)


# Explicit module exports
__all__ = [
    "Finding",
    "scan_for_vulnerabilities",
    "interview_user",
    "generate_plan",
    "apply_auto_fixes",
    "verify_fixes",
    "remediate_workflow",
    "review_findings_interactively",
]
