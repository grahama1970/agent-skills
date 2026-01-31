import typer
import sys
import os
from typing import Optional
from rich.console import Console
from rich.table import Table
from util import ChutesClient
from datetime import datetime, timezone
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
    """Check Global Subscription Quota and Account Balance."""
    try:
        client = ChutesClient()
        reset_time = client.get_day_reset_time()
        now = datetime.now(timezone.utc)
        
        # Calculate countdown
        diff = reset_time - now
        hours = int(diff.total_seconds() // 3600)
        minutes = int((diff.total_seconds() % 3600) // 60)

        # 1. Global Quota (Authoritative)
        data = client.get_global_quota()
        if "error" in data:
             console.print(f"[red]Global Quota Check Failed:[/red] {data['error']}")
        else:
             quota = data.get("quota", DAILY_LIMIT)
             used = data.get("used", 0)
             remaining = max(quota - used, 0)
             
             color = "green" if remaining > (quota * 0.1) else "red"
             
             console.print(f"[bold]Daily Quota Usage[/bold]")
             console.print(f"  Used: {used:.2f} / {quota}")
             console.print(f"  Remaining: [{color}]{remaining:.2f}[/{color}]")
             console.print(f"  Resets in: {hours}h {minutes}m")

        # 2. Account Balance (Backstop)
        user_info = client.get_user_info()
        if "error" not in user_info:
             balance = user_info.get("balance", "unknown")
             if isinstance(balance, (int, float)):
                 console.print(f"[bold]Account Balance:[/bold] ${balance:.2f}")
             else:
                 console.print(f"[bold]Account Balance:[/bold] {balance}")

    except Exception as e:
        console.print(f"[red]Error checking usage: {e}[/red]")
        sys.exit(1)

@app.command("budget-check")
def budget_check():
    """
    Exit code 0 if budget OK.
    Exit code 1 if Quota exhausted OR Balance too low.
    """
    try:
        client = ChutesClient()
        
        # 1. Check Global Quota
        data = client.get_global_quota()
        if "error" not in data:
            quota = data.get("quota", DAILY_LIMIT)
            used = data.get("used", 0)
            if used >= quota:
                console.print(f"[red]Daily Quota Exhausted ({used:.2f}/{quota})[/red]")
                sys.exit(1)
            else:
                console.print(f"[green]Daily Quota OK ({used:.2f}/{quota})[/green]")
        
        # 2. Check Balance (Backstop)
        user_info = client.get_user_info()
        if "error" not in user_info:
            balance = user_info.get("balance", 0)
            if isinstance(balance, (int, float)):
                if balance < MIN_BALANCE:
                    console.print(f"[red]Balance Exhausted (${balance:.2f} < ${MIN_BALANCE:.2f})[/red]")
                    sys.exit(1)
                else:
                    console.print(f"[green]Balance OK (${balance:.2f})[/green]")
        
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
