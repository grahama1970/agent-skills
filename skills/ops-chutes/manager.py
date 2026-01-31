import typer
import sys
import os
import time
import json
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
def usage(
    chute_id: Optional[str] = typer.Option(None, help="Check specific chute quota (if owned)"),
    as_json: bool = typer.Option(False, "--json", help="Output only JSON for automation")
):
    """Check Subscription Quota and Remaining Balance."""
    try:
        client = ChutesClient()
        reset_time = client.get_day_reset_time()
        now = datetime.now(timezone.utc)
        
        # Calculate countdown
        diff = reset_time - now
        seconds_until_reset = int(diff.total_seconds())
        hours = seconds_until_reset // 3600
        minutes = (seconds_until_reset % 3600) // 60

        # 1. Quota
        quota_data = client.get_quota(chute_id)
        quota = quota_data["quota"]
        used = quota_data["used"]
        remaining_quota = max(quota - used, 0)

        # 2. Account Balance
        user_info = client.get_user_info()
        balance = user_info["balance"]

        if as_json:
            result = {
                "used": float(used),
                "quota": float(quota),
                "remaining": float(remaining_quota),
                "balance": float(balance) if isinstance(balance, (int, float)) else balance,
                "reset_in_seconds": seconds_until_reset,
                "reset_at_utc": reset_time.isoformat()
            }
            print(json.dumps(result))
            return

        # Regular rich UI
        target_name = f"Chute {chute_id}" if chute_id else "Daily Quota Usage"
        color_q = "green" if remaining_quota > (quota * 0.1) else "red"
        
        console.print(f"[bold]{target_name}[/bold]")
        console.print(f"  Used: {used:.2f} / {quota}")
        console.print(f"  Remaining: [{color_q}]{remaining_quota:.2f}[/]")
        if not chute_id:
             console.print(f"  Resets in: {hours}h {minutes}m")

        if isinstance(balance, (int, float)):
             color_b = "green" if balance > MIN_BALANCE else "red"
             console.print(f"[bold]Remaining Balance:[/bold] [{color_b}]${balance:.2f}[/]")
        else:
             console.print(f"[bold]Remaining Balance:[/bold] {balance}")

    except Exception as e:
        if as_json:
            print(json.dumps({"error": str(e)}))
        else:
            console.print(f"[red]Error checking usage: {e}[/red]")
        sys.exit(1)

@app.command()
def models(
    query: Optional[str] = typer.Option(None, help="Filter models by ID (substring, case-insensitive)"),
    owner: Optional[str] = typer.Option(None, help="Filter models by owner (e.g. sglang, vllm)"),
    modality: Optional[str] = typer.Option(None, help="Filter models by modality (e.g. image, text)"),
    feature: Optional[str] = typer.Option(None, help="Filter models by feature (e.g. reasoning, tools)"),
    as_json: bool = typer.Option(False, "--json", help="Output only JSON for automation")
):
    """Explore all available models with advanced filtering."""
    try:
        client = ChutesClient()
        models_list = client.list_models()
        
        if not models_list:
            if as_json:
                print(json.dumps([]))
            else:
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

        if as_json:
            # Strip some bulk for cleaner API
            clean_list = []
            for m in models_list:
                clean_list.append({
                    "id": m.get("id"),
                    "owner": m.get("owned_by"),
                    "pricing": m.get("pricing"),
                    "features": m.get("supported_features"),
                    "modalities": list(set(m.get("input_modalities", []) + m.get("output_modalities", [])))
                })
            print(json.dumps(clean_list))
            return

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
            
            table.add_row(m_id, owned_by, price_str, mods, feats)
            
        console.print(table)
        console.print(f"[dim]Total matches: {len(models_list)}[/dim]")
    except Exception as e:
        if as_json:
            print(json.dumps({"error": str(e)}))
        else:
            console.print(f"[red]Failed to list models: {e}[/red]")
        sys.exit(1)

@app.command("model-health")
def model_health(model_id: str):
    """Report health of a specific model: HOT (ready), COLD (loading), DOWN (off)."""
    try:
        client = ChutesClient()
        status = client.get_model_status(model_id)
        
        color = {"HOT": "green", "COLD": "yellow", "DOWN": "red"}.get(status, "white")
        console.print(f"Model [bold]{model_id}[/bold] is: [{color}]{status}[/]")
    except Exception as e:
        console.print(f"[red]Error checking health: {e}[/red]")
        sys.exit(1)

@app.command("wait-for-reset")
def wait_for_reset(timeout: int = typer.Option(86400, help="Max wait in seconds")):
    """Block until the daily quota reset (7PM ET)."""
    try:
        client = ChutesClient()
        reset_at = client.get_day_reset_time()
        
        # We also check if we CURRENTLY have quota. If we do, no wait needed.
        quota_data = client.get_quota()
        if (quota_data["quota"] - quota_data["used"]) > 10:
            console.print("[green]Quota available, no wait required.[/green]")
            return

        now = datetime.now(timezone.utc)
        wait_seconds = int((reset_at - now).total_seconds())
        
        if wait_seconds > timeout:
            console.print(f"[red]Wait time {wait_seconds}s exceeds timeout {timeout}s[/red]")
            sys.exit(1)

        if wait_seconds <= 0:
            console.print("[green]Reset just happened or is imminent. Proceeding.[/green]")
            return

        console.print(f"[yellow]Quota exhausted. Waiting {wait_seconds}s until reset at {reset_at.isoformat()}...[/yellow]")
        time.sleep(wait_seconds)
        console.print("[green]Reset reached. Proceeding.[/green]")

    except Exception as e:
        console.print(f"[red]Wait failed: {e}[/red]")
        sys.exit(1)

@app.command("can-complete")
def can_complete(calls: int = typer.Argument(..., help="Number of planned calls")):
    """Exit 0 if planned calls fit in remaining quota, else exit 1."""
    try:
        client = ChutesClient()
        quota_data = client.get_quota()
        remaining = quota_data["quota"] - quota_data["used"]
        
        if remaining >= calls:
            console.print(f"[green]Feasible: {calls} calls requested, {remaining:.2f} remaining.[/green]")
            sys.exit(0)
        else:
            console.print(f"[red]Infeasible: {calls} calls requested, only {remaining:.2f} remaining.[/red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]Check failed: {e}[/red]")
        sys.exit(1)

@app.command("budget-check")
def budget_check():
    """Exit code 1 if Quota exhausted OR Balance too low."""
    try:
        client = ChutesClient()
        quota_data = client.get_quota()
        if quota_data["used"] >= quota_data["quota"]:
            console.print(f"[red]Daily Quota Exhausted ({quota_data['used']:.2f}/{quota_data['quota']})[/red]")
            sys.exit(1)
        
        user_info = client.get_user_info()
        balance = user_info["balance"]
        if isinstance(balance, (int, float)) and balance < MIN_BALANCE:
            console.print(f"[red]Balance Exhausted (${balance:.2f} < ${MIN_BALANCE:.2f})[/red]")
            sys.exit(1)
        
        console.print("[green]Budget OK[/green]")
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
        
        status = client.get_model_status(model)
        if status == "HOT":
            console.print(f"[green]✅ Model is HOT (Responding to Inference)[/green]")
        elif status == "COLD":
            console.print(f"[yellow]❌ Model is COLD (Present in registry but not responding)[/yellow]")
            sys.exit(1)
        else:
            console.print(f"[red]❌ Model is DOWN (Not found in model registry or completely unresponsive)[/red]")
            sys.exit(1)
            
    except Exception as e:
        console.print(f"[red]Sanity check crashed: {e}[/red]")
        sys.exit(1)

if __name__ == "__main__":
    app()
