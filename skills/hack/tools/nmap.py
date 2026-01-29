"""
Nmap network scanning tool integration.

This module provides network vulnerability scanning using nmap
running in an isolated Docker container.
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


def scan_command(
    target: str,
    ports: str = "1-1000",
    scan_type: str = "basic",
    output: str | None = None,
    recall: bool = True,
):
    """
    Run network vulnerability scan on the target using nmap.

    ALL scanning runs in an isolated Docker container for security.

    Args:
        target: Target IP or hostname to scan
        ports: Port range to scan (e.g., '22,80,443' or '1-1000')
        scan_type: Scan type - basic, service, or vuln
        output: Output file path for results
        recall: Whether to query memory for prior scanning knowledge

    Scan types:
        basic   - Host discovery and port scan (-sS -sV)
        service - Service/version detection (-sV -sC)
        vuln    - Vulnerability scripts (--script vuln)
    """
    console.print(
        f"[bold cyan]Starting {scan_type} scan on target:[/bold cyan] {target}"
    )
    console.print("[dim]Running in isolated Docker container...[/dim]")

    # Memory recall for relevant scanning techniques
    if recall:
        show_memory_context(
            f"nmap scanning techniques for {scan_type} scan port {ports}"
        )

    require_docker_image()

    # Build nmap command based on scan type
    cmd = ["nmap"]

    if scan_type == "basic":
        cmd.extend(["-sS", "-sV", "-p", ports])
    elif scan_type == "service":
        cmd.extend(["-sV", "-sC", "-p", ports])
    elif scan_type == "vuln":
        cmd.extend(["-sV", "--script", "vuln", "-p", ports])
    else:
        console.print(f"[red]Unknown scan type: {scan_type}[/red]")
        sys.exit(1)

    cmd.append(target)

    console.print(f"[dim]Command: {' '.join(cmd)}[/dim]")

    try:
        result = run_in_docker(cmd, network="host")

        if result.returncode == 0:
            console.print("[green]Scan complete![/green]")
            console.print(result.stdout)
            if result.stderr:
                console.print(f"[dim]{result.stderr}[/dim]")
            if output:
                # Save output to file
                Path(output).write_text(result.stdout)
                console.print(f"[dim]Results saved to: {output}[/dim]")
        else:
            console.print(f"[red]Scan failed:[/red]\n{result.stderr}")
            sys.exit(1)

    except subprocess.TimeoutExpired:
        console.print("[red]Scan timed out (10 min limit)[/red]")
        sys.exit(1)


def create_scan_typer_command() -> Callable[..., None]:
    """Create a typer command wrapper for scan_command."""

    def scan(
        target: str = typer.Argument(..., help="Target IP or hostname to scan"),
        ports: str = typer.Option(
            "1-1000", help="Port range to scan (e.g., '22,80,443' or '1-1000')"
        ),
        scan_type: str = typer.Option(
            "basic", help="Scan type: basic, service, vuln"
        ),
        output: str = typer.Option(
            None, help="Output file path for results (XML format)"
        ),
        recall: bool = typer.Option(
            True, help="Query memory for prior scanning knowledge"
        ),
    ):
        """
        Run network vulnerability scan on the target using nmap.

        ALL scanning runs in an isolated Docker container for security.

        Scan types:
          basic   - Host discovery and port scan (-sS -sV)
          service - Service/version detection (-sV -sC)
          vuln    - Vulnerability scripts (--script vuln)
        """
        scan_command(target, ports, scan_type, output, recall)

    return scan

# Explicit module exports for clarity
__all__ = ["scan_command", "create_scan_typer_command"]
