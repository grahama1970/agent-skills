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
# Optional budget file path
BUDGET_FILE = os.environ.get("CHUTES_BUDGET_FILE")

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
        reset_time = client.get_day_reset_time()
        
        console.print(f"[bold]Daily Limit:[/bold] {DAILY_LIMIT}")
        console.print(f"[bold]Reset Time (UTC):[/bold] {reset_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        
        # Try to surface current rate-limit headers via a lightweight call
        try:
            import httpx
            with httpx.Client(base_url="https://api.chutes.ai", headers=client.headers, timeout=client.timeout) as hc:
                resp = hc.get("/ping")
            
            remaining = resp.headers.get("X-RateLimit-Remaining") or resp.headers.get("RateLimit-Remaining")
            limit = resp.headers.get("X-RateLimit-Limit") or resp.headers.get("RateLimit-Limit")
            
            if remaining or limit:
                console.print(f"[bold]RateLimit:[/bold] remaining={remaining}, limit={limit}")
            else:
                console.print("[dim]No rate-limit headers present; exact remaining unknown.[/dim]")
        except Exception:
            console.print("[dim]Unable to read rate-limit headers from /ping.[/dim]")

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
        # Check external budget file if configured
        usage = 0
        if BUDGET_FILE and os.path.isfile(BUDGET_FILE):
            try:
                with open(BUDGET_FILE, "r") as f:
                    raw = f.read().strip()
                    usage = int(raw or "0")
                    # Sanity check values
                    if usage < 0:
                        console.print("[yellow]Warning: budget file contains negative value; treating as 0[/yellow]")
                        usage = 0
                    if usage > 10000000:
                        console.print("[yellow]Warning: budget file value unusually large; capping[/yellow]")
                        usage = 10000000
            except Exception as e:
                console.print(f"[yellow]Warning: failed to read budget file: {e}[/yellow]")
        
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
