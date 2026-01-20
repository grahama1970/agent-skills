#!/usr/bin/env python3
"""Lean4 theorem prover CLI via scillm.

Adheres to SCILLM_PAVED_PATH_CONTRACT.md.
Uses `scillm[certainly]` integration.

Usage:
    # Prove a claim
    python prove.py "Prove that n + 0 = n"

    # With tactic hints
    python prove.py "Prove n < n + 1" --tactics omega
"""
import asyncio
import json
import typer
from rich.console import Console

console = Console(stderr=True)

app = typer.Typer(add_completion=False, help="Lean4 theorem proving via scillm")

@app.command()
def prove(
    claim: str = typer.Argument(None, help="Claim to prove (natural language)"),
    tactics: str = typer.Option("", "--tactics", "-t", help="Comma-separated tactics"),
    timeout: int = typer.Option(120, "--timeout", help="Compile timeout (s)"),
    candidates: int = typer.Option(3, "--candidates", "-n", help="Number of proof candidates"),
    check: bool = typer.Option(False, "--check", help="Check availability"),
    json_out: bool = typer.Option(True, "--json/--no-json", help="Output JSON"),
):
    """Prove a mathematical claim using Lean4."""
    try:
        from scillm.integrations.certainly import (
            prove_requirement,
            is_available,
            check_lean_container,
        )
    except ImportError:
        err = {"ok": False, "error": "scillm[certainly] not installed."}
        if json_out:
            print(json.dumps(err))
        else:
            console.print(f"[red]{err['error']}[/red]")
        raise typer.Exit(1)

    if check:
        pkg = is_available()
        # check_lean_container might hang if docker is slow, use caution or async?
        # usually fast enough for CLI.
        ctr = check_lean_container() if pkg else False
        res = {
            "package": pkg,
            "container": ctr,
            "ready": pkg and ctr
        }
        if json_out:
            print(json.dumps(res, indent=2))
        else:
            console.print(f"Ready: {res['ready']} (Package={pkg}, Container={ctr})")
        raise typer.Exit(0 if res["ready"] else 1)

    if not claim:
        console.print("[red]Error: Claim required.[/red]")
        raise typer.Exit(1)

    tactic_list = [t.strip() for t in tactics.split(",")] if tactics else None

    async def _run():
        return await prove_requirement(
            requirement=claim,
            tactics=tactic_list,
            compile_timeout_s=timeout,
            num_candidates=candidates,
        )

    console.print(f"[blue]Proving: {claim}[/blue]")
    result = asyncio.run(_run())

    if json_out:
        # Simplified public output
        out = {
            "ok": result.get("ok"),
            "lean4_code": result.get("best", {}).get("lean4") if result.get("ok") else None,
            "error": result.get("error") if not result.get("ok") else None,
            "diagnosis": result.get("diagnosis", {}).get("diagnosis"),
        }
        print(json.dumps(out, indent=2))
    else:
        if result.get("ok"):
            console.print(f"[green]PROVED:[/green]\n{result['best']['lean4']}")
        else:
            console.print(f"[red]FAILED:[/red] {result.get('error') or result.get('diagnosis', {}).get('diagnosis')}")

    raise typer.Exit(0 if result.get("ok") else 1)

if __name__ == "__main__":
    app()
