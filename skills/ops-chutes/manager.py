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
MIN_BALANCE = float(os.environ.get("CHUTES_MIN_BALANCE", 0.05))

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
def usage(chute_id: Optional[str] = typer.Option(None, help="Check specific chute quota (if owned)")):
    """Check Daily Usage (Calls) and Account Balance."""
    try:
        client = ChutesClient()
        reset_time = client.get_day_reset_time()
        
        console.print(f"[bold]Daily Call Limit:[/bold] {DAILY_LIMIT}")
        console.print(f"[bold]Reset Time (UTC):[/bold] {reset_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        # 1. Daily Usage (Count)
        try:
             count = client.get_daily_usage()
             remaining = max(DAILY_LIMIT - count, 0)
             color = "green" if remaining > 500 else "red"
             
             console.print(f"[bold]Daily Usage:[/bold] {count} / {DAILY_LIMIT}")
             console.print(f"[bold]Remaining:[/bold] [{color}]{remaining}[/{color}]")
             
        except Exception as e:
             console.print(f"[red]Failed to fetch usage:[/red] {e}")

        # 2. Account Balance (Backstop)
        user_info = client.get_user_info()
        if "error" in user_info:
             console.print(f"[red]Balance Check Failed:[/red] {user_info['error']}")
        else:
             balance = user_info.get("balance", "unknown")
             console.print(f"[bold]Account Balance:[/bold] {balance} Credits")

    except Exception as e:
        console.print(f"[red]Error checking usage: {e}[/red]")
        sys.exit(1)

@app.command("budget-check")
def budget_check():
    """
    Exit code 0 if budget OK.
    Exit code 1 if Daily Limit exhausted OR Balance too low.
    """
    try:
        client = ChutesClient()
        
        # 1. Check Daily Limit (Count)
        try:
            count = client.get_daily_usage()
            if count >= DAILY_LIMIT:
                console.print(f"[red]Daily Limit Exhausted ({count}/{DAILY_LIMIT})[/red]")
                sys.exit(1)
            else:
                console.print(f"[green]Daily Limit OK ({count}/{DAILY_LIMIT})[/green]")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not verify daily usage ({e})[/yellow]")

        # 2. Check Balance (Backstop)
        user_info = client.get_user_info()
        if "error" not in user_info:
            balance = user_info.get("balance", 0)
            if isinstance(balance, (int, float)):
                if balance < MIN_BALANCE:
                    console.print(f"[red]Balance Exhausted ({balance} < {MIN_BALANCE})[/red]")
                    sys.exit(1)
                else:
                    console.print(f"[green]Balance OK ({balance})[/green]")
        
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
