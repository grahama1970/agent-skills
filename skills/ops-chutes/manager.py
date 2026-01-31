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
             console.print("[yellow]No chutes found.[/yellow]")
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
    """Check Subscription Quota and Remaining Balance."""
    try:
        client = ChutesClient()
        reset_time = client.get_day_reset_time()
        now = datetime.now(timezone.utc)
        
        # Calculate countdown
        diff = reset_time - now
        hours = int(diff.total_seconds() // 3600)
        minutes = int((diff.total_seconds() % 3600) // 60)

        # 1. Quota (Authoritative)
        target_name = f"Chute {chute_id}" if chute_id else "Daily Quota Usage"
        quota_data = client.get_quota(chute_id)
        
        quota = quota_data["quota"]
        used = quota_data["used"]
        remaining_quota = max(quota - used, 0)
        
        color_q = "green" if remaining_quota > (quota * 0.1) else "red"
        
        console.print(f"[bold]{target_name}[/bold]")
        console.print(f"  Used: {used:.2f} / {quota}")
        console.print(f"  Remaining: [{color_q}]{remaining_quota:.2f}[/]")
        if not chute_id:
             # Only global quota has a clear daily reset timer in this context
             console.print(f"  Resets in: {hours}h {minutes}m")

        # 2. Account Balance
        user_info = client.get_user_info()
        balance = user_info["balance"]
        
        if isinstance(balance, (int, float)):
             color_b = "green" if balance > MIN_BALANCE else "red"
             console.print(f"[bold]Remaining Balance:[/bold] [{color_b}]${balance:.2f}[/]")
        else:
             console.print(f"[bold]Remaining Balance:[/bold] {balance}")

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
        quota_data = client.get_quota()
        quota = quota_data["quota"]
        used = quota_data["used"]
        
        if used >= quota:
            console.print(f"[red]Daily Quota Exhausted ({used:.2f}/{quota})[/red]")
            sys.exit(1)
        else:
             console.print(f"[green]Daily Quota OK ({used:.2f}/{quota})[/green]")
        
        # 2. Check Balance (Backstop)
        user_info = client.get_user_info()
        balance = user_info["balance"]
        
        if isinstance(balance, (int, float)):
            if balance < MIN_BALANCE:
                console.print(f"[red]Balance Exhausted (${balance:.2f} < ${MIN_BALANCE:.2f})[/red]")
                sys.exit(1)
            else:
                console.print(f"[green]Balance OK (${balance:.2f})[/green]")
        else:
             console.print(f"[yellow]Warning: Balance is non-numeric: {balance}[/yellow]")
        
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

@app.command()
def models(
    query: Optional[str] = typer.Option(None, help="Filter models by ID (substring, case-insensitive)"),
    owner: Optional[str] = typer.Option(None, help="Filter models by owner (e.g. sglang, vllm)"),
    modality: Optional[str] = typer.Option(None, help="Filter models by modality (e.g. image, text)"),
    feature: Optional[str] = typer.Option(None, help="Filter models by feature (e.g. reasoning, tools)")
):
    """Explore all available models with advanced filtering."""
    try:
        client = ChutesClient()
        models_list = client.list_models()
        
        if not models_list:
            console.print("[yellow]No models found.[/yellow]")
            return

        # Filtering logic
        if query:
            models_list = [m for m in models_list if query.lower() in m.get("id", "").lower()]
        
        if owner:
            models_list = [m for m in models_list if owner.lower() == m.get("owned_by", "").lower()]
            
        if modality:
            modality = modality.lower()
            models_list = [
                m for m in models_list 
                if modality in [mod.lower() for mod in m.get("input_modalities", [])] or
                   modality in [mod.lower() for mod in m.get("output_modalities", [])]
            ]
            
        if feature:
            feature = feature.lower()
            models_list = [
                m for m in models_list 
                if feature in [f.lower() for f in m.get("supported_features", [])]
            ]

        table = Table("Model ID", "Owner", "Price (In/Out)", "Modalities", "Features")
        for m in models_list:
            m_id = m.get("id", "??")
            owned_by = m.get("owned_by", "??")
            
            # Pricing
            pricing = m.get("pricing", {})
            p_prompt = pricing.get("prompt", 0.0)
            p_comp = pricing.get("completion", 0.0)
            price_str = f"${p_prompt:.3f} / ${p_comp:.3f}"
            
            # Modalites & Features
            inputs = m.get("input_modalities", [])
            outputs = m.get("output_modalities", [])
            mods = ",".join(set(inputs + outputs))
            
            feats = ",".join(m.get("supported_features", []))
            
            table.add_row(
                m_id, 
                owned_by, 
                price_str,
                mods,
                feats
            )
            
        console.print(table)
        console.print(f"[dim]Total matches: {len(models_list)}[/dim]")
    except Exception as e:
        console.print(f"[red]Failed to list models: {e}[/red]")
        sys.exit(1)

if __name__ == "__main__":
    app()
