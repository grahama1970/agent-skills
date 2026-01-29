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
if str(SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR.parent))

# Import from modular components
from hack.container_manager import display_tools_status
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
)

app = typer.Typer(help="Automated security auditing and ethical hacking tools.")

# Register tool commands (core security tools)
app.command()(create_scan_typer_command())
app.command()(create_audit_typer_command())
app.command()(create_sca_typer_command())
app.command(name="nuclei")(create_nuclei_typer_command())
app.command(name="nuclei-update")(create_nuclei_update_typer_command())
app.command(name="nuclei-list")(create_nuclei_list_typer_command())

# Register additional commands (skill integrations)
app.command()(create_learn_command())
app.command()(create_research_command())
app.command()(create_process_command())
app.command()(create_prove_command())
app.command()(create_exploit_command())
app.command()(create_harden_command())
app.command(name="docker-cleanup")(create_docker_cleanup_command())
app.command()(create_symbols_command())
app.command()(create_classify_command())
app.command()(create_remember_command())
app.command()(create_recall_command())


@app.command()
def tools() -> None:
    """List available security tools and Docker image status."""
    display_tools_status()


if __name__ == "__main__":
    app()

# Explicit module exports for clarity
__all__ = ["app"]
