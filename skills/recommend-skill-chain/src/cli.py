"""Typer CLI for recommend-skill-chain."""

from __future__ import annotations

import json
import sys
from typing import Annotated, Optional

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from . import recommender

app = typer.Typer(
    name="recommend-skill-chain",
    help="Shadow-LEGO cascade recommender for skill chain composition.",
    no_args_is_help=True,
)
console = Console()

# Configure loguru
logger.remove()
logger.add(sys.stderr, level="WARNING")


def _print_json(data: dict | list):
    console.print_json(json.dumps(data, default=str))


# ---------------------------------------------------------------------------
# recommend
# ---------------------------------------------------------------------------
@app.command()
def recommend(
    task: Annotated[str, typer.Option("--task", "-t", help="Task description")],
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max recommendations")] = 5,
    as_json: Annotated[bool, typer.Option("--json", help="JSON output")] = False,
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Suggest model routing in chains"),
):
    """Recommend skill chains for a task."""
    result = recommender.recommend(task=task, limit=limit, model=model)

    if as_json:
        _print_json(result)
        return

    if not result["recommendations"]:
        console.print("[yellow]No recommendations found.[/yellow]")
        console.print("Components may be unavailable. Run: ./run.sh status")
        return

    table = Table(title=f"Skill Chain Recommendations for: {task}")
    table.add_column("#", style="bold", width=3)
    table.add_column("Chain", style="cyan")
    table.add_column("Orchestrator", style="green")
    table.add_column("Confidence", justify="right")
    table.add_column("Tier", style="magenta")
    table.add_column("Elegance", style="yellow")
    table.add_column("ATP", justify="right")
    table.add_column("Reason")

    for rec in result["recommendations"]:
        chain_str = " → ".join(rec["chain"])
        if model:
            chain_str = f"{chain_str} with {model}"
        orch = rec.get("orchestrator") or "-"
        table.add_row(
            str(rec["rank"]),
            chain_str,
            orch,
            f"{rec['confidence']:.3f}",
            rec["tier"],
            rec["elegance"],
            f"{rec['energy_atp']:.1f}",
            rec["reason"][:60],
        )

    console.print(table)

    shadow = result.get("shadow", {})
    if shadow.get("status") != "no_data":
        console.print(
            f"\n[dim]Shadow: {shadow.get('status', '?')} "
            f"(agreement: {shadow.get('agreement_rate', '?')}, "
            f"n={shadow.get('total', 0)})[/dim]"
        )


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------
@app.command()
def evaluate(
    skills: Annotated[list[str], typer.Argument(help="Skill names to evaluate")],
    as_json: Annotated[bool, typer.Option("--json", help="JSON output")] = False,
):
    """Evaluate a specific skill chain's bond strength and elegance."""
    result = recommender.evaluate(skills=skills)

    if as_json:
        _print_json(result)
        return

    console.print(f"\n[bold]Chain:[/bold] {' → '.join(result['chain'])}")

    if "success_probability" in result:
        console.print(f"[bold]Success Probability:[/bold] {result['success_probability']:.3f}")

    if "bonds" in result:
        bond_table = Table(title="Bonds")
        bond_table.add_column("From")
        bond_table.add_column("To")
        bond_table.add_column("Type", style="cyan")
        bond_table.add_column("Probability", justify="right")
        for bond in result["bonds"]:
            bond_table.add_row(
                bond.get("from", "?"),
                bond.get("to", "?"),
                bond.get("bond_type", "?"),
                f"{bond.get('success_probability', 0):.3f}",
            )
        console.print(bond_table)

    if "elegance" in result and isinstance(result["elegance"], dict):
        console.print(f"[bold]Elegance:[/bold] {result['elegance'].get('grade', '?')}")
        console.print(f"[bold]Energy:[/bold] {result.get('energy', {}).get('total_energy', '?')} ATP")

    if result.get("orchestrator"):
        console.print(f"[bold green]Orchestrator:[/bold green] {result['orchestrator']}")

    if "error" in result:
        console.print(f"[red]Error:[/red] {result['error']}")


# ---------------------------------------------------------------------------
# chains
# ---------------------------------------------------------------------------
@app.command()
def chains(
    as_json: Annotated[bool, typer.Option("--json", help="JSON output")] = False,
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
):
    """List known chains from training data and recommendation history."""
    known = recommender.get_known_chains()

    if as_json:
        _print_json(known[:limit])
        return

    if not known:
        console.print("[yellow]No known chains yet.[/yellow]")
        console.print("Run recommendations or ./run.sh train to populate.")
        return

    table = Table(title=f"Known Chains ({len(known)} total, showing {min(limit, len(known))})")
    table.add_column("Task")
    table.add_column("Chain", style="cyan")
    table.add_column("Confidence", justify="right")
    table.add_column("Source", style="dim")

    for entry in known[:limit]:
        table.add_row(
            (entry["task"][:50] + "...") if len(entry.get("task", "")) > 50 else entry.get("task", ""),
            " → ".join(entry.get("chain", [])),
            f"{entry.get('confidence', 0):.2f}",
            entry.get("source", "?"),
        )

    console.print(table)


# ---------------------------------------------------------------------------
# shadow-status
# ---------------------------------------------------------------------------
@app.command("shadow-status")
def shadow_status(
    as_json: Annotated[bool, typer.Option("--json", help="JSON output")] = False,
):
    """Show shadow-LEGO agreement rate between classifier and teacher."""
    result = recommender.get_shadow_status()

    if as_json:
        _print_json(result)
        return

    status = result.get("status", "unknown")
    color = {"CONFIDENT": "green", "LEARNING": "yellow", "DIVERGENT": "red"}.get(status, "dim")
    console.print(f"[bold]Shadow Status:[/bold] [{color}]{status}[/{color}]")

    rate = result.get("agreement_rate")
    if rate is not None:
        console.print(f"[bold]Agreement Rate:[/bold] {rate:.1%}")
    else:
        console.print("[dim]No shadow data collected yet.[/dim]")

    console.print(f"[bold]Total Comparisons:[/bold] {result.get('total', 0)}")


# ---------------------------------------------------------------------------
# train
# ---------------------------------------------------------------------------
@app.command()
def train(
    as_json: Annotated[bool, typer.Option("--json", help="JSON output")] = False,
):
    """Retrain from accumulated labels via chain_miner + train_classifiers."""
    from . import trainer

    result = trainer.retrain()

    if as_json:
        _print_json(result)
        return

    if result.get("success"):
        console.print("[green]Retrain completed successfully.[/green]")
    else:
        console.print(f"[red]Retrain failed:[/red] {result.get('error', 'unknown')}")

    for step, info in result.get("steps", {}).items():
        status = "[green]OK[/green]" if info.get("success") else f"[red]FAIL: {info.get('error', '?')}[/red]"
        console.print(f"  {step}: {status}")


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------
@app.command()
def status(
    as_json: Annotated[bool, typer.Option("--json", help="JSON output")] = False,
):
    """Health check: report which components are available."""
    result = recommender.get_status()

    if as_json:
        _print_json(result)
        return

    healthy = result.get("healthy", False)
    color = "green" if healthy else "red"
    console.print(f"[bold]Health:[/bold] [{color}]{'HEALTHY' if healthy else 'DEGRADED'}[/{color}]")
    console.print(f"[bold]Components:[/bold] {result['available']}/{result['total']}")

    table = Table()
    table.add_column("Component")
    table.add_column("Status")

    for name, available in result.get("components", {}).items():
        s = "[green]available[/green]" if available else "[red]missing[/red]"
        table.add_row(name, s)

    console.print(table)
    console.print(f"\n[dim]Data: {result['data_dir']}[/dim]")
    console.print(f"[dim]Recommendations logged: {result['recommendations_count']}[/dim]")
    console.print(f"[dim]Shadow comparisons: {result['shadow_count']}[/dim]")


if __name__ == "__main__":
    app()
