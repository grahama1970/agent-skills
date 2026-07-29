#!/usr/bin/env python3
"""
Hack Skill - Automated security auditing and ethical hacking tools.

This is the thin CLI entry point that imports and assembles commands
from modular components. All security tools run in isolated Docker
containers for safety.

Modules:
- config.py: Constants and paths
- utils.py: Common utilities and memory integration
- container_manager.py: Docker container management
- commands.py: Additional CLI commands
- tools/nmap.py: Network scanning
- tools/semgrep.py: SAST and SCA
- tools/nuclei.py: Template-based vulnerability scanning
"""
from __future__ import annotations

import sys
from pathlib import Path

import typer

# Ensure hack package is importable
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR.parent))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import from modular components
from hack.container_manager import display_tools_status
from hack.cache import get_cache_stats, clear_cache, CACHE_DIR
from hack.tools.nmap import create_scan_typer_command
from hack.tools.semgrep import create_audit_typer_command, create_sca_typer_command
from hack.tools.nuclei import (
    create_nuclei_typer_command,
    create_nuclei_update_typer_command,
    create_nuclei_list_typer_command,
)
from hack.commands import (
    create_learn_command,
    create_research_command,
    create_process_command,
    create_prove_command,
    create_exploit_command,
    create_harden_command,
    create_docker_cleanup_command,
    create_symbols_command,
    create_classify_command,
    create_remember_command,
    create_recall_command,
    create_remediate_command,
    create_update_exploits_command,
)
from hack.session_audit import create_session_audit_command
from hack.chaos_campaign import create_chaos_campaign_command
from hack.battle_mode import create_battle_command
from hack.evolutionary_campaign import create_evolve_campaign_command, create_validate_seed_command
from hack.hack_scan_request import create_validate_scan_request_command
from hack.target_authorization import create_authorization_preflight_command
from hack.proof_authority import create_prove_proof_authority_command
from hack.compose_policy import create_compose_policy_command, create_compose_policy_matrix_command

from rich.console import Console

app = typer.Typer(help="Automated security auditing and ethical hacking tools.")
console = Console()

# Register tool commands (core security tools)
app.command()(create_scan_typer_command())
app.command()(create_audit_typer_command())
app.command()(create_sca_typer_command())
app.command(name="nuclei")(create_nuclei_typer_command())
app.command(name="nuclei-update")(create_nuclei_update_typer_command())
app.command(name="nuclei-list")(create_nuclei_list_typer_command())

# Cache management commands
@app.command(name="cache-stats")
def cache_stats_cmd():
    """Show cache statistics."""
    stats = get_cache_stats()
    console.print(f"\n[bold]Hack Skill Cache Statistics[/bold]")
    console.print(f"  Location: {CACHE_DIR}")
    console.print(f"  Total files: {stats['total_files']}")
    console.print(f"  Total size: {stats['total_size_mb']} MB")
    if stats['oldest']:
        console.print(f"  Oldest entry: {stats['oldest'].strftime('%Y-%m-%d %H:%M')}")
    if stats['newest']:
        console.print(f"  Newest entry: {stats['newest'].strftime('%Y-%m-%d %H:%M')}")
    console.print()

@app.command(name="clear-cache")
def clear_cache_cmd(
    command: str = typer.Option(None, help="Clear only this command's cache"),
    target: str = typer.Option(None, help="Clear only this target's cache"),
    all: bool = typer.Option(False, "--all", help="Clear entire cache"),
):
    """Clear cached results."""
    if not all and not command and not target:
        console.print("[yellow]Specify --all, --command, or --target[/yellow]")
        return

    removed = clear_cache(command=command, target=target)
    console.print(f"[green]✓ Removed {removed} cache entries[/green]")

# Register additional commands (skill integrations)
app.command()(create_learn_command())
app.command()(create_research_command())
app.command()(create_process_command())
app.command()(create_prove_command())
app.command()(create_exploit_command())
app.command()(create_harden_command())
app.command(name="docker-cleanup")(create_docker_cleanup_command())
app.command(name="symbols")(create_symbols_command())
app.command(name="classify")(create_classify_command())
app.command(name="remember")(create_remember_command())
app.command(name="recall")(create_recall_command())
app.command(name="remediate")(create_remediate_command())
app.command(name="update-exploits")(create_update_exploits_command())
app.command(name="session-audit")(create_session_audit_command())
app.command(name="chaos-campaign", hidden=True)(create_chaos_campaign_command())
app.command(name="evolve-campaign")(create_evolve_campaign_command())
app.command(name="battle")(create_battle_command())
app.command(name="validate-seed")(create_validate_seed_command())
app.command(name="validate-scan-request")(create_validate_scan_request_command())
app.command(name="authorization-preflight")(create_authorization_preflight_command())
app.command(name="prove-proof-authority")(create_prove_proof_authority_command())
app.command(name="compose-policy")(create_compose_policy_command())
app.command(name="compose-policy-matrix")(create_compose_policy_matrix_command())


@app.command()
def tools() -> None:
    """List available security tools and Docker image status."""
    display_tools_status()


if __name__ == "__main__":
    app()

# Explicit module exports for clarity
__all__ = ["app"]
