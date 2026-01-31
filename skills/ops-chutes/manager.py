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
def usage(chute_id: Optional[str] = typer.Option(None, help="Check specific chute quota (if owned)")):
    """Check Account Balance and optional Chute Quota."""
    try:
        client = ChutesClient()
        reset_time = client.get_day_reset_time()
        
        console.print(f"[bold]Reset Time (UTC):[/bold] {reset_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        # Primary Metric: Account Balance
        user_info = client.get_user_info()
        if "error" in user_info:
             console.print(f"[red]Balance Check Failed:[/red] {user_info['error']}")
        else:
             balance = user_info.get("balance", "unknown")
             currency = "Credits" # or USD, typically credits
             color = "green" if isinstance(balance, (int, float)) and balance > 1.0 else "yellow"
             console.print(f"[bold]Account Balance:[/bold] [{color}]{balance} {currency}[/{color}]")

        # Secondary Metric: Specific Chute Quota
        if chute_id:
            data = client.get_quota_usage(chute_id)
            if "error" in data:
                console.print(f"[yellow]Quota Check Failed for {chute_id}:[/yellow] {data['error']}")
            else:
                quota = data.get("quota") or data.get("subscription", {}).get("quota")
                used = data.get("used") or data.get("subscription", {}).get("used")
                console.print(f"[bold]Chute:[/bold] {chute_id}")
                console.print(f"[bold]Quota:[/bold] {quota}")
                console.print(f"[bold]Used:[/bold] {used}")

    except Exception as e:
        console.print(f"[red]Error checking usage: {e}[/red]")
        sys.exit(1)

@app.command("budget-check")
def budget_check(chute_id: Optional[str] = typer.Option(None, help="Check specific chute quota")):
    """
    Exit code 0 if budget OK.
    Exit code 1 if budget exhausted.
    Checks Account Balance > MIN_BALANCE (default $0.05).
    """
    try:
        client = ChutesClient()
        
        # 1. Check Balance (Global Gate)
        user_info = client.get_user_info()
        if "error" not in user_info:
            balance = user_info.get("balance", 0)
            if isinstance(balance, (int, float)):
                if balance < MIN_BALANCE:
                    console.print(f"[red]Budget Exhausted: Balance {balance} < {MIN_BALANCE}[/red]")
                    sys.exit(1)
                else:
                    console.print(f"[green]Balance OK: {balance}[/green]")
        
        # 2. Check Specific Quota (Optional)
        if chute_id:
            data = client.get_quota_usage(chute_id)
            if "error" not in data:
                quota = data.get("quota") or data.get("subscription", {}).get("quota")
                used = data.get("used") or data.get("subscription", {}).get("used")
                if quota is not None and used is not None and used >= quota:
                    console.print(f"[red]Chute Quota Exhausted ({used}/{quota})[/red]")
                    sys.exit(1)
                elif quota is not None:
                     console.print(f"[green]Chute Quota OK ({used}/{quota})[/green]")

        # If we got here, we're good
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
