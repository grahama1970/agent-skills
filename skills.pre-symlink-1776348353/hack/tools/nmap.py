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
    profile: str = "hobbyist",
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
    from hack.cache import get_cached_result, cache_result
    
    # Check cache first (unless --no-cache specified)
    cache_params = {"ports": ports, "scan_type": scan_type}
    cached = get_cached_result("scan", target, **cache_params)
    
    if cached:
        age_minutes = int(cached["age"].total_seconds() / 60)
        console.print(
            f"[dim]✓ Using cached result ({age_minutes}m old, 24h TTL)[/dim]"
        )
        console.print(cached["result"])
        if output:
            Path(output).write_text(cached["result"])
            console.print(f"[dim]Results saved to: {output}[/dim]")
        return
    
    from hack.utils import start_task_session, end_task_session, add_task_accomplishment
    
    console.print(
        f"[bold cyan]Starting {scan_type} scan on target:[/bold cyan] {target}"
    )
    console.print(f"[dim]Profile: {profile}[/dim]")
    console.print("[dim]Running in isolated Docker container...[/dim]")
    add_task_accomplishment(f"Starting {scan_type} nmap scan on {target} ({profile})")

    # Memory recall for relevant scanning techniques
    if recall:
        show_memory_context(
            f"nmap scanning techniques for {scan_type} scan port {ports}"
        )

    require_docker_image()

    # Build nmap command based on scan type
    cmd = ["nmap"]

    from hack.config import THREAT_PROFILES
    profile_cfg = THREAT_PROFILES.get(profile, THREAT_PROFILES["hobbyist"])
    timing = profile_cfg.get("nmap_timing", "-T3")

    if scan_type == "basic":
        cmd.extend(["-sS", "-sV", timing, "-p", ports])
    elif scan_type == "service":
        cmd.extend(["-sV", "-sC", timing, "-p", ports])
    elif scan_type == "vuln":
        cmd.extend(["-sV", timing, "--script", "vuln", "-p", ports])
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
            
            # Cache successful result
            cache_result("scan", target, result.stdout, **cache_params)
            
            if result.returncode == 0 and result.stderr:
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
        profile: str = typer.Option(
            "hobbyist", help="Threat profile: script-kiddie, hobbyist, organized-crime, state-actor"
        ),
        output: str = typer.Option(
            None, help="Output file path for results (XML format)"
        ),
        recall: bool = typer.Option(
            True, help="Query memory for prior scanning knowledge"
        ),
        no_cache: bool = typer.Option(
            False, "--no-cache", help="Skip cache lookup and force fresh scan"
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
        from hack.utils import start_task_session, end_task_session
        start_task_session(project=f"nmap-{target}")
        
        # Disable cache if --no-cache flag set
        if no_cache:
            # Temporarily patch cache to always return None
            import hack.cache
            original_get = hack.cache.get_cached_result
            hack.cache.get_cached_result = lambda *args, **kwargs: None
            try:
                scan_command(target, ports, scan_type, profile, output, recall)
            finally:
                hack.cache.get_cached_result = original_get
        else:
            scan_command(target, ports, scan_type, profile, output, recall)
            
        end_task_session(notes=f"Nmap scan complete for {target}")

    return scan

# Explicit module exports for clarity
__all__ = ["scan_command", "create_scan_typer_command"]
