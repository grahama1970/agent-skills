"""
Battle Skill - GDB Support
GDB remote debugging support for QEMU-emulated firmware battles.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from rich.console import Console

from qemu_support import parse_qemu_config

console = Console()


def get_gdb_connection_info(
    battle_id: str,
    team: str,
    worktree_base: Path
) -> dict[str, Any] | None:
    """
    Get GDB connection information for a team's QEMU instance.

    Args:
        battle_id: Battle identifier
        team: Team name
        worktree_base: Base path for team worktrees

    Returns:
        Dict with host, port, machine, symbol_file, and container name
    """
    team_dir = worktree_base / team
    config = parse_qemu_config(team_dir)

    if not config:
        return None

    gdb_port = int(config.get('gdb_port', '5000'))
    machine = config.get('machine', 'arm')

    # Look for ELF file with debug symbols
    symbol_file = None
    for ext in ['.elf', '.axf', '.out']:
        candidates = list(team_dir.glob(f"*{ext}"))
        if candidates:
            symbol_file = candidates[0]
            break

    return {
        'host': 'localhost',
        'port': gdb_port,
        'machine': machine,
        'symbol_file': str(symbol_file) if symbol_file else None,
        'container': f"battle_{battle_id}_{team}",
    }


def generate_gdb_script(
    battle_id: str,
    team: str,
    worktree_base: Path,
    symbol_file: Path | None = None,
    breakpoints: list[str] | None = None
) -> str:
    """
    Generate a GDB script for connecting to a team's QEMU instance.

    Args:
        battle_id: Battle identifier
        team: Team name
        worktree_base: Base path for team worktrees
        symbol_file: Optional ELF file with debug symbols
        breakpoints: Optional list of breakpoint locations (function names or addresses)

    Returns:
        GDB script content that can be run with 'gdb -x script.gdb'
    """
    info = get_gdb_connection_info(battle_id, team, worktree_base)
    if not info:
        return ""

    script_lines = [
        "# Auto-generated GDB script for battle skill",
        f"# Team: {team}",
        f"# Architecture: {info['machine']}",
        "",
        "set pagination off",
        "set confirm off",
        "",
        f"target remote {info['host']}:{info['port']}",
    ]

    # Load symbols if available
    sym_file = symbol_file or info.get('symbol_file')
    if sym_file:
        script_lines.extend([
            "",
            "# Load debug symbols",
            f"file {sym_file}",
        ])

    # Add breakpoints
    if breakpoints:
        script_lines.append("")
        script_lines.append("# Breakpoints")
        for bp in breakpoints:
            script_lines.append(f"break {bp}")

    # Add useful commands
    script_lines.extend([
        "",
        "# Useful commands:",
        "# info registers - show CPU registers",
        "# x/10i $pc - disassemble at program counter",
        "# continue - resume execution",
        "# stepi - single step instruction",
    ])

    return "\n".join(script_lines)


def test_gdb_connection(
    battle_id: str,
    team: str,
    worktree_base: Path
) -> bool:
    """
    Test GDB connection to a team's QEMU instance.

    Verifies:
    - GDB connects successfully
    - Registers are readable

    Returns:
        True if connection successful and registers readable
    """
    info = get_gdb_connection_info(battle_id, team, worktree_base)
    if not info:
        console.print(f"[red]No GDB info for {team}[/red]")
        return False

    console.print(f"[cyan]Testing GDB connection for {team}...[/cyan]")
    console.print(f"  Target: localhost:{info['port']} (inside container)")

    container_name = info['container']

    # Run GDB inside the container where it's available
    gdb_args = [
        "gdb-multiarch", "-batch",
        "-ex", f"target remote localhost:{info['port']}",
        "-ex", "info registers",
    ]

    try:
        result = subprocess.run(
            ["docker", "exec", container_name, *gdb_args],
            capture_output=True, text=True, timeout=30
        )

        if result.stdout:
            # Check if we got register output
            if any(reg in result.stdout.lower() for reg in ['r0', 'sp', 'pc', 'rax', 'eax', 'ra']):
                console.print(f"  [green]GDB connected, registers readable[/green]")
                # Show a sample of register output
                lines = result.stdout.strip().split('\n')[:5]
                for line in lines:
                    console.print(f"    {line}")
                return True

        console.print(f"[red]GDB connection failed: {result.stderr}[/red]")
        return False

    except subprocess.TimeoutExpired:
        console.print("[red]GDB connection timed out[/red]")
        return False
    except Exception as e:
        console.print(f"[red]GDB test failed: {e}[/red]")
        return False


def set_gdb_breakpoint(
    battle_id: str,
    team: str,
    worktree_base: Path,
    location: str,
    symbol_file: Path | None = None
) -> bool:
    """
    Set a GDB breakpoint in a team's QEMU instance.

    Supports:
    - Load ELF symbols if available
    - Set breakpoint on function or address
    - Verify breakpoint was set

    Args:
        battle_id: Battle identifier
        team: Team name
        worktree_base: Base path for team worktrees
        location: Breakpoint location (function name or address like '0x8000')
        symbol_file: Optional ELF file with symbols

    Returns:
        True if breakpoint set successfully
    """
    info = get_gdb_connection_info(battle_id, team, worktree_base)
    if not info:
        return False

    container_name = info['container']

    # Build GDB command as argument list (no shell)
    gdb_args = [
        "gdb-multiarch", "-batch",
        "-ex", f"target remote localhost:{info['port']}",
    ]

    # Load symbols if provided
    sym_file = symbol_file or info.get('symbol_file')
    if sym_file:
        # Map symbol file path to container path if needed
        container_sym = f"/battle/firmware/{Path(sym_file).name}" if sym_file else None
        if container_sym:
            gdb_args.extend(["-ex", f"file {container_sym}"])

    # Set breakpoint
    gdb_args.extend(["-ex", f"break {location}"])

    # Show breakpoints
    gdb_args.extend(["-ex", "info breakpoints"])

    try:
        result = subprocess.run(
            ["docker", "exec", container_name, *gdb_args],
            capture_output=True, text=True, timeout=30
        )

        if "Breakpoint" in result.stdout:
            console.print(f"  [green]Breakpoint set at {location}[/green]")
            return True
        else:
            console.print(f"[yellow]Breakpoint may not have been set: {result.stdout}[/yellow]")
            return False

    except Exception as e:
        console.print(f"[red]Failed to set breakpoint: {e}[/red]")
        return False
