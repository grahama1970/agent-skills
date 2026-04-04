"""
Battle Skill - AFL++ Fuzzing Integration
Coverage-guided fuzzing support for firmware/binary targets.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from config import SAFE_FILENAME_PATTERN
from loguru import logger

console = Console()


def start_afl_fuzzing(
    battle_id: str,
    team: str,
    worktree_base: Path,
    target_binary: str,
    input_corpus: str | None = None,
    timeout_ms: int = 1000,
    memory_limit_mb: int = 256
) -> bool:
    """
    Start AFL++ fuzzing for a team's target.

    Uses AFL++ QEMU mode for coverage-guided fuzzing without source.

    Args:
        battle_id: Battle identifier
        team: Team name (typically 'red' for attacks)
        worktree_base: Base path for team worktrees
        target_binary: Path to binary inside container
        input_corpus: Path to initial corpus (or None for empty)
        timeout_ms: Timeout per execution in milliseconds
        memory_limit_mb: Memory limit for fuzzed process

    Returns:
        True if fuzzing started successfully
    """
    container_name = f"battle_{battle_id}_{team}"
    team_dir = worktree_base / team

    # Ensure directories exist in container
    for dir_name in ["corpus", "crashes", "findings"]:
        subprocess.run(
            ["docker", "exec", container_name, "mkdir", "-p", f"/battle/{dir_name}"],
            capture_output=True
        )

    # Create initial corpus if needed (security: no shell, use docker cp)
    if not input_corpus:
        input_corpus = "/battle/corpus"
        # Check if corpus is empty without shell
        list_res = subprocess.run(
            ["docker", "exec", container_name, "ls", "-A", "/battle/corpus"],
            capture_output=True, text=True, timeout=10
        )
        if list_res.returncode != 0 or not list_res.stdout.strip():
            # Create seed file via docker cp (no shell injection)
            with tempfile.NamedTemporaryFile(mode='wb', delete=False) as tf:
                tf.write(b"AAAA")
                host_seed = tf.name
            try:
                subprocess.run(
                    ["docker", "cp", host_seed, f"{container_name}:/battle/corpus/seed_0"],
                    capture_output=True, text=True, timeout=10
                )
            finally:
                try:
                    os.unlink(host_seed)
                except Exception as e:
                    logger.debug("os failed: {}", e)

    # Build AFL++ command as argument list (no shell)
    # Using QEMU mode (-Q) for binary-only fuzzing
    afl_cmd = [
        "afl-fuzz",
        "-Q",  # QEMU mode
        "-i", input_corpus,
        "-o", "/battle/findings",
        "-t", str(timeout_ms),
        "-m", str(memory_limit_mb),
        "--", target_binary
    ]

    console.print(f"[red]Starting AFL++ fuzzing for {team}...[/red]")
    console.print(f"  Target: {target_binary}")
    console.print(f"  Corpus: {input_corpus}")

    # Start AFL++ in background inside container (no shell)
    result = subprocess.run(
        ["docker", "exec", "-d", container_name, *afl_cmd],
        capture_output=True, text=True
    )

    if result.returncode == 0:
        console.print(f"  [green]AFL++ started in container {container_name}[/green]")
        # Save fuzzing state
        (team_dir / ".afl_running").write_text(json.dumps({
            "target": target_binary,
            "started": datetime.now().isoformat(),
            "container": container_name
        }))
        return True
    else:
        console.print(f"[red]Failed to start AFL++: {result.stderr}[/red]")
        return False


def stop_afl_fuzzing(battle_id: str, team: str, worktree_base: Path) -> bool:
    """Stop AFL++ fuzzing for a team."""
    container_name = f"battle_{battle_id}_{team}"
    team_dir = worktree_base / team

    result = subprocess.run(
        ["docker", "exec", container_name, "pkill", "-f", "afl-fuzz"],
        capture_output=True
    )

    # Clean up state file
    state_file = team_dir / ".afl_running"
    if state_file.exists():
        state_file.unlink()

    console.print(f"[red]AFL++ stopped for {team}[/red]")
    return True


def get_fuzzing_stats(battle_id: str, team: str) -> dict[str, Any]:
    """
    Get AFL++ fuzzing statistics.

    Returns coverage %, execs/sec, crash count, etc.
    """
    container_name = f"battle_{battle_id}_{team}"

    try:
        # Read AFL++ stats file
        result = subprocess.run(
            ["docker", "exec", container_name, "cat", "/battle/findings/default/fuzzer_stats"],
            capture_output=True, text=True, timeout=10
        )

        if result.returncode != 0:
            return {"error": "Fuzzer not running or stats unavailable"}

        # Parse stats
        stats: dict[str, Any] = {}
        for line in result.stdout.strip().split('\n'):
            if ':' in line:
                key, val = line.split(':', 1)
                key = key.strip()
                val = val.strip()
                # Try to convert to number
                try:
                    stats[key] = int(val)
                except ValueError:
                    try:
                        stats[key] = float(val)
                    except ValueError:
                        stats[key] = val

        # Calculate coverage metrics
        if "bitmap_cvg" in stats:
            stats["coverage_percent"] = float(str(stats["bitmap_cvg"]).rstrip('%'))

        return stats

    except Exception as e:
        return {"error": str(e)}


def collect_crashes(battle_id: str, team: str) -> list[dict[str, Any]]:
    """
    Collect crash files from AFL++ output.

    Returns list of crash info with paths and metadata.
    """
    container_name = f"battle_{battle_id}_{team}"
    crashes: list[dict[str, Any]] = []

    try:
        # List crash files
        result = subprocess.run(
            ["docker", "exec", container_name, "ls", "-la", "/battle/findings/default/crashes/"],
            capture_output=True, text=True, timeout=10
        )

        if result.returncode != 0:
            return []

        # Parse file listing
        for line in result.stdout.strip().split('\n'):
            parts = line.split()
            if len(parts) >= 9 and parts[-1].startswith('id:'):
                filename = parts[-1]
                size = parts[4]
                crashes.append({
                    "filename": filename,
                    "path": f"/battle/findings/default/crashes/{filename}",
                    "size": size,
                    "team": team,
                })

        console.print(f"[red]Found {len(crashes)} crashes for {team}[/red]")
        return crashes

    except Exception as e:
        console.print(f"[red]Error collecting crashes: {e}[/red]")
        return []


def triage_crash(battle_id: str, team: str, crash_path: str) -> dict[str, Any]:
    """
    Triage a crash using GDB to get backtrace.

    Restores QEMU snapshot, feeds crash input, attaches GDB for analysis.
    """
    container_name = f"battle_{battle_id}_{team}"

    console.print(f"[cyan]Triaging crash: {crash_path}[/cyan]")

    try:
        # Use GDB to analyze the crash
        gdb_script = f"""set pagination off
set confirm off
run < {crash_path}
bt full
info registers
quit
"""
        # Write GDB script via docker cp (no shell injection)
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.gdb') as tf:
            tf.write(gdb_script)
            host_gdb_path = tf.name
        try:
            subprocess.run(
                ["docker", "cp", host_gdb_path, f"{container_name}:/tmp/triage.gdb"],
                capture_output=True, text=True, timeout=10
            )
        finally:
            try:
                os.unlink(host_gdb_path)
            except Exception as e:
                logger.debug("os failed: {}", e)

        # Run GDB with crash input
        result = subprocess.run(
            ["docker", "exec", container_name, "timeout", "30",
             "gdb-multiarch", "-batch", "-x", "/tmp/triage.gdb"],
            capture_output=True, text=True, timeout=60
        )

        # Parse backtrace
        triage_result: dict[str, Any] = {
            "crash_path": crash_path,
            "backtrace": "",
            "registers": "",
            "crash_address": None,
            "crash_function": None,
        }

        if result.stdout:
            lines = result.stdout.split('\n')

            for line in lines:
                if line.startswith('#'):
                    triage_result["backtrace"] += line + '\n'
                    if triage_result["crash_function"] is None and ' in ' in line:
                        triage_result["crash_function"] = line.split(' in ')[1].split()[0]
                elif any(reg in line.lower() for reg in ['r0', 'rax', 'eax', 'pc', 'rip']):
                    triage_result["registers"] += line + '\n'

        console.print(f"  [green]Crash function: {triage_result.get('crash_function', 'unknown')}[/green]")
        return triage_result

    except Exception as e:
        console.print(f"[red]Triage failed: {e}[/red]")
        return {"error": str(e)}


def add_to_corpus(
    battle_id: str,
    team: str,
    input_data: bytes,
    name: str | None = None
) -> bool:
    """
    Add a new input to the fuzzing corpus.

    Args:
        battle_id: Battle identifier
        team: Team name
        input_data: The input bytes to add
        name: Optional name for the corpus file

    Returns:
        True if added successfully
    """
    container_name = f"battle_{battle_id}_{team}"

    if name is None:
        name = f"seed_{int(time.time())}"

    # Sanitize filename to prevent path traversal
    if not re.fullmatch(SAFE_FILENAME_PATTERN, name):
        console.print(f"[red]Invalid corpus filename: {name}[/red]")
        return False

    try:
        # Write input via docker cp (no shell injection)
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as tf:
            tf.write(input_data)
            host_path = tf.name
        try:
            result = subprocess.run(
                ["docker", "cp", host_path, f"{container_name}:/battle/corpus/{name}"],
                capture_output=True, text=True, timeout=10
            )
        finally:
            try:
                os.unlink(host_path)
            except Exception as e:
                logger.debug("os failed: {}", e)

        if result.returncode == 0:
            console.print(f"  [green]Added to corpus: {name}[/green]")
            return True
        return False

    except Exception as e:
        console.print(f"[red]Failed to add to corpus: {e}[/red]")
        return False


def get_corpus_stats(battle_id: str, team: str) -> dict[str, Any]:
    """
    Get corpus statistics.

    Returns count, total size, and file list.
    """
    container_name = f"battle_{battle_id}_{team}"

    try:
        # Count files without shell
        list_res = subprocess.run(
            ["docker", "exec", container_name, "ls", "-1", "/battle/corpus"],
            capture_output=True, text=True, timeout=10
        )
        count = 0
        if list_res.returncode == 0 and list_res.stdout:
            count = len([ln for ln in list_res.stdout.strip().split("\n") if ln.strip()])

        # Get size without shell
        size_res = subprocess.run(
            ["docker", "exec", container_name, "du", "-sh", "/battle/corpus"],
            capture_output=True, text=True, timeout=10
        )
        size = "0"
        if size_res.returncode == 0 and size_res.stdout:
            size = size_res.stdout.strip().split()[0]

        return {
            "count": count,
            "total_size": size,
            "team": team
        }

    except Exception as e:
        return {"error": str(e)}


def sync_corpus_from_findings(battle_id: str, team: str) -> int:
    """
    Sync interesting inputs from AFL++ findings to corpus.

    This transfers new coverage-improving inputs to the corpus
    for future fuzzing runs.

    Returns:
        Number of new inputs synced
    """
    container_name = f"battle_{battle_id}_{team}"

    try:
        # List queue files without shell
        q_list = subprocess.run(
            ["docker", "exec", container_name, "ls", "-1", "/battle/findings/default/queue/"],
            capture_output=True, text=True, timeout=15
        )
        if q_list.returncode != 0:
            return 0

        # List existing corpus files
        c_list = subprocess.run(
            ["docker", "exec", container_name, "ls", "-1", "/battle/corpus/"],
            capture_output=True, text=True, timeout=15
        )

        queue_files = [ln for ln in q_list.stdout.strip().split("\n") if ln.strip()]
        corpus_files: set[str] = set()
        if c_list.returncode == 0 and c_list.stdout:
            corpus_files = set(ln for ln in c_list.stdout.strip().split("\n") if ln.strip())

        # Copy new files one by one (no shell glob)
        count = 0
        for fname in queue_files:
            if fname not in corpus_files:
                src = f"/battle/findings/default/queue/{fname}"
                dst = f"/battle/corpus/{fname}"
                cp_res = subprocess.run(
                    ["docker", "exec", container_name, "cp", src, dst],
                    capture_output=True, text=True, timeout=15
                )
                if cp_res.returncode == 0:
                    count += 1

        console.print(f"[green]Synced {count} new inputs to corpus for {team}[/green]")
        return count

    except Exception as e:
        console.print(f"[red]Failed to sync corpus: {e}[/red]")
        return 0
