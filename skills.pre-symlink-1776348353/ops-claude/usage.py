#!/usr/bin/env python3
"""
Claude Code usage analytics dashboard.

Wraps ccusage CLI to provide Rich-formatted reports, savings calculators,
rate limit correlation, and figure-compatible JSON exports.
"""

import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Claude Code usage analytics")
console = Console()

# Anthropic API pricing per million tokens (for API-equivalent cost calculation)
# These are "what you'd pay on API" — Max plan pays $0 per token
MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-6": {
        "input": 15.0,
        "output": 75.0,
        "cache_write": 18.75,  # 1.25x input
        "cache_read": 1.50,  # 0.1x input
    },
    "claude-opus-4-5-20251101": {
        "input": 15.0,
        "output": 75.0,
        "cache_write": 18.75,
        "cache_read": 1.50,
    },
    "claude-sonnet-4-5-20250929": {
        "input": 3.0,
        "output": 15.0,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    "claude-sonnet-4-6": {
        "input": 3.0,
        "output": 15.0,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    "claude-haiku-4-5-20251001": {
        "input": 0.80,
        "output": 4.0,
        "cache_write": 1.00,
        "cache_read": 0.08,
    },
}

MAX_PLAN_COST = 100.0  # Monthly Max plan cost (5x)
# Fallback pricing for unknown models (use Sonnet rates)
DEFAULT_PRICING = {"input": 3.0, "output": 15.0, "cache_write": 3.75, "cache_read": 0.30}


def run_ccusage(cmd: str, **kwargs: Any) -> dict:
    """Run ccusage with --json --offline --mode calculate."""
    args = ["ccusage", cmd, "--json", "--offline", "--mode", "calculate"]
    if since := kwargs.get("since"):
        args.extend(["--since", since])
    if until := kwargs.get("until"):
        args.extend(["--until", until])
    if kwargs.get("instances"):
        args.append("--instances")
    if kwargs.get("breakdown"):
        args.append("--breakdown")
    result = subprocess.run(args, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        logger.error(f"ccusage failed: {result.stderr}")
        raise typer.Exit(1)
    return json.loads(result.stdout)


def calc_model_cost(breakdown: dict) -> float:
    """Calculate API-equivalent cost for a single model breakdown entry."""
    model = breakdown.get("modelName", "")
    pricing = MODEL_PRICING.get(model, DEFAULT_PRICING)
    cost = 0.0
    cost += breakdown.get("inputTokens", 0) / 1e6 * pricing["input"]
    cost += breakdown.get("outputTokens", 0) / 1e6 * pricing["output"]
    cost += breakdown.get("cacheCreationTokens", 0) / 1e6 * pricing["cache_write"]
    cost += breakdown.get("cacheReadTokens", 0) / 1e6 * pricing["cache_read"]
    return cost


def calc_day_costs(day: dict) -> tuple[float, dict[str, float]]:
    """Calculate total and per-model API-equivalent cost for a day."""
    model_costs: dict[str, float] = {}
    for bd in day.get("modelBreakdowns", []):
        name = bd.get("modelName", "unknown")
        model_costs[name] = calc_model_cost(bd)
    return sum(model_costs.values()), model_costs


def fmt_tokens(n: int) -> str:
    """Format token count with appropriate suffix."""
    if n >= 1e9:
        return f"{n / 1e9:.2f}B"
    if n >= 1e6:
        return f"{n / 1e6:.1f}M"
    if n >= 1e3:
        return f"{n / 1e3:.1f}K"
    return str(n)


def date_range_args(days: int) -> dict[str, str]:
    """Build since/until args for ccusage from days count."""
    until = datetime.now()
    since = until - timedelta(days=days - 1)
    return {"since": since.strftime("%Y%m%d"), "until": until.strftime("%Y%m%d")}


def short_model(name: str) -> str:
    """Shorten model name for display."""
    if "opus" in name:
        return "Opus"
    if "sonnet" in name:
        return "Sonnet"
    if "haiku" in name:
        return "Haiku"
    return name


@app.command()
def report(
    daily: bool = typer.Option(True, "--daily/--monthly", help="Daily or monthly view"),
    days: int = typer.Option(7, "--days", "-d", help="Number of days to show"),
    as_json: bool = typer.Option(False, "--json", "-j", help="JSON output for automation"),
):
    """Usage dashboard — token volumes and API-equivalent costs."""
    if daily:
        data = run_ccusage("daily", **date_range_args(days))
        entries = data.get("daily", [])
    else:
        data = run_ccusage("monthly")
        entries = data.get("monthly", [])

    if not entries:
        console.print("[yellow]No usage data found.[/yellow]")
        raise typer.Exit(0)

    # Calculate costs for each entry
    enriched = []
    for entry in entries:
        total_cost, model_costs = calc_day_costs(entry)
        enriched.append({**entry, "_api_cost": total_cost, "_model_costs": model_costs})

    if as_json:
        # Build figure-compatible output
        dates = [e.get("date", e.get("month", "")) for e in enriched]
        costs = [e["_api_cost"] for e in enriched]

        # Model breakdown for bar chart
        model_totals: dict[str, float] = defaultdict(float)
        for e in enriched:
            for m, c in e["_model_costs"].items():
                model_totals[short_model(m)] += c

        # Day-of-week heatmap
        heatmap: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for e in enriched:
            date_str = e.get("date", "")
            if date_str:
                dow = datetime.strptime(date_str, "%Y-%m-%d").strftime("%a")
                for m, c in e["_model_costs"].items():
                    heatmap[dow][short_model(m)] += c

        output = {
            "daily" if daily else "monthly": [
                {
                    k: v
                    for k, v in e.items()
                    if not k.startswith("_")
                }
                | {"apiCost": round(e["_api_cost"], 2)}
                for e in enriched
            ],
            "figure_data": {
                "line": {"API Cost": {"x": dates, "y": [round(c, 2) for c in costs]}},
                "bar": {"metrics": {k: round(v, 2) for k, v in model_totals.items()}},
                "heatmap": {dow: {m: round(v, 2) for m, v in models.items()} for dow, models in heatmap.items()},
            },
        }
        print(json.dumps(output, indent=2))
        return

    # Rich table
    period = "Daily" if daily else "Monthly"
    date_col = "Date" if daily else "Month"
    table = Table(title=f"Claude Usage Report ({period}, Last {days} {'Days' if daily else 'Months'})")
    table.add_column(date_col, style="bold")
    table.add_column("Input", justify="right")
    table.add_column("Output", justify="right")
    table.add_column("Cache Write", justify="right")
    table.add_column("Cache Read", justify="right")
    table.add_column("Total Tokens", justify="right")
    table.add_column("API Cost", justify="right")

    total_input = total_output = total_cw = total_cr = total_tokens = 0
    total_cost_sum = 0.0

    for e in enriched:
        label = e.get("date", e.get("month", ""))
        inp = e.get("inputTokens", 0)
        out = e.get("outputTokens", 0)
        cw = e.get("cacheCreationTokens", 0)
        cr = e.get("cacheReadTokens", 0)
        total = e.get("totalTokens", 0)
        cost = e["_api_cost"]

        total_input += inp
        total_output += out
        total_cw += cw
        total_cr += cr
        total_tokens += total
        total_cost_sum += cost

        # Color: red for high-cost days (>$500), green for cache-heavy
        cache_ratio = cr / total if total else 0
        cost_style = "red" if cost > 500 else ("green" if cache_ratio > 0.8 else "")
        cost_str = f"[{cost_style}]${cost:,.2f}[/{cost_style}]" if cost_style else f"${cost:,.2f}"

        table.add_row(label, fmt_tokens(inp), fmt_tokens(out), fmt_tokens(cw), fmt_tokens(cr), fmt_tokens(total), cost_str)

    table.add_section()
    table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold]{fmt_tokens(total_input)}[/bold]",
        f"[bold]{fmt_tokens(total_output)}[/bold]",
        f"[bold]{fmt_tokens(total_cw)}[/bold]",
        f"[bold]{fmt_tokens(total_cr)}[/bold]",
        f"[bold]{fmt_tokens(total_tokens)}[/bold]",
        f"[bold]${total_cost_sum:,.2f}[/bold]",
    )
    console.print(table)

    # Model summary
    all_models = set()
    for e in enriched:
        all_models.update(e.get("modelsUsed", []))
    all_models.discard("<synthetic>")
    console.print(f"\n[dim]Models Used: {', '.join(sorted(all_models))}[/dim]")
    console.print(f"[dim]Max Plan Savings: ${total_cost_sum:,.2f} saved vs API pricing (${MAX_PLAN_COST:.0f} plan cost)[/dim]")
    if total_cost_sum > 0:
        console.print(f"[dim]ROI: {total_cost_sum / MAX_PLAN_COST:.1f}x[/dim]")


@app.command()
def savings(
    monthly: bool = typer.Option(True, "--monthly/--all-time", help="Current month or all time"),
    as_json: bool = typer.Option(False, "--json", "-j", help="JSON output"),
):
    """Max plan ROI calculator — API costs vs subscription."""
    if monthly:
        now = datetime.now()
        since = now.replace(day=1).strftime("%Y%m%d")
        data = run_ccusage("daily", since=since)
        entries = data.get("daily", [])
        period = now.strftime("%B %Y")
    else:
        data = run_ccusage("monthly")
        entries = data.get("monthly", [])
        period = "All Time"

    # Aggregate per-model costs
    model_costs: dict[str, float] = defaultdict(float)
    model_tokens: dict[str, int] = defaultdict(int)
    for entry in entries:
        for bd in entry.get("modelBreakdowns", []):
            name = bd.get("modelName", "unknown")
            display = short_model(name)
            model_costs[display] += calc_model_cost(bd)
            model_tokens[display] += sum(
                bd.get(k, 0) for k in ("inputTokens", "outputTokens", "cacheCreationTokens", "cacheReadTokens")
            )

    total_api = sum(model_costs.values())
    savings_amt = total_api - MAX_PLAN_COST
    roi = total_api / MAX_PLAN_COST if MAX_PLAN_COST > 0 else 0

    if as_json:
        output = {
            "period": period,
            "models": {m: {"api_cost": round(c, 2), "tokens": model_tokens[m]} for m, c in model_costs.items()},
            "total_api_cost": round(total_api, 2),
            "max_plan_cost": MAX_PLAN_COST,
            "savings": round(savings_amt, 2),
            "roi": round(roi, 1),
        }
        print(json.dumps(output, indent=2))
        return

    table = Table(title=f"Claude Max Savings ({period})")
    table.add_column("Model", style="bold")
    table.add_column("Tokens", justify="right")
    table.add_column("API Cost", justify="right")
    table.add_column("Max Cost", justify="right")
    table.add_column("Savings", justify="right", style="green")
    table.add_column("ROI", justify="right")

    first = True
    for model in sorted(model_costs, key=lambda m: model_costs[m], reverse=True):
        cost = model_costs[model]
        max_col = f"${MAX_PLAN_COST:.0f}" if first else "(included)"
        model_savings = cost - (MAX_PLAN_COST if first else 0)
        model_roi = f"{cost / MAX_PLAN_COST:.1f}x" if first else "—"
        table.add_row(
            model,
            fmt_tokens(model_tokens[model]),
            f"${cost:,.2f}",
            max_col,
            f"${model_savings:,.2f}",
            model_roi,
        )
        first = False

    table.add_section()
    table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold]{fmt_tokens(sum(model_tokens.values()))}[/bold]",
        f"[bold]${total_api:,.2f}[/bold]",
        f"[bold]${MAX_PLAN_COST:.0f}[/bold]",
        f"[bold green]${savings_amt:,.2f}[/bold green]",
        f"[bold]{roi:.1f}x[/bold]",
    )
    console.print(table)

    verdict_style = "green" if savings_amt > 0 else "red"
    console.print(f"\n[{verdict_style}]Verdict: Max plan {'saves' if savings_amt > 0 else 'costs'} ${abs(savings_amt):,.2f}/mo ({roi:.1f}x ROI)[/{verdict_style}]")


@app.command()
def correlate(
    days: int = typer.Option(14, "--days", "-d", help="Days to analyze"),
    as_json: bool = typer.Option(False, "--json", "-j", help="JSON output"),
):
    """Rate limit correlation — find patterns between usage and rate limits."""
    # Get daily token volumes
    data = run_ccusage("daily", **date_range_args(days))
    daily_entries = data.get("daily", [])

    # Get blocks for rate limit window analysis
    blocks_data = run_ccusage("blocks", **date_range_args(days))
    blocks = [b for b in blocks_data.get("blocks", []) if not b.get("isGap", False)]

    # Build daily token map
    daily_tokens: dict[str, int] = {}
    for entry in daily_entries:
        daily_tokens[entry["date"]] = entry.get("totalTokens", 0)

    # Count blocks per day and detect gaps (potential rate limit windows)
    daily_blocks: dict[str, int] = defaultdict(int)
    daily_gaps: dict[str, int] = defaultdict(int)
    for block in blocks_data.get("blocks", []):
        date = block["startTime"][:10]
        if block.get("isGap"):
            daily_gaps[date] += 1
        else:
            daily_blocks[date] += 1

    # Build correlation data
    rows = []
    for entry in daily_entries:
        date = entry["date"]
        tokens = entry.get("totalTokens", 0)
        block_count = daily_blocks.get(date, 0)
        gap_count = daily_gaps.get(date, 0)
        pattern = "SPIKE" if tokens > 500_000_000 else "NORMAL"
        rows.append({
            "date": date,
            "tokens": tokens,
            "blocks": block_count,
            "gaps": gap_count,
            "pattern": pattern,
        })

    # Compute simple correlation (tokens vs gaps)
    if len(rows) >= 3:
        tok_vals = [r["tokens"] for r in rows]
        gap_vals = [r["gaps"] for r in rows]
        mean_t = sum(tok_vals) / len(tok_vals)
        mean_g = sum(gap_vals) / len(gap_vals)
        cov = sum((t - mean_t) * (g - mean_g) for t, g in zip(tok_vals, gap_vals))
        var_t = sum((t - mean_t) ** 2 for t in tok_vals)
        var_g = sum((g - mean_g) ** 2 for g in gap_vals)
        denom = (var_t * var_g) ** 0.5
        correlation = cov / denom if denom > 0 else 0.0
    else:
        correlation = 0.0

    # Find threshold where gaps increase
    sorted_by_tok = sorted(rows, key=lambda r: r["tokens"])
    threshold = None
    for i, r in enumerate(sorted_by_tok):
        if r["gaps"] > 1 and r["tokens"] > 0:
            threshold = r["tokens"]
            break

    if as_json:
        output = {
            "correlation": round(correlation, 2),
            "threshold": threshold,
            "days": rows,
        }
        print(json.dumps(output, indent=2))
        return

    table = Table(title=f"Rate Limit Correlation (Last {days} Days)")
    table.add_column("Date", style="bold")
    table.add_column("Tokens", justify="right")
    table.add_column("Blocks", justify="right")
    table.add_column("Gaps", justify="right")
    table.add_column("Pattern", justify="right")

    for r in rows:
        pattern_style = "red bold" if r["pattern"] == "SPIKE" else ""
        pattern_str = f"[{pattern_style}]{r['pattern']}[/{pattern_style}]" if pattern_style else r["pattern"]
        table.add_row(
            r["date"],
            fmt_tokens(r["tokens"]),
            str(r["blocks"]),
            str(r["gaps"]),
            pattern_str,
        )

    console.print(table)
    console.print(f"\n[dim]Correlation (tokens vs gaps): r={correlation:.2f}[/dim]")
    if threshold:
        console.print(f"[dim]Threshold: Gaps increase above ~{fmt_tokens(threshold)} tokens/day[/dim]")
    console.print(f"[dim]Recommendation: Spread Opus-heavy work across sessions when approaching limits[/dim]")


@app.command()
def insights(
    days: int = typer.Option(14, "--days", "-d", help="Days to analyze"),
    as_json: bool = typer.Option(False, "--json", "-j", help="JSON output"),
):
    """Analytics insights — trends, anomalies, and patterns."""
    data = run_ccusage("daily", **date_range_args(days))
    entries = data.get("daily", [])

    if not entries:
        console.print("[yellow]No data found.[/yellow]")
        raise typer.Exit(0)

    # Calculate costs and trends
    enriched = []
    for entry in entries:
        total_cost, model_costs = calc_day_costs(entry)
        enriched.append({**entry, "_api_cost": total_cost, "_model_costs": model_costs})

    # Weekly comparison (this week vs last week)
    mid = len(enriched) // 2
    first_half = enriched[:mid] if mid > 0 else []
    second_half = enriched[mid:] if mid > 0 else enriched
    first_cost = sum(e["_api_cost"] for e in first_half) if first_half else 0
    second_cost = sum(e["_api_cost"] for e in second_half)
    wow_change = ((second_cost - first_cost) / first_cost * 100) if first_cost > 0 else 0

    # Model mix trends
    model_trend: dict[str, list[float]] = defaultdict(list)
    for e in enriched:
        for m, c in e["_model_costs"].items():
            model_trend[short_model(m)].append(c)

    # Cache efficiency over time
    cache_ratios = []
    for e in enriched:
        total = e.get("totalTokens", 0)
        cr = e.get("cacheReadTokens", 0)
        if total > 0:
            cache_ratios.append(cr / total)

    first_cache = sum(cache_ratios[: len(cache_ratios) // 2]) / max(len(cache_ratios) // 2, 1)
    second_cache = sum(cache_ratios[len(cache_ratios) // 2 :]) / max(len(cache_ratios) - len(cache_ratios) // 2, 1)

    # Anomaly detection (>2x daily average)
    costs = [e["_api_cost"] for e in enriched]
    avg_cost = sum(costs) / len(costs) if costs else 0
    anomalies = [e for e in enriched if e["_api_cost"] > avg_cost * 2]

    # Peak hours from blocks
    try:
        blocks_data = run_ccusage("blocks", **date_range_args(days))
        hour_tokens: dict[int, int] = defaultdict(int)
        for block in blocks_data.get("blocks", []):
            if block.get("isGap"):
                continue
            start_hour = int(block["startTime"][11:13])
            hour_tokens[start_hour] += block.get("totalTokens", 0)
        peak_hours = sorted(hour_tokens, key=hour_tokens.get, reverse=True)[:4]
        peak_str = ", ".join(f"{h}:00-{h + 5}:00" for h in sorted(peak_hours))
    except Exception:
        peak_str = "unavailable"

    # Top project from instances
    try:
        inst_data = run_ccusage("daily", instances=True, **date_range_args(days))
        projects = inst_data.get("projects", {})
        project_costs: dict[str, float] = {}
        for proj, proj_entries in projects.items():
            cost = 0.0
            for pe in (proj_entries if isinstance(proj_entries, list) else [proj_entries]):
                c, _ = calc_day_costs(pe)
                cost += c
            display = proj.replace("-home-graham-workspace-", "").replace("-", "/", 1)
            project_costs[display] = cost
        top_projects = sorted(project_costs.items(), key=lambda x: x[1], reverse=True)[:5]
    except Exception:
        top_projects = []

    if as_json:
        output = {
            "trends": {
                "wow_cost_change_pct": round(wow_change, 1),
                "cache_efficiency": {
                    "first_half": round(first_cache * 100, 1),
                    "second_half": round(second_cache * 100, 1),
                },
            },
            "anomalies": [
                {"date": e.get("date", ""), "cost": round(e["_api_cost"], 2), "tokens": e.get("totalTokens", 0)}
                for e in anomalies
            ],
            "peak_hours": peak_str,
            "top_projects": [{"project": p, "cost": round(c, 2)} for p, c in top_projects],
        }
        print(json.dumps(output, indent=2))
        return

    console.print("[bold]Usage Insights[/bold]\n")

    console.print("[bold]Trends:[/bold]")
    direction = "up" if wow_change > 0 else "down"
    style = "red" if wow_change > 20 else ("green" if wow_change < -10 else "")
    change_str = f"[{style}]{abs(wow_change):.0f}% {direction}[/{style}]" if style else f"{abs(wow_change):.0f}% {direction}"
    # Find dominant model
    dominant = max(model_trend, key=lambda m: sum(model_trend[m])) if model_trend else "unknown"
    console.print(f"  - Cost {change_str} week-over-week (mostly {dominant} sessions)")
    console.print(f"  - Cache hit rate: {first_cache * 100:.0f}% → {second_cache * 100:.0f}% over {days} days")
    console.print(f"  - Peak hours (UTC): {peak_str}")

    if anomalies:
        console.print(f"\n[bold]Anomalies:[/bold]")
        for e in anomalies:
            console.print(
                f"  - {e.get('date', '?')}: {fmt_tokens(e.get('totalTokens', 0))} tokens "
                f"(${e['_api_cost']:,.0f}, {e['_api_cost'] / avg_cost:.1f}x normal)"
            )

    if top_projects:
        total_proj_cost = sum(c for _, c in top_projects)
        console.print(f"\n[bold]Top Projects (by API-equivalent cost):[/bold]")
        for i, (proj, cost) in enumerate(top_projects, 1):
            pct = cost / total_proj_cost * 100 if total_proj_cost else 0
            console.print(f"  {i}. {proj:<35s} ${cost:>10,.2f}  ({pct:.1f}%)")


@app.command(name="top-projects")
def top_projects(
    days: int = typer.Option(7, "--days", "-d", help="Days to analyze"),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of projects to show"),
    as_json: bool = typer.Option(False, "--json", "-j", help="JSON output"),
):
    """Per-project usage breakdown."""
    data = run_ccusage("daily", instances=True, **date_range_args(days))
    projects = data.get("projects", {})

    if not projects:
        console.print("[yellow]No project data found.[/yellow]")
        raise typer.Exit(0)

    # Aggregate per project
    results: list[dict] = []
    for proj, proj_entries in projects.items():
        entries_list = proj_entries if isinstance(proj_entries, list) else [proj_entries]
        total_cost = 0.0
        total_tokens = 0
        sessions = len(entries_list)
        for pe in entries_list:
            c, _ = calc_day_costs(pe)
            total_cost += c
            total_tokens += pe.get("totalTokens", 0)
        display = proj.replace("-home-graham-workspace-", "").replace("-", "/", 1)
        results.append({
            "project": display,
            "tokens": total_tokens,
            "api_cost": total_cost,
            "days": sessions,
        })

    results.sort(key=lambda r: r["api_cost"], reverse=True)
    results = results[:limit]

    if as_json:
        output = {"projects": [{**r, "api_cost": round(r["api_cost"], 2)} for r in results]}
        print(json.dumps(output, indent=2))
        return

    table = Table(title=f"Top Projects (Last {days} Days)")
    table.add_column("Project", style="bold")
    table.add_column("Tokens", justify="right")
    table.add_column("API Cost", justify="right")
    table.add_column("Active Days", justify="right")

    total_tok = total_cost = 0
    for r in results:
        total_tok += r["tokens"]
        total_cost += r["api_cost"]
        table.add_row(
            r["project"],
            fmt_tokens(r["tokens"]),
            f"${r['api_cost']:,.2f}",
            str(r["days"]),
        )

    table.add_section()
    table.add_row(
        f"[bold]TOTAL ({len(results)} projects)[/bold]",
        f"[bold]{fmt_tokens(total_tok)}[/bold]",
        f"[bold]${total_cost:,.2f}[/bold]",
        "",
    )
    console.print(table)


if __name__ == "__main__":
    app()
