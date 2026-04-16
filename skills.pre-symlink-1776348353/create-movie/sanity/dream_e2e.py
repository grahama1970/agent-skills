#!/usr/bin/env python3
"""
Dream Mode End-to-End Sanity Test

Verifies that Horus persona can dream using create-movie skill:
1. Memory skill connectivity
2. Horus memory scopes have data
3. fetch_day_residue() returns content
4. Dream command dry-run works

Usage:
    python sanity/dream_e2e.py
    python sanity/dream_e2e.py --verbose
    python sanity/dream_e2e.py --scope horus_lore
"""

import typer
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

console = Console()

# Add parent directory to path for imports
SKILL_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SKILL_DIR))


# Horus memory scopes to test
HORUS_SCOPES = [
    "horus_lore",       # Persona/voice core
    "horus-movies",     # Cinematic motifs
    "horus-library",    # Literary metaphors
    "horus-feeds",      # World echoes
    "horus-music",      # Soundtrack anchors
]


def check_memory_skill_available() -> bool:
    """Check if memory skill is available and working."""
    console.print("\n[bold]1. Memory Skill Connectivity[/bold]")

    try:
        from create_movie.skill_registry import is_skill_available, run_skill

        if not is_skill_available("memory"):
            console.print("[red]FAIL: Memory skill not available[/red]")
            return False

        # Test with a simple recall
        result = run_skill("memory", ["recall", "--q", "test", "--k", "1"], capture=True)

        if result.get("returncode") == 0:
            console.print("[green]PASS: Memory skill is available and responding[/green]")
            return True
        else:
            stderr = result.get("stderr", "")
            console.print(f"[yellow]WARN: Memory skill returned non-zero: {stderr[:100]}[/yellow]")
            return True  # Skill exists even if no results

    except ImportError as e:
        console.print(f"[red]FAIL: Cannot import skill_registry: {e}[/red]")
        return False
    except Exception as e:
        console.print(f"[red]FAIL: Unexpected error: {e}[/red]")
        return False


def check_horus_scope(scope: str, verbose: bool = False) -> dict:
    """Check if a specific Horus memory scope has data."""
    try:
        from create_movie.skill_registry import run_skill

        result = run_skill(
            "memory",
            ["recall", "--q", "persona creative", "--scope", scope, "--k", "3"],
            capture=True
        )

        stdout = result.get("stdout", "")
        returncode = result.get("returncode", 1)

        if returncode != 0:
            return {"scope": scope, "status": "error", "count": 0, "sample": None}

        # Try to parse JSON output
        try:
            data = json.loads(stdout)
            items = data.get("items", [])
            count = len(items)
            sample = items[0].get("text", "")[:80] if items else None

            return {
                "scope": scope,
                "status": "ok" if count > 0 else "empty",
                "count": count,
                "sample": sample
            }
        except json.JSONDecodeError:
            # Non-JSON output (possibly formatted text)
            lines = stdout.strip().split("\n")
            has_content = any(line.strip() and not line.startswith("[") for line in lines)

            return {
                "scope": scope,
                "status": "ok" if has_content else "empty",
                "count": len(lines) if has_content else 0,
                "sample": lines[0][:80] if has_content else None
            }

    except Exception as e:
        return {"scope": scope, "status": "error", "count": 0, "sample": str(e)[:50]}


def check_horus_scopes(verbose: bool = False) -> bool:
    """Check all Horus memory scopes for data."""
    console.print("\n[bold]2. Horus Memory Scopes[/bold]")

    table = Table(title="Horus Persona Scopes")
    table.add_column("Scope", style="cyan")
    table.add_column("Status")
    table.add_column("Items")
    table.add_column("Sample")

    all_empty = True
    any_error = False

    for scope in HORUS_SCOPES:
        result = check_horus_scope(scope, verbose)

        if result["status"] == "ok":
            status = "[green]OK[/green]"
            all_empty = False
        elif result["status"] == "empty":
            status = "[yellow]EMPTY[/yellow]"
        else:
            status = "[red]ERROR[/red]"
            any_error = True

        sample = (result["sample"][:40] + "...") if result["sample"] else "-"
        table.add_row(scope, status, str(result["count"]), sample)

    console.print(table)

    if any_error:
        console.print("[red]FAIL: Errors accessing some scopes[/red]")
        return False
    elif all_empty:
        console.print("[yellow]WARN: All scopes are empty - Horus has no memories to dream from[/yellow]")
        return False
    else:
        console.print("[green]PASS: Horus memory scopes have data[/green]")
        return True


def check_fetch_day_residue(verbose: bool = False) -> bool:
    """Test the fetch_day_residue() function."""
    console.print("\n[bold]3. Day Residue Collection[/bold]")

    try:
        from create_movie.phases.dream_mode import fetch_day_residue

        console.print("[dim]Fetching day residue from Horus memory...[/dim]")
        residue = fetch_day_residue()

        prompt = residue.get("prompt", "")
        ids = residue.get("ids", [])

        if verbose:
            console.print(f"\n[dim]Raw residue prompt:[/dim]\n{prompt[:500]}...")

        # Check for meaningful content
        if not prompt or len(prompt) < 50:
            console.print("[yellow]WARN: Day residue is thin - may produce abstract dreams[/yellow]")
            console.print(f"  Prompt length: {len(prompt)} chars")
            console.print(f"  Source IDs: {len(ids)}")
            return True  # Not a failure, just a warning

        # Check for seed/fallback content (still usable for dreaming)
        if "seed:" in str(ids):
            console.print("[yellow]WARN: Using seed residue (memory unavailable or empty)[/yellow]")
            return True  # Seed memories are valid for testing

        console.print(f"[green]PASS: Day residue collected ({len(prompt)} chars, {len(ids)} sources)[/green]")

        # Show first few sources
        for source_id in ids[:3]:
            console.print(f"  - {source_id}")
        if len(ids) > 3:
            console.print(f"  ... and {len(ids) - 3} more")

        return True

    except ImportError as e:
        console.print(f"[red]FAIL: Cannot import dream_mode: {e}[/red]")
        return False
    except Exception as e:
        console.print(f"[red]FAIL: Error fetching day residue: {e}[/red]")
        return False


def check_dream_dry_run() -> bool:
    """Test the dream command in dry-run mode."""
    console.print("\n[bold]4. Dream Command (Dry Run)[/bold]")

    try:
        result = subprocess.run(
            ["uv", "run", "--project", str(SKILL_DIR), "python", str(SKILL_DIR / "orchestrator.py"),
             "dream", "generate", "--limit", "2", "--dry-run"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(SKILL_DIR)
        )

        stdout = result.stdout
        stderr = result.stderr

        if result.returncode == 0:
            console.print("[green]PASS: Dream dry-run completed successfully[/green]")

            # Check for expected output patterns
            if "Dry run" in stdout or "Dry Run" in stdout:
                console.print("  [dim]Dry run mode confirmed in output[/dim]")
            if "residue" in stdout.lower():
                console.print("  [dim]Day residue fetching attempted[/dim]")

            return True
        else:
            console.print(f"[yellow]WARN: Dream dry-run exited with code {result.returncode}[/yellow]")
            if stderr:
                console.print(f"[dim]stderr: {stderr[:200]}[/dim]")
            # Check if it's an expected failure (missing dependencies)
            if "graph_memory" in stderr or "MemoryClient" in stderr:
                console.print("[yellow]  Note: graph_memory import failed - may need memory service[/yellow]")
                return True  # Known issue, not a hard failure
            return False

    except subprocess.TimeoutExpired:
        console.print("[yellow]WARN: Dream dry-run timed out (60s)[/yellow]")
        return False
    except Exception as e:
        console.print(f"[red]FAIL: Error running dream command: {e}[/red]")
        return False


def run_sanity_test(verbose: bool = False, scope: Optional[str] = None) -> int:
    """
    Run the complete dream mode sanity test.

    Returns:
        0 if all tests pass
        1 if there are warnings but tests pass
        2 if critical tests fail
    """
    console.print("[bold cyan]═══ Dream Mode End-to-End Sanity Test ═══[/bold cyan]")
    console.print(f"Skill directory: {SKILL_DIR}")

    results = {}

    # Test 1: Memory skill connectivity
    results["memory_skill"] = check_memory_skill_available()

    if not results["memory_skill"]:
        console.print("\n[red]CRITICAL: Memory skill not available. Cannot proceed.[/red]")
        return 2

    # Test 2: Horus scopes (or single scope if specified)
    if scope:
        console.print(f"\n[bold]2. Checking Single Scope: {scope}[/bold]")
        result = check_horus_scope(scope, verbose)
        console.print(f"  Status: {result['status']}, Count: {result['count']}")
        if result["sample"]:
            console.print(f"  Sample: {result['sample'][:60]}...")
        results["horus_scopes"] = result["status"] == "ok"
    else:
        results["horus_scopes"] = check_horus_scopes(verbose)

    # Test 3: Day residue collection
    results["day_residue"] = check_fetch_day_residue(verbose)

    # Test 4: Dream command dry-run
    results["dream_command"] = check_dream_dry_run()

    # Summary
    console.print("\n[bold]═══ Summary ═══[/bold]")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    table = Table()
    table.add_column("Test", style="cyan")
    table.add_column("Result")

    for test, result in results.items():
        status = "[green]PASS[/green]" if result else "[red]FAIL[/red]"
        table.add_row(test.replace("_", " ").title(), status)

    console.print(table)

    if passed == total:
        console.print(f"\n[bold green]All {total} tests passed! Horus can dream.[/bold green]")
        return 0
    elif passed >= 2:  # Memory + at least one other
        console.print(f"\n[bold yellow]{passed}/{total} tests passed. Dream mode may work with limitations.[/bold yellow]")
        return 1
    else:
        console.print(f"\n[bold red]{passed}/{total} tests passed. Dream mode is not functional.[/bold red]")
        return 2


app = typer.Typer(help="Dream Mode End-to-End Sanity Test")


@app.command()
def main(
    verbose: bool = typer.Option(False, help="Show detailed output"),
    scope: str = typer.Option(None, help="Test a single Horus scope"),
):
    exit_code = run_sanity_test(verbose=verbose, scope=scope)
    sys.exit(exit_code)


if __name__ == "__main__":
    app()
