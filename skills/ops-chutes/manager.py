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
def usage():
    """Check API usage and estimated budget."""
    try:
        client = ChutesClient()
        # Note: Since there is no direct quota endpoint, we infer or just show limits
        reset_time = client.get_day_reset_time()
        
        console.print(f"[bold]Daily Limit:[/bold] {DAILY_LIMIT}")
        console.print(f"[bold]Reset Time:[/bold] {reset_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        
        # In a real implementation, we would fetch actual usage here.
        # For now, we report the configuration.
        console.print("[dim]Note: Exact remaining calls requires accumulation from RateLimit headers.[/dim]")
        
    except Exception as e:
        console.print(f"[red]Error checking usage: {e}[/red]")
        sys.exit(1)

@app.command("budget-check")
def budget_check():
    """
    Exit code 0 if budget OK.
    Exit code 1 if budget exhausted.
    Used by scheduler.
    """
    try:
        # TODO: Implement persistent storage for call counting to make this real.
        # For now, we assume budget is always OK unless we hit a 429 externally.
        # If we had a shared counter (e.g. in Memory or a local file), we check it here.
        
        # Placeholder logic: Check a local file or env var if we were tracking it
        # usage = get_stored_usage()
        usage = 0 
        
        if usage >= DAILY_LIMIT:
            console.print(f"[red]Budget Exhausted ({usage}/{DAILY_LIMIT})[/red]")
            sys.exit(1)
            
        console.print(f"[green]Budget OK ({usage}/{DAILY_LIMIT})[/green]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

@app.command()
def sanity(model: str = typer.Option(None, help="Specific model/chute to test")):
    """Run a sanity check/ping."""
    try:
        client = ChutesClient()
        if client.check_sanity():
            console.print("[green]✅ Chutes API is reachable[/green]")
        else:
            console.print("[red]❌ Chutes API ping failed[/red]")
            sys.exit(1)
            
    except Exception as e:
        console.print(f"[red]Sanity check crashed: {e}[/red]")
        sys.exit(1)

if __name__ == "__main__":
    app()
