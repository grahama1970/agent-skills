import typer
import sys
import os
from typing import Optional
from rich.console import Console
from rich.table import Table
from util import ChutesClient
from datetime import datetime
import pytz

app = typer.Typer(help="Ops Chutes Manager")
console = Console()

DAILY_LIMIT = int(os.environ.get("CHUTES_DAILY_LIMIT", 5000))

@app.command()
def status():
    """List status of accessible chutes."""
    try:
        client = ChutesClient()
        chutes = client.list_chutes()
        
        if not chutes:
             console.print("[yellow]No chutes found or access denied (Management API).[/yellow]")
             return

        table = Table("ID", "Name", "Status", "Image")
        for c in chutes:
            # Adjust fields based on actual API response structure
            c_id = c.get("id", "??")
            name = c.get("name", "??") 
            status = c.get("status", "unknown")
            image = c.get("image", "")
            
            style = "green" if status == "running" else "red"
            table.add_row(c_id, name, f"[{style}]{status}[/{style}]", image)
            
        console.print(table)
    except Exception as e:
        console.print(f"[red]Failed to list chutes: {e}[/red]")
        sys.exit(1)

@app.command()
def usage(chute_id: str = typer.Option(..., help="Chute ID to check quota usage")):
    """Check API usage and estimated budget."""
    try:
        client = ChutesClient()
        reset_time = client.get_day_reset_time()
        
        console.print(f"[bold]Daily Limit:[/bold] {DAILY_LIMIT}")
        console.print(f"[bold]Reset Time (UTC):[/bold] {reset_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        data = client.get_quota_usage(chute_id)

        if "error" in data:
             console.print(f"[red]Usage Check Failed:[/red] {data['error']}")
             if "Auth failed" in data.get("error", ""):
                 console.print("[dim]Note: Your token might be valid for Inference but NOT Management API.[/dim]")
             return

        # Adjust field names based on actual response schema - defensive
        quota = data.get("quota") or data.get("subscription", {}).get("quota")
        used = data.get("used") or data.get("subscription", {}).get("used")

        console.print(f"[bold]Chute:[/bold] {chute_id}")
        console.print(f"[bold]Quota:[/bold] {quota}")
        console.print(f"[bold]Used:[/bold] {used}")
        if quota is not None and used is not None:
            remaining = max(quota - used, 0)
            console.print(f"[bold]Remaining:[/bold] {remaining}")
        else:
            console.print("[yellow]Quota fields not found in response; check API schema.[/yellow]")
            console.print(f"[dim]Raw Response: {data}[/dim]")

    except Exception as e:
        console.print(f"[red]Error checking usage: {e}[/red]")
        sys.exit(1)

@app.command("budget-check")
def budget_check(chute_id: str = typer.Option(..., help="Chute ID to check quota usage")):
    """
    Exit code 0 if budget OK.
    Exit code 1 if budget exhausted.
    Used by scheduler.
    """
    try:
        client = ChutesClient()
        data = client.get_quota_usage(chute_id)

        if "error" in data:
            console.print(f"[yellow]Warning: Could not verify budget ({data['error']}). Assuming OK.[/yellow]")
            sys.exit(0)

        quota = data.get("quota") or data.get("subscription", {}).get("quota")
        used = data.get("used") or data.get("subscription", {}).get("used")

        if quota is None or used is None:
            console.print("[red]Quota usage response missing required fields.[/red]")
            # Fail safe or fail loud? Fail loud for now to detect schema mismatches
            sys.exit(1)

        if used >= quota:
            console.print(f"[red]Budget Exhausted ({used}/{quota})[/red]")
            sys.exit(1)
            
        console.print(f"[green]Budget OK ({used}/{quota})[/green]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

@app.command()
def sanity(model: str = typer.Option("Qwen/Qwen2.5-72B-Instruct", help="Specific model/chute to test")):
    """Run a sanity check/ping via Inference."""
    try:
        client = ChutesClient()
        console.print(f"Testing inference on [bold]{model}[/bold]...")
        if client.check_sanity(model=model):
            console.print("[green]✅ Chutes API is reachable and responding (Inference OK)[/green]")
        else:
            console.print("[red]❌ Chutes API check failed (Inference Error)[/red]")
            sys.exit(1)
            
    except Exception as e:
        console.print(f"[red]Sanity check crashed: {e}[/red]")
        sys.exit(1)

if __name__ == "__main__":
    app()
