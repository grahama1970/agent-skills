"""manager - ops-chutes.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

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
from loguru import logger

# Load .env from common locations
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)
    # Also try the memory project .env
    _mem_env = os.path.expanduser("~/workspace/experiments/memory/.env")
    if os.path.exists(_mem_env):
        load_dotenv(_mem_env, override=False)
except ImportError:
    pass

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

        # 3. DeepSeek Direct Balance (if DEEPSEEK_API_KEY set)
        ds_key = os.environ.get("DEEPSEEK_API_KEY")
        ds_balance = None
        if ds_key:
            try:
                import httpx
                r = httpx.get(
                    "https://api.deepseek.com/user/balance",
                    headers={"Authorization": f"Bearer {ds_key}"},
                    timeout=5,
                )
                ds_data = r.json()
                if ds_data.get("is_available"):
                    for bi in ds_data.get("balance_infos", []):
                        if bi.get("currency") == "USD":
                            ds_balance = float(bi["total_balance"])
            except Exception as e:
                logger.debug("value lookup failed: {}", e)

        if as_json:
            result["deepseek_balance"] = ds_balance
            print(json.dumps(result))
            return

        if ds_balance is not None:
            ds_color = "green" if ds_balance > 1.0 else "red"
            console.print(f"[bold]DeepSeek Direct Balance:[/bold] [{ds_color}]${ds_balance:.2f}[/]")

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
def sanity(model: str = typer.Argument("Qwen/Qwen2.5-72B-Instruct", help="Specific model/chute to test")):
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

@app.command()
def recommend(
    model: str = typer.Argument(..., help="Model ID to check (e.g. deepseek-ai/DeepSeek-V3.1-TEE)"),
    as_json: bool = typer.Option(False, "--json", help="Output JSON for automation"),
    skip_ping: bool = typer.Option(False, "--skip-ping", help="Skip latency test, use metadata only"),
):
    """Rank all variants in a model family by speed and recommend the best."""
    try:
        client = ChutesClient()
        err_console = Console(stderr=True)
        log = err_console if as_json else console
        all_models = client.list_inference_models()

        # Verify the input model exists
        target = None
        for m in all_models:
            if m["id"] == model:
                target = m
                break
        if not target:
            console.print(f"[red]Model not found: {model}[/red]")
            sys.exit(1)

        # Find all family members
        family = client.find_family(model, all_models)
        if not family:
            family = [target]

        # Gather metadata + latency for each variant
        variants = []
        for m in family:
            mid = m["id"]
            is_tee = m.get("confidential_compute", False)
            chute_id = m.get("chute_id", "")

            detail = None
            try:
                if chute_id:
                    detail = client.get_chute_details(chute_id)
            except Exception as e:
                logger.debug("if failed: {}", e)

            hot = detail.get("hot") if detail else None
            boost = detail.get("boost", 1.0) if detail else None
            instances = detail.get("instances", []) if detail else []
            active = sum(1 for i in instances if i.get("active"))
            conc = detail.get("concurrency", 0) if detail else 0

            latency = None
            if not skip_ping and hot is not False:
                log.print(f"[dim]Pinging {mid}...[/dim]")
                latency = client.timed_ping(mid)

            variants.append({
                "model": mid,
                "tee": is_tee,
                "hot": hot,
                "boost": boost,
                "instances": active,
                "concurrency": conc,
                "latency_s": latency,
                "current": mid == model,
            })

        # Rank: sort by (hot desc, latency asc with None last)
        def sort_key(v):
            hot_score = 0 if v["hot"] else 1 if v["hot"] is None else 2
            lat = v["latency_s"] if v["latency_s"] is not None else 999
            return (hot_score, lat)

        variants.sort(key=sort_key)

        # Best candidate
        best = variants[0]
        current = next((v for v in variants if v["current"]), variants[0])

        rec = {
            "current": model,
            "family": variants,
            "best": best["model"],
        }

        # Miner preference context: non-TEE models get more miners (higher throughput,
        # lower latency) because TEE enclave overhead reduces TPS and complicates scaling.
        tee_note = ""
        if current["tee"] and not best.get("tee", False):
            tee_note = (
                " Miners prefer non-TEE (higher throughput, no enclave overhead), "
                "so non-TEE variants typically have more active nodes and lower latency."
            )
        elif not current["tee"] and best.get("tee", False):
            tee_note = " Note: TEE adds ~10-20% latency overhead due to enclave isolation."

        if best["model"] == model:
            rec["action"] = "stay"
            rec["reason"] = f"{model} is already the fastest in its family."
        elif best["latency_s"] is not None and current["latency_s"] is not None:
            speedup = current["latency_s"] / best["latency_s"]
            rec["action"] = "switch"
            rec["switch_to"] = best["model"]
            rec["reason"] = (
                f"{best['model']} is {speedup:.1f}x faster "
                f"({best['latency_s']:.1f}s vs {current['latency_s']:.1f}s)"
            )
            if best["tee"] != current["tee"]:
                label = "non-TEE" if not best["tee"] else "TEE"
                rec["reason"] += f", {label}"
            rec["reason"] += f".{tee_note}"
        elif best["latency_s"] is not None and current["latency_s"] is None:
            rec["action"] = "switch"
            rec["switch_to"] = best["model"]
            rec["reason"] = (
                f"{model} timed out; {best['model']} responded in "
                f"{best['latency_s']:.1f}s.{tee_note}"
            )
        elif best["hot"] and not current["hot"]:
            rec["action"] = "switch"
            rec["switch_to"] = best["model"]
            rec["reason"] = (
                f"{model} is not hot; {best['model']} is available.{tee_note}"
            )
        else:
            rec["action"] = "stay"
            rec["reason"] = "No strong signal to switch."

        if as_json:
            print(json.dumps(rec))
            return

        # Rich table output
        console.print()
        table = Table(title=f"Model Family: {model.split('/')[0]}")
        table.add_column("Model", style="bold")
        table.add_column("TEE")
        table.add_column("Hot")
        table.add_column("Boost")
        table.add_column("Instances")
        table.add_column("Latency")
        table.add_column("", style="bold")  # recommendation marker

        for v in variants:
            tee_str = "[yellow]TEE[/yellow]" if v["tee"] else ""
            hot_str = "[green]Yes[/green]" if v["hot"] else "[red]No[/red]" if v["hot"] is False else "[dim]?[/dim]"

            boost_val = v["boost"]
            if boost_val is not None:
                bc = "green" if boost_val < 1.5 else "yellow" if boost_val < 2.0 else "red"
                boost_str = f"[{bc}]{boost_val:.2f}[/{bc}]"
            else:
                boost_str = "[dim]?[/dim]"

            inst_str = f"{v['instances']}" if v["instances"] else "[dim]-[/dim]"

            lat = v["latency_s"]
            if lat is not None:
                lc = "green" if lat < 3.0 else "yellow" if lat < 8.0 else "red"
                lat_str = f"[{lc}]{lat:.2f}s[/{lc}]"
            elif skip_ping:
                lat_str = "[dim]skipped[/dim]"
            else:
                lat_str = "[red]timeout[/red]"

            marker = ""
            if v["model"] == best["model"] and v["model"] != model:
                marker = "[bold green]>>> BEST[/bold green]"
            elif v["model"] == model:
                marker = "[dim]current[/dim]"

            table.add_row(v["model"], tee_str, hot_str, boost_str, inst_str, lat_str, marker)

        console.print(table)
        console.print()

        action = rec["action"]
        if action == "switch":
            console.print(f"[bold yellow]>>> SWITCH to {rec['switch_to']}[/bold yellow]")
            console.print(f"    {rec['reason']}")
        else:
            console.print(f"[bold green]>>> STAY on {model}[/bold green]")
            console.print(f"    {rec['reason']}")

    except Exception as e:
        if as_json:
            print(json.dumps({"error": str(e)}))
        else:
            console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@app.command()
def report(
    days: int = typer.Option(30, help="Number of days to report on"),
    monthly: bool = typer.Option(False, "--monthly", help="Show monthly aggregation"),
    spikes: bool = typer.Option(False, "--spikes", help="Show only days exceeding quota"),
    hourly: Optional[str] = typer.Option(None, "--hourly", help="Show hourly breakdown for a date (YYYY-MM-DD)"),
    as_json: bool = typer.Option(False, "--json", help="Output JSON for automation"),
):
    """Usage analytics report from hourly history data."""
    from collections import defaultdict

    try:
        client = ChutesClient()
        console.print("[dim]Fetching usage history...[/dim]", highlight=False)
        items = client.get_usage_history()

        if not items:
            console.print("[yellow]No usage history found.[/yellow]")
            return

        # Aggregate by day and month
        daily: dict = defaultdict(lambda: {"amount": 0.0, "count": 0, "input_tokens": 0, "output_tokens": 0})
        monthly_agg: dict = defaultdict(lambda: {"amount": 0.0, "count": 0, "input_tokens": 0, "output_tokens": 0})

        for item in items:
            day = item["bucket"][:10]
            month = item["bucket"][:7]
            for k in ("amount", "count", "input_tokens", "output_tokens"):
                daily[day][k] += item.get(k, 0)
                monthly_agg[month][k] += item.get(k, 0)

        # --- Hourly breakdown for a specific date ---
        if hourly:
            hour_items = [i for i in items if i["bucket"].startswith(hourly)]
            if not hour_items:
                console.print(f"[yellow]No data for {hourly}[/yellow]")
                return
            if as_json:
                print(json.dumps(sorted(hour_items, key=lambda x: x["bucket"])))
                return
            table = Table(title=f"Hourly Breakdown: {hourly}")
            table.add_column("Hour", style="bold")
            table.add_column("Calls", justify="right")
            table.add_column("Input Tok", justify="right")
            table.add_column("Output Tok", justify="right")
            table.add_column("Cost", justify="right")
            for h in sorted(hour_items, key=lambda x: x["bucket"]):
                table.add_row(
                    h["bucket"][11:16],
                    f"{h['count']:,}",
                    f"{h['input_tokens']:,}",
                    f"{h['output_tokens']:,}",
                    f"${h['amount']:.4f}",
                )
            d = daily.get(hourly, {})
            table.add_section()
            table.add_row(
                "[bold]TOTAL[/bold]",
                f"[bold]{d.get('count', 0):,}[/bold]",
                f"[bold]{d.get('input_tokens', 0):,}[/bold]",
                f"[bold]{d.get('output_tokens', 0):,}[/bold]",
                f"[bold]${d.get('amount', 0):.4f}[/bold]",
            )
            console.print(table)
            return

        # --- Monthly aggregation ---
        if monthly:
            if as_json:
                print(json.dumps({m: monthly_agg[m] for m in sorted(monthly_agg)}))
                return
            table = Table(title="Monthly Usage Summary")
            table.add_column("Month", style="bold")
            table.add_column("Calls", justify="right")
            table.add_column("Input MTok", justify="right")
            table.add_column("Output MTok", justify="right")
            table.add_column("PAYG Cost", justify="right")
            table.add_column("Total (est)", justify="right")
            for m in sorted(monthly_agg):
                d = monthly_agg[m]
                table.add_row(
                    m,
                    f"{d['count']:,}",
                    f"{d['input_tokens'] / 1e6:.1f}",
                    f"{d['output_tokens'] / 1e6:.1f}",
                    f"${d['amount']:.2f}",
                    f"${d['amount'] + 50:.2f}",
                )
            # Totals
            t_calls = sum(d["count"] for d in monthly_agg.values())
            t_in = sum(d["input_tokens"] for d in monthly_agg.values())
            t_out = sum(d["output_tokens"] for d in monthly_agg.values())
            t_cost = sum(d["amount"] for d in monthly_agg.values())
            n_months = len(monthly_agg)
            table.add_section()
            table.add_row(
                f"[bold]TOTAL ({n_months}mo)[/bold]",
                f"[bold]{t_calls:,}[/bold]",
                f"[bold]{t_in / 1e6:.1f}[/bold]",
                f"[bold]{t_out / 1e6:.1f}[/bold]",
                f"[bold]${t_cost:.2f}[/bold]",
                f"[bold]${t_cost + 50 * n_months:.2f}[/bold]",
            )
            console.print(table)
            console.print(f"[dim]Total (est) = PAYG overage + $50/mo Pro subscription[/dim]")
            return

        # --- Spike days only ---
        if spikes:
            spike_days = {d: v for d, v in daily.items() if v["count"] > DAILY_LIMIT}
            if as_json:
                print(json.dumps({d: spike_days[d] for d in sorted(spike_days, reverse=True)}))
                return
            if not spike_days:
                console.print(f"[green]No days exceeded {DAILY_LIMIT:,} call quota.[/green]")
                return
            table = Table(title=f"Days Exceeding {DAILY_LIMIT:,} Quota")
            table.add_column("Date", style="bold")
            table.add_column("Calls", justify="right")
            table.add_column("Overage Cost", justify="right")
            table.add_column("Input MTok", justify="right")
            table.add_column("Output MTok", justify="right")
            for d in sorted(spike_days, reverse=True):
                v = spike_days[d]
                table.add_row(
                    d,
                    f"[red]{v['count']:,}[/red]",
                    f"${v['amount']:.2f}",
                    f"{v['input_tokens'] / 1e6:.2f}",
                    f"{v['output_tokens'] / 1e6:.2f}",
                )
            active_days = sum(1 for v in daily.values() if v["count"] > 0)
            console.print(table)
            console.print(f"[dim]{len(spike_days)} spike days out of {active_days} active days[/dim]")
            return

        # --- Default: daily report (last N days) ---
        sorted_days = sorted(daily.keys(), reverse=True)[:days]
        if as_json:
            print(json.dumps({d: daily[d] for d in sorted_days}))
            return

        table = Table(title=f"Daily Usage (last {days} days)")
        table.add_column("Date", style="bold")
        table.add_column("Calls", justify="right")
        table.add_column("Input MTok", justify="right")
        table.add_column("Output MTok", justify="right")
        table.add_column("Cost", justify="right")
        table.add_column("Avg Tok/Call", justify="right")
        for d in sorted_days:
            v = daily[d]
            avg_tok = (v["input_tokens"] + v["output_tokens"]) / v["count"] if v["count"] else 0
            call_style = "red" if v["count"] > DAILY_LIMIT else "green"
            table.add_row(
                d,
                f"[{call_style}]{v['count']:,}[/{call_style}]",
                f"{v['input_tokens'] / 1e6:.2f}",
                f"{v['output_tokens'] / 1e6:.2f}",
                f"${v['amount']:.2f}",
                f"{avg_tok:,.0f}",
            )
        # Summary row
        r_calls = sum(daily[d]["count"] for d in sorted_days)
        r_cost = sum(daily[d]["amount"] for d in sorted_days)
        r_in = sum(daily[d]["input_tokens"] for d in sorted_days)
        r_out = sum(daily[d]["output_tokens"] for d in sorted_days)
        active = sum(1 for d in sorted_days if daily[d]["count"] > 0)
        table.add_section()
        table.add_row(
            f"[bold]TOTAL[/bold]",
            f"[bold]{r_calls:,}[/bold]",
            f"[bold]{r_in / 1e6:.2f}[/bold]",
            f"[bold]{r_out / 1e6:.2f}[/bold]",
            f"[bold]${r_cost:.2f}[/bold]",
            f"[bold]{(r_in + r_out) / r_calls:,.0f}[/bold]" if r_calls else "-",
        )
        console.print(table)
        console.print(f"[dim]Active days: {active}/{len(sorted_days)} | "
                      f"Avg calls/active day: {r_calls // active if active else 0:,} | "
                      f"Over-quota days: {sum(1 for d in sorted_days if daily[d]['count'] > DAILY_LIMIT)}[/dim]")

    except Exception as e:
        if as_json:
            print(json.dumps({"error": str(e)}))
        else:
            console.print(f"[red]Error generating report: {e}[/red]")
        sys.exit(1)


@app.command()
def acquire(
    timeout: float = typer.Option(90.0, help="Max seconds to wait for a slot"),
):
    """Acquire a Chutes concurrency slot (blocks until available).

    Prints the slot index to stdout. Hold the process open to keep the slot.
    Use Ctrl+C to release.
    """
    from throttle import ChutesSemaphore

    sem = ChutesSemaphore(timeout=timeout)
    try:
        slot = sem.acquire()
        print(slot)  # stdout for bash callers
        console.print(f"[green]Acquired slot {slot}. Press Ctrl+C to release.[/green]", highlight=False)
        import signal
        signal.pause()
    except TimeoutError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    except KeyboardInterrupt:
        pass
    finally:
        sem.release()
        console.print("[dim]Slot released.[/dim]")


@app.command()
def release():
    """Show current slot usage (no-op — slots auto-release on process exit)."""
    from throttle import ChutesSemaphore

    in_use = ChutesSemaphore.slots_in_use()
    console.print(f"Concurrency: {in_use}/5 slots in use")


@app.command("slots")
def slots_status():
    """Show how many concurrency slots are currently in use."""
    from throttle import ChutesSemaphore

    in_use = ChutesSemaphore.slots_in_use()
    bar = "\u2588" * in_use + "\u2591" * (5 - in_use)
    style = "green" if in_use < 4 else "yellow" if in_use < 5 else "red"
    console.print(f"[{style}]{bar}[/{style}] {in_use}/5 slots")


if __name__ == "__main__":
    app()
