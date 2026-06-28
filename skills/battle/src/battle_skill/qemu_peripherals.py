"""
Battle Skill - QEMU Peripherals
Peripheral configuration, MMIO logging, and overlay management for QEMU battles.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console()


def parse_qemu_config(team_dir: Path) -> dict[str, str]:
    """
    Parse QEMU configuration from team directory.

    Args:
        team_dir: Path to team directory

    Returns:
        Dict of config key-value pairs
    """
    qemu_config = team_dir / "qemu.conf"
    if not qemu_config.exists():
        return {}

    config = {}
    for line in qemu_config.read_text().strip().split('\n'):
        if '=' in line and not line.startswith('#'):
            key, val = line.split('=', 1)
            config[key] = val

    return config


def configure_peripheral_stubs(
    worktree_base: Path,
    team: str,
    stub_config: dict[str, Any] | None = None
) -> bool:
    """
    Configure peripheral stubs for a team's QEMU instance.

    Args:
        worktree_base: Base path for team worktrees
        team: Team name (red, blue, arena)
        stub_config: Optional custom stub configuration

    Returns:
        True if configuration was written successfully
    """
    team_dir = worktree_base / team

    # Default stub configuration
    default_config = {
        "uart": True,
        "timer": True,
        "irq": True,
        "watchdog": False,
        "mmio_log": False,
    }

    config = {**default_config, **(stub_config or {})}

    stub_file = team_dir / "peripheral_stubs.json"
    stub_file.write_text(json.dumps(config, indent=2))

    console.print(f"  [green]Configured peripheral stubs for {team}[/green]")
    return True


def enable_mmio_logging(worktree_base: Path, team: str) -> Path | None:
    """
    Enable MMIO logging for a team's QEMU instance.

    Logs all memory-mapped I/O accesses to help debug boot failures.

    Args:
        worktree_base: Base path for team worktrees
        team: Team name

    Returns:
        Path to MMIO log file, or None if failed
    """
    team_dir = worktree_base / team
    mmio_log = team_dir / "mmio.log"

    # Update stub config to enable MMIO logging
    stub_file = team_dir / "peripheral_stubs.json"
    if stub_file.exists():
        config = json.loads(stub_file.read_text())
    else:
        config = {}

    config["mmio_log"] = True
    config["mmio_log_path"] = str(mmio_log)
    stub_file.write_text(json.dumps(config, indent=2))

    console.print(f"  [green]MMIO logging enabled for {team}: {mmio_log}[/green]")
    return mmio_log


def read_mmio_log(battle_id: str, team: str, worktree_base: Path, tail_lines: int = 50) -> str:
    """
    Read MMIO log entries for a team.

    Args:
        battle_id: Battle identifier
        team: Team name
        worktree_base: Base path for team worktrees
        tail_lines: Number of recent lines to return

    Returns:
        MMIO log content
    """
    team_dir = worktree_base / team
    mmio_log = team_dir / "mmio.log"

    if not mmio_log.exists():
        return "MMIO log not found (enable with enable_mmio_logging first)"

    container_name = f"battle_{battle_id}_{team}"

    try:
        result = subprocess.run(
            ["docker", "exec", container_name, "tail", f"-{tail_lines}", str(mmio_log)],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout if result.returncode == 0 else result.stderr
    except Exception as e:
        return f"Error reading MMIO log: {e}"


def create_qcow2_overlay(
    battle_id: str,
    team: str,
    worktree_base: Path,
    overlay_name: str = "patched"
) -> Path | None:
    """
    Create a QCOW2 overlay for Blue team patching.

    Overlays allow non-destructive modifications:
    - Original firmware preserved
    - Patches stored in overlay
    - Easy to discard/reset patches

    Args:
        battle_id: Battle identifier
        team: Team name (typically "blue")
        worktree_base: Base path for team worktrees
        overlay_name: Name for the overlay file

    Returns:
        Path to overlay file, or None on failure
    """
    team_dir = worktree_base / team
    base_disk = team_dir / f"{team}_disk.qcow2"
    overlay_path = team_dir / f"{overlay_name}.qcow2"

    container_name = f"battle_{battle_id}_{team}"

    try:
        result = subprocess.run(
            ["docker", "exec", container_name,
             "qemu-img", "create", "-f", "qcow2",
             "-b", str(base_disk), "-F", "qcow2",
             str(overlay_path)],
            capture_output=True, text=True
        )

        if result.returncode == 0:
            console.print(f"  [green]Created overlay: {overlay_path.name}[/green]")
            return overlay_path
        else:
            console.print(f"[red]Overlay creation failed: {result.stderr}[/red]")
            return None

    except Exception as e:
        console.print(f"[red]Overlay creation failed: {e}[/red]")
        return None
