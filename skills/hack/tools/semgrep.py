"""
Semgrep and Bandit SAST tool integration.

This module provides static application security testing (SAST)
and software composition analysis (SCA) using semgrep, bandit,
pip-audit, and safety running in isolated Docker containers.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import typer
from typing import Callable
from rich.console import Console

from hack.config import BANDIT_SEVERITY_FLAGS
from hack.container_manager import require_docker_image, run_in_docker
from hack.utils import show_memory_context

console = Console()


def audit_command(
    target: str,
    tool: str = "all",
    severity: str = "medium",
    output: str | None = None,
    recall: bool = True,
):
    """
    Run static application security testing (SAST) on code.

    ALL auditing runs in an isolated Docker container for security.
    Uses Semgrep and Bandit to find security vulnerabilities in Python code.

    Args:
        target: Directory or file to audit
        tool: Tool to use - all, semgrep, or bandit
        severity: Minimum severity - low, medium, or high
        output: Output file path (JSON format)
        recall: Whether to query memory for prior audit knowledge
    """
    target_path = Path(target).resolve()
    if not target_path.exists():
        console.print(f"[red]Target not found: {target}[/red]")
        sys.exit(1)

    console.print(f"[bold red]Starting security audit for:[/bold red] {target_path}")
    console.print("[dim]Running in isolated Docker container...[/dim]")

    # Memory recall for relevant vulnerability patterns
    if recall:
        show_memory_context(f"SAST security vulnerabilities {tool} Python code audit")

    require_docker_image()

    results = {"semgrep": None, "bandit": None, "total_findings": 0}

    # Determine mount path
    if target_path.is_file():
        mount_path = target_path.parent
        scan_target = f"/scan/{target_path.name}"
    else:
        mount_path = target_path
        scan_target = "/scan"

    # Run Semgrep
    if tool in ("all", "semgrep"):
        console.print("\n[cyan]Running Semgrep (SAST)...[/cyan]")
        cmd = ["semgrep", "scan", "--config", "auto", scan_target]

        try:
            result = run_in_docker(cmd, target_path=str(mount_path), network="none")
            if result.stdout:
                console.print(result.stdout)
                results["semgrep"] = result.stdout
            if result.stderr:
                console.print(f"[dim]{result.stderr}[/dim]")
        except subprocess.TimeoutExpired:
            console.print("[yellow]Semgrep timed out[/yellow]")
        except Exception as e:
            console.print(f"[yellow]Semgrep error: {e}[/yellow]")

    # Run Bandit (Python-specific)
    if tool in ("all", "bandit"):
        console.print("\n[cyan]Running Bandit (Python SAST)...[/cyan]")

        # Bandit severity: -l (low+), -ll (medium+), -lll (high only)
        sev_flag = BANDIT_SEVERITY_FLAGS.get(severity.lower(), "-ll")

        cmd = ["bandit", "-r", scan_target, sev_flag, "-f", "txt"]

        try:
            result = run_in_docker(cmd, target_path=str(mount_path), network="none")
            if result.stdout:
                console.print(result.stdout)
                results["bandit"] = result.stdout
            if result.stderr and "No issues" not in result.stderr:
                console.print(f"[dim]{result.stderr}[/dim]")
        except subprocess.TimeoutExpired:
            console.print("[yellow]Bandit timed out[/yellow]")
        except Exception as e:
            console.print(f"[yellow]Bandit error: {e}[/yellow]")

    # Save combined results
    if output:
        with open(output, "w") as f:
            json.dump(results, f, indent=2)
        console.print(f"\n[green]Results saved to: {output}[/green]")

    console.print("\n[bold green]Audit complete.[/bold green]")


def sca_command(
    target: str = ".",
    tool: str = "pip-audit",
    output: str | None = None,
):
    """
    Software Composition Analysis - scan dependencies for known vulnerabilities.

    ALL scanning runs in an isolated Docker container for security.

    Args:
        target: Directory to scan for dependencies
        tool: Tool to use - pip-audit or safety
        output: Output file path (JSON format)
    """
    target_path = Path(target).resolve()
    console.print(f"[bold blue]Scanning dependencies in:[/bold blue] {target_path}")
    console.print("[dim]Running in isolated Docker container...[/dim]")

    require_docker_image()

    # Check for requirements.txt or pyproject.toml
    req_file = target_path / "requirements.txt"
    pyproject = target_path / "pyproject.toml"

    if not req_file.exists() and not pyproject.exists():
        console.print("[yellow]No requirements.txt or pyproject.toml found[/yellow]")

    if tool == "pip-audit":
        cmd = ["pip-audit"]
        if req_file.exists():
            cmd.extend(["-r", "/scan/requirements.txt"])

        console.print(f"[dim]Command: {' '.join(cmd)}[/dim]")

        try:
            result = run_in_docker(
                cmd, target_path=str(target_path), network="bridge"
            )

            if result.returncode == 0:
                console.print("[green]No vulnerabilities found![/green]")
            else:
                console.print(result.stdout)
                console.print("[yellow]Vulnerabilities detected - review above[/yellow]")

            if result.stderr:
                console.print(f"[dim]{result.stderr}[/dim]")

            if output:
                Path(output).write_text(result.stdout or "")
                console.print(f"[dim]Results saved to: {output}[/dim]")

        except subprocess.TimeoutExpired:
            console.print("[red]Scan timed out[/red]")
            sys.exit(1)

    elif tool == "safety":
        cmd = ["safety", "check"]
        if req_file.exists():
            cmd.extend(["-r", "/scan/requirements.txt"])

        console.print(f"[dim]Command: {' '.join(cmd)}[/dim]")

        try:
            result = run_in_docker(
                cmd, target_path=str(target_path), network="bridge"
            )
            console.print(result.stdout)
            if result.stderr:
                console.print(f"[dim]{result.stderr}[/dim]")

            if output:
                Path(output).write_text(result.stdout or "")
                console.print(f"[dim]Results saved to: {output}[/dim]")

        except subprocess.TimeoutExpired:
            console.print("[red]Scan timed out[/red]")
            sys.exit(1)


def create_audit_typer_command() -> Callable[..., None]:
    """Create a typer command wrapper for audit_command."""

    def audit(
        target: str = typer.Argument(..., help="Directory or file to audit"),
        tool: str = typer.Option("all", help="Tool to use: all, semgrep, bandit"),
        severity: str = typer.Option(
            "medium", help="Minimum severity: low, medium, high"
        ),
        output: str = typer.Option(None, help="Output file (JSON format)"),
        recall: bool = typer.Option(
            True, help="Query memory for prior audit knowledge"
        ),
    ):
        """
        Run static application security testing (SAST) on code.

        ALL auditing runs in an isolated Docker container for security.
        Uses Semgrep and Bandit to find security vulnerabilities in Python code.
        """
        audit_command(target, tool, severity, output, recall)

    return audit


def create_sca_typer_command() -> Callable[..., None]:
    """Create a typer command wrapper for sca_command."""

    def sca(
        target: str = typer.Argument(
            ".", help="Directory to scan for dependencies"
        ),
        tool: str = typer.Option("pip-audit", help="Tool: pip-audit, safety"),
        output: str = typer.Option(None, help="Output file (JSON)"),
    ):
        """
        Software Composition Analysis - scan dependencies for known vulnerabilities.

        ALL scanning runs in an isolated Docker container for security.
        """
        sca_command(target, tool, output)

    return sca

# Explicit module exports for clarity
__all__ = [
    "audit_command",
    "sca_command",
    "create_audit_typer_command",
    "create_sca_typer_command",
]
