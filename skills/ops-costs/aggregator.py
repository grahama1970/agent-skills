"""Unified cost aggregator across all provider ops-* skills."""

from __future__ import annotations
import os

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Unified cost aggregator for Embry OS providers")
console = Console()

SKILLS_ROOT = Path(__file__).resolve().parent.parent
HISTORY_DIR = Path.home() / ".pi" / "costs"
LAST_RUN = HISTORY_DIR / "last_run.json"

# Provider configurations: (skill_name, subcommand_args, parser_function_name)
PROVIDERS = {
    "chutes": {
        "skill": "ops-chutes",
        "args": ["report", "--monthly", "--json"],
        "source": "api",
    },
    "claude": {
        "skill": "ops-claude",
        "args": ["report", "--monthly", "--json"],
        "source": "max_plan_equivalent",
    },
    "google": {
        "skill": "ops-google",
        "args": ["usage", "--json"],
        "source": "free_tier",
    },
    "runpod": {
        "skill": "ops-runpod",
        "args": ["list-instances"],
        "source": "gpu_hours",
    },
}


def _call_provider(name: str, config: dict, timeout: int = 30) -> dict:
    """Call a provider's run.sh and parse output."""
    run_sh = SKILLS_ROOT / config["skill"] / "run.sh"
    if not run_sh.exists():
        return {"error": f"{config['skill']}/run.sh not found", "total_usd": 0.0}

    try:
        proc = subprocess.run(
            ["bash", str(run_sh)] + config["args"],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if proc.returncode != 0:
            return {
                "error": f"exit {proc.returncode}: {proc.stderr.strip()[:200]}",
                "total_usd": 0.0,
                "source": config["source"],
            }

        stdout = proc.stdout.strip()
        if not stdout:
            return {"total_usd": 0.0, "source": config["source"], "note": "empty output"}

        # Try to parse as JSON
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            # For non-JSON output (e.g., runpod list-instances), extract what we can
            return {
                "total_usd": 0.0,
                "source": config["source"],
                "raw_lines": len(stdout.splitlines()),
                "note": "non-json output",
            }

        return _extract_cost(name, data, config["source"])

    except subprocess.TimeoutExpired:
        return {"error": f"timeout after {timeout}s", "total_usd": 0.0}
    except Exception as exc:
        return {"error": str(exc), "total_usd": 0.0}


def _extract_cost(name: str, data: dict, source: str) -> dict:
    """Extract cost from provider-specific JSON format."""
    result: dict = {"source": source}

    if name == "chutes":
        # ops-chutes: {daily: [{apiCost: N}, ...], total: N}
        if "total" in data:
            result["total_usd"] = float(data["total"])
        elif "daily" in data:
            result["total_usd"] = sum(
                float(d.get("apiCost", 0)) for d in data["daily"]
            )
        else:
            result["total_usd"] = 0.0
        return result

    if name == "claude":
        # ops-claude: similar structure or flat total
        if "total" in data:
            result["total_usd"] = float(data["total"])
        elif "monthly_equivalent" in data:
            result["total_usd"] = float(data["monthly_equivalent"])
        else:
            result["total_usd"] = 0.0
        return result

    if name == "google":
        # ops-google: {calls_today: N, ...} — free tier
        result["total_usd"] = 0.0
        result["calls"] = data.get("calls_today", data.get("total_calls", 0))
        return result

    if name == "runpod":
        # ops-runpod: list of instances with cost fields
        if isinstance(data, list):
            result["total_usd"] = sum(
                float(i.get("costPerHr", 0)) * float(i.get("hours", 1))
                for i in data
            )
        elif "total_cost" in data:
            result["total_usd"] = float(data["total_cost"])
        else:
            result["total_usd"] = 0.0
        return result

    result["total_usd"] = 0.0
    return result


def aggregate_costs() -> dict:
    """Call all providers and aggregate costs."""
    t0 = time.monotonic()
    providers_result = {}

    for name, config in PROVIDERS.items():
        logger.info(f"Querying {name}...")
        providers_result[name] = _call_provider(name, config)

    total_usd = sum(p.get("total_usd", 0) for p in providers_result.values())
    duration = round(time.monotonic() - t0, 2)

    # Build figure_data (exclude zero-cost providers from charts)
    bar_metrics = {}
    pie_data = {}
    for name, pdata in providers_result.items():
        cost = pdata.get("total_usd", 0)
        label = name.capitalize()
        if name == "claude":
            label = "Claude (equiv)"
        bar_metrics[label] = round(cost, 2)
        if cost > 0:
            pie_data[name.capitalize()] = round(cost, 2)

    now = datetime.now(timezone.utc)
    return {
        "period": now.strftime("%Y-%m"),
        "timestamp": now.isoformat(),
        "providers": providers_result,
        "total_usd": round(total_usd, 2),
        "duration_s": duration,
        "figure_data": {
            "bar": {"metrics": bar_metrics},
            "pie": pie_data,
        },
    }


def save_last_run(data: dict) -> None:
    """Persist last run to disk."""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    LAST_RUN.write_text(json.dumps(data, indent=2))


# --- CLI ---


@app.command()
def report(
    monthly: bool = typer.Option(True, "--monthly/--daily", help="Monthly or daily"),
    days: int = typer.Option(30, "--days", help="Number of days"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Aggregated cost report from all providers."""
    result = aggregate_costs()
    save_last_run(result)

    if json_output:
        print(json.dumps(result, indent=2))
    else:
        _print_report(result)


@app.command()
def breakdown(
    provider: str = typer.Option(..., "--provider", help="Provider: chutes|claude|google|runpod"),
) -> None:
    """Show detailed breakdown for a single provider."""
    if provider not in PROVIDERS:
        console.print(f"[red]Unknown provider: {provider}. Choose from: {', '.join(PROVIDERS)}[/red]")
        raise typer.Exit(1)

    config = PROVIDERS[provider]
    result = _call_provider(provider, config, timeout=30)
    console.print(f"\n[bold]{provider.capitalize()} Breakdown[/bold]")
    for k, v in result.items():
        console.print(f"  {k}: {v}")
    console.print()


@app.command()
def budget(
    monthly_limit: float = typer.Option(200.0, "--monthly-limit", help="Monthly budget limit in USD"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Check if spending is approaching budget limit."""
    result = aggregate_costs()
    save_last_run(result)

    total = result["total_usd"]
    pct = round((total / monthly_limit) * 100, 1) if monthly_limit > 0 else 0
    status = "ok" if pct < 80 else ("warning" if pct < 100 else "over_budget")

    budget_result = {
        "monthly_limit_usd": monthly_limit,
        "current_usd": total,
        "percent_used": pct,
        "status": status,
        "providers": result["providers"],
    }

    if json_output:
        print(json.dumps(budget_result, indent=2))
    else:
        color = "green" if status == "ok" else ("yellow" if status == "warning" else "red")
        console.print(f"\n[bold]Budget Check[/bold]")
        console.print(f"  Limit:   ${monthly_limit:.2f}")
        console.print(f"  Current: ${total:.2f}")
        console.print(f"  Used:    [{color}]{pct}%[/{color}]")
        console.print(f"  Status:  [{color}]{status.upper()}[/{color}]\n")


# --- Display ---


def _print_report(result: dict) -> None:
    """Print Rich table for cost report."""
    table = Table(title=f"Cost Report — {result['period']}")
    table.add_column("Provider", style="cyan")
    table.add_column("Cost (USD)", justify="right")
    table.add_column("Source")
    table.add_column("Notes")

    for name, pdata in result.get("providers", {}).items():
        cost = f"${pdata.get('total_usd', 0):.2f}"
        source = pdata.get("source", "unknown")
        notes = ""
        if "error" in pdata:
            notes = f"[red]{pdata['error'][:50]}[/red]"
        elif "calls" in pdata:
            notes = f"{pdata['calls']} calls"
        elif "note" in pdata:
            notes = pdata["note"]
        table.add_row(name.capitalize(), cost, source, notes)

    console.print(table)
    console.print(f"\n[bold]Total: ${result['total_usd']:.2f}[/bold]  (queried in {result['duration_s']}s)\n")


if __name__ == "__main__":
    app()
