"""
Nuclei template-based vulnerability scanning integration.

This module provides dynamic application security testing (DAST)
using nuclei running in an isolated Docker container.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer
from typing import Callable
from rich.console import Console

from hack.container_manager import require_docker_image, run_in_docker
from hack.utils import show_memory_context

console = Console()


def nuclei_command(
    target: str,
    templates: str | None = None,
    severity: str = "medium,high,critical",
    rate_limit: int = 150,
    output: str | None = None,
    recall: bool = True,
):
    """
    Run template-based vulnerability scanning using Nuclei.

    ALL scanning runs in an isolated Docker container for security.

    Args:
        target: Target URL or file with list of URLs
        templates: Template directory or specific template to use
        severity: Severity filter (comma-separated: info,low,medium,high,critical)
        rate_limit: Maximum requests per second
        output: Output file path for results
        recall: Whether to query memory for prior scanning knowledge
    """
    console.print(f"[bold magenta]Starting Nuclei scan on:[/bold magenta] {target}")
    console.print("[dim]Running in isolated Docker container...[/dim]")

    # Memory recall for relevant scanning techniques
    if recall:
        show_memory_context(
            f"nuclei vulnerability scanning templates {severity} severity"
        )

    require_docker_image()

    # Build nuclei command
    cmd = ["nuclei", "-target", target]

    # Add severity filter
    if severity:
        cmd.extend(["-severity", severity])

    # Add rate limiting
    cmd.extend(["-rate-limit", str(rate_limit)])

    # Add templates if specified
    if templates:
        if Path(templates).exists():
            # Mount template directory
            cmd.extend(["-templates", "/templates"])
        else:
            # Use template name/tag
            cmd.extend(["-templates", templates])

    # Add output format
    cmd.extend(["-json"])

    console.print(f"[dim]Command: {' '.join(cmd)}[/dim]")

    try:
        # Determine if we need to mount templates
        template_path = None
        if templates and Path(templates).exists():
            template_path = str(Path(templates).resolve())

        result = run_in_docker(
            cmd,
            target_path=template_path,
            network="host",  # Nuclei needs network access
        )

        if result.returncode == 0:
            console.print("[green]Nuclei scan complete![/green]")
            if result.stdout:
                console.print(result.stdout)
            if not result.stdout.strip():
                console.print("[green]No vulnerabilities found.[/green]")
        else:
            if result.stdout:
                console.print(result.stdout)
            if result.stderr:
                console.print(f"[dim]{result.stderr}[/dim]")

        if output:
            Path(output).write_text(result.stdout or "")
            console.print(f"[dim]Results saved to: {output}[/dim]")

    except subprocess.TimeoutExpired:
        console.print("[red]Scan timed out (10 min limit)[/red]")
        sys.exit(1)


def nuclei_update_command():
    """
    Update Nuclei templates to the latest version.
    """
    console.print("[bold cyan]Updating Nuclei templates...[/bold cyan]")
    console.print("[dim]Running in isolated Docker container...[/dim]")

    require_docker_image()

    cmd = ["nuclei", "-update-templates"]

    try:
        result = run_in_docker(cmd, network="bridge")

        if result.returncode == 0:
            console.print("[green]Templates updated successfully![/green]")
            if result.stdout:
                console.print(result.stdout)
        else:
            console.print(f"[red]Update failed:[/red]\n{result.stderr}")

    except subprocess.TimeoutExpired:
        console.print("[red]Update timed out[/red]")
        sys.exit(1)


def nuclei_list_templates_command(
    tags: str | None = None,
    severity: str | None = None,
):
    """
    List available Nuclei templates.

    Args:
        tags: Filter by tags (comma-separated)
        severity: Filter by severity
    """
    console.print("[bold cyan]Listing Nuclei templates...[/bold cyan]")

    require_docker_image()

    cmd = ["nuclei", "-tl"]

    if tags:
        cmd.extend(["-tags", tags])
    if severity:
        cmd.extend(["-severity", severity])

    try:
        result = run_in_docker(cmd, network="none")

        if result.returncode == 0 and result.stdout:
            console.print(result.stdout)
        else:
            console.print("[yellow]No templates found matching criteria[/yellow]")

    except subprocess.TimeoutExpired:
        console.print("[red]Command timed out[/red]")
        sys.exit(1)


def create_nuclei_typer_command() -> Callable[..., None]:
    """Create a typer command wrapper for nuclei_command."""

    def nuclei(
        target: str = typer.Argument(..., help="Target URL or file with URLs"),
        templates: str = typer.Option(
            None, help="Template directory or specific template"
        ),
        severity: str = typer.Option(
            "medium,high,critical",
            help="Severity filter (comma-separated)",
        ),
        rate_limit: int = typer.Option(
            150, help="Maximum requests per second"
        ),
        output: str = typer.Option(None, help="Output file path"),
        recall: bool = typer.Option(
            True, help="Query memory for prior knowledge"
        ),
    ):
        """
        Run template-based vulnerability scanning using Nuclei.

        ALL scanning runs in an isolated Docker container for security.
        Nuclei uses community-maintained templates to detect vulnerabilities,
        misconfigurations, and security issues.
        """
        nuclei_command(target, templates, severity, rate_limit, output, recall)

    return nuclei


def create_nuclei_update_typer_command() -> Callable[..., None]:
    """Create a typer command wrapper for nuclei_update_command."""

    def nuclei_update():
        """Update Nuclei templates to the latest version."""
        nuclei_update_command()

    return nuclei_update


def create_nuclei_list_typer_command() -> Callable[..., None]:
    """Create a typer command wrapper for nuclei_list_templates_command."""

    def nuclei_list(
        tags: str = typer.Option(None, help="Filter by tags (comma-separated)"),
        severity: str = typer.Option(None, help="Filter by severity"),
    ):
        """List available Nuclei templates."""
        nuclei_list_templates_command(tags, severity)

    return nuclei_list

# Explicit module exports for clarity
__all__ = [
    "nuclei_command",
    "nuclei_update_command",
    "nuclei_list_templates_command",
    "create_nuclei_typer_command",
    "create_nuclei_update_typer_command",
    "create_nuclei_list_typer_command",
]
