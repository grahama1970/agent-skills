"""CLI manager for /ops-google skill."""
import json
import os
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from util import GeminiClient, read_shared_usage, update_max_daily

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)
    _mem_env = os.path.expanduser("~/workspace/experiments/memory/.env")
    if os.path.exists(_mem_env):
        load_dotenv(_mem_env, override=False)
except ImportError:
    pass

app = typer.Typer(help="Ops Google — Gemini API management and budget safety")
console = Console()


@app.command()
def status():
    """Model health + rate limits + budget remaining."""
    try:
        client = GeminiClient()

        # Health check
        health = client.model_health()
        h_color = {"OK": "green", "SLOW": "yellow", "DOWN": "red"}.get(health["status"], "white")
        console.print(f"[bold]Gemini Health:[/bold] [{h_color}]{health['status']}[/{h_color}]"
                      f" ({health.get('latency_ms', '?')}ms, {health['model']})")

        # Budget
        budget = client.get_budget_status()
        calls = budget.get("calls_today", 0)
        max_d = budget.get("max_daily", 5000)
        remaining = max(max_d - calls, 0)
        b_color = "green" if remaining > max_d * 0.2 else "yellow" if remaining > 0 else "red"
        console.print(f"[bold]Budget:[/bold] [{b_color}]{calls}/{max_d} calls today[/{b_color}]"
                      f" ({remaining} remaining)")

        # Rate limits
        limits = client.get_rate_limits()
        console.print(f"[bold]Rate Limits ({limits['tier']}):[/bold]"
                      f" {limits.get('rpm', '?')} RPM, {limits.get('tpm', '?'):,} TPM")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@app.command()
def models(
    as_json: bool = typer.Option(False, "--json", help="Output JSON for automation"),
):
    """List available Gemini models with specs."""
    try:
        client = GeminiClient()
        model_list = client.list_models()

        if as_json:
            print(json.dumps(model_list, indent=2))
            return

        if not model_list:
            console.print("[yellow]No models found.[/yellow]")
            return

        table = Table("Model", "Display Name", "Input Tokens", "Output Tokens")
        for m in model_list:
            table.add_row(
                m["name"],
                m.get("display_name", ""),
                f"{m.get('input_token_limit', '?'):,}",
                f"{m.get('output_token_limit', '?'):,}",
            )
        console.print(table)
        console.print(f"[dim]Total: {len(model_list)} models with generateContent[/dim]")

    except Exception as e:
        if as_json:
            print(json.dumps({"error": str(e)}))
        else:
            console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@app.command()
def usage(
    as_json: bool = typer.Option(False, "--json", help="Output JSON for automation"),
):
    """Show Gemini call count from shared budget file (cross-process)."""
    budget = read_shared_usage()
    calls = budget.get("calls_today", 0)
    max_d = budget.get("max_daily", 5000)
    remaining = max(max_d - calls, 0)

    if as_json:
        budget["remaining"] = remaining
        print(json.dumps(budget))
        return

    b_color = "green" if remaining > max_d * 0.2 else "yellow" if remaining > 0 else "red"
    console.print(f"[bold]Gemini Usage (today: {budget.get('date', '?')}):[/bold]")
    console.print(f"  Calls: [{b_color}]{calls} / {max_d}[/{b_color}]")
    console.print(f"  Remaining: [{b_color}]{remaining}[/{b_color}]")
    if budget.get("last_call"):
        console.print(f"  Last call: {budget['last_call']}")


@app.command("rate-limits")
def rate_limits(
    model: str = typer.Option("gemini-2.5-flash", help="Model to check"),
    as_json: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """RPM/TPM limits for current tier (Google Pro)."""
    try:
        client = GeminiClient()
        limits = client.get_rate_limits(model)

        if as_json:
            print(json.dumps(limits))
            return

        console.print(f"[bold]{limits['model']}[/bold] ({limits['tier']})")
        console.print(f"  RPM: {limits.get('rpm', '?')}")
        console.print(f"  TPM: {limits.get('tpm', '?'):,}" if isinstance(limits.get('tpm'), int) else f"  TPM: {limits.get('tpm', '?')}")
        console.print(f"  RPD: {limits.get('rpd', '?'):,}" if isinstance(limits.get('rpd'), int) else f"  RPD: {limits.get('rpd', '?')}")
    except Exception as e:
        if as_json:
            print(json.dumps({"error": str(e)}))
        else:
            console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@app.command()
def sanity(
    model: str = typer.Argument("gemini-2.5-flash", help="Model to test"),
):
    """Quick API connectivity test."""
    try:
        client = GeminiClient()
        console.print(f"Testing [bold]{model}[/bold]...")

        health = client.model_health(model)
        if health["status"] in ("OK", "SLOW"):
            color = "green" if health["status"] == "OK" else "yellow"
            console.print(f"[{color}]API reachable — {health['status']} "
                          f"({health['latency_ms']}ms)[/{color}]")
            if health.get("response"):
                console.print(f"  Response: {health['response']}")
        else:
            console.print(f"[red]API unreachable: {health.get('error', 'unknown')}[/red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]Sanity check failed: {e}[/red]")
        sys.exit(1)


@app.command("billing-check")
def billing_check():
    """Check if Gemini usage is within safe bounds.

    Warns about Google's auto-billing and checks the local budget cap.
    Exit code 1 if budget exhausted or no cap set.
    """
    budget = read_shared_usage()
    calls = budget.get("calls_today", 0)
    max_d = budget.get("max_daily", 5000)

    if max_d <= 0:
        console.print("[red]Gemini DISABLED (max_daily=0)[/red]")
        sys.exit(1)

    if calls >= max_d:
        console.print(f"[red]Budget EXHAUSTED: {calls}/{max_d} calls today[/red]")
        console.print("[yellow]Google auto-bills beyond this. Run: ./run.sh set-budget <N> to adjust.[/yellow]")
        sys.exit(1)

    remaining = max_d - calls
    pct = remaining / max_d * 100

    if pct < 10:
        console.print(f"[yellow]Budget LOW: {calls}/{max_d} ({remaining} remaining, {pct:.0f}%)[/yellow]")
        console.print("[yellow]Google auto-bills with no hard cap. Consider pausing.[/yellow]")
    else:
        console.print(f"[green]Budget OK: {calls}/{max_d} ({remaining} remaining, {pct:.0f}%)[/green]")

    # Check if API key is even set
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        console.print("[dim]Note: GEMINI_API_KEY not set (Gemini fallback inactive)[/dim]")


@app.command("set-budget")
def set_budget(
    max_calls: int = typer.Argument(..., help="New max daily call limit"),
):
    """Update the max daily Gemini call limit in shared state."""
    if max_calls < 0:
        console.print("[red]max_calls must be >= 0[/red]")
        sys.exit(1)

    data = update_max_daily(max_calls)
    console.print(f"[green]Budget updated: max_daily={max_calls}[/green]")
    console.print(f"  Current calls today: {data.get('calls_today', 0)}")
    if max_calls == 0:
        console.print("[yellow]Gemini fallback is now DISABLED[/yellow]")


if __name__ == "__main__":
    app()
