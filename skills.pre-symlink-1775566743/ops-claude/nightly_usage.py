#!/usr/bin/env python3
"""
Nightly Claude usage report — scheduled at 6:00am daily.

Generates a daily usage summary, compares against rolling average,
detects anomalies, and stores results to memory.
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

MEMORY_DIR = Path.home() / ".pi" / "memory" / "ops-claude"
REPORT_DIR = Path("/tmp") / "claude-usage"


def run_ccusage(cmd: str, **kwargs) -> dict:
    """Run ccusage with --json --offline."""
    args = ["ccusage", cmd, "--json", "--offline", "--mode", "calculate"]
    if since := kwargs.get("since"):
        args.extend(["--since", since])
    if until := kwargs.get("until"):
        args.extend(["--until", until])
    result = subprocess.run(args, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        logger.error(f"ccusage failed: {result.stderr}")
        return {}
    return json.loads(result.stdout)


def calc_api_cost(entry: dict) -> float:
    """Calculate API-equivalent cost from model breakdowns."""
    from usage import calc_day_costs
    total, _ = calc_day_costs(entry)
    return total


def nightly_report():
    """Generate daily usage report, store to memory, alert on anomalies."""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    yesterday_display = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # 1. Get yesterday's usage
    data = run_ccusage("daily", since=yesterday, until=yesterday)
    entries = data.get("daily", [])
    if not entries:
        logger.warning(f"No usage data for {yesterday_display}")
        return

    day = entries[0]
    day_cost = calc_api_cost(day)
    day_tokens = day.get("totalTokens", 0)

    # 2. Get 7-day rolling average for comparison
    week_ago = (datetime.now() - timedelta(days=8)).strftime("%Y%m%d")
    week_data = run_ccusage("daily", since=week_ago, until=yesterday)
    week_entries = week_data.get("daily", [])

    avg_cost = 0.0
    avg_tokens = 0
    if week_entries:
        costs = [calc_api_cost(e) for e in week_entries]
        avg_cost = sum(costs) / len(costs)
        avg_tokens = sum(e.get("totalTokens", 0) for e in week_entries) // len(week_entries)

    # 3. Anomaly detection
    is_anomaly = day_cost > avg_cost * 2 if avg_cost > 0 else False
    ratio = day_cost / avg_cost if avg_cost > 0 else 0

    # 4. Build summary
    summary = {
        "date": yesterday_display,
        "tokens": day_tokens,
        "api_cost": round(day_cost, 2),
        "avg_7d_cost": round(avg_cost, 2),
        "avg_7d_tokens": avg_tokens,
        "anomaly": is_anomaly,
        "ratio_vs_avg": round(ratio, 2),
        "models": day.get("modelsUsed", []),
    }

    # 5. Store to memory directory
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = MEMORY_DIR / f"usage_{yesterday_display}.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    logger.info(f"Stored usage summary to {summary_path}")

    # 6. Store latest report for quick access
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    latest_path = REPORT_DIR / "claude-usage-latest.json"
    latest_path.write_text(json.dumps(summary, indent=2))

    # 7. Log results
    status = "ANOMALY" if is_anomaly else "NORMAL"
    logger.info(
        f"[{status}] {yesterday_display}: "
        f"{day_tokens:,} tokens, ${day_cost:,.2f} API-equiv "
        f"(avg: ${avg_cost:,.2f}, ratio: {ratio:.1f}x)"
    )

    if is_anomaly:
        logger.warning(
            f"Usage anomaly detected: {yesterday_display} was {ratio:.1f}x "
            f"the 7-day average (${day_cost:,.2f} vs ${avg_cost:,.2f})"
        )

    # 8. Prune old summaries (keep 30 days)
    cutoff = datetime.now() - timedelta(days=30)
    for f in MEMORY_DIR.glob("usage_*.json"):
        try:
            date_str = f.stem.replace("usage_", "")
            file_date = datetime.strptime(date_str, "%Y-%m-%d")
            if file_date < cutoff:
                f.unlink()
                logger.debug(f"Pruned old summary: {f}")
        except ValueError:
            continue


if __name__ == "__main__":
    nightly_report()
