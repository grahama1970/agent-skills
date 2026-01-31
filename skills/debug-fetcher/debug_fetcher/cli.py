"""CLI for learn-fetcher skill.

Provides commands for self-learning URL fetching with memory integration.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Optional

import click
from rich.console import Console
from rich.table import Table

from .memory_bridge import (
    recall_strategy,
    recall_strategies_for_domain,
    learn_strategy,
    get_best_strategy_for_url,
)
from .memory_schema import FetchStrategy
from .strategy_engine import StrategyEngine, exhaust_strategies


console = Console()


@click.group()
def main():
    """Learn-fetcher: Self-learning URL fetcher with memory integration."""
    pass


@main.command("fetch-learn")
@click.argument("url")
@click.option("--no-memory", is_flag=True, help="Disable memory integration")
@click.option("--json-output", is_flag=True, help="Output as JSON")
def fetch_learn(url: str, no_memory: bool, json_output: bool):
    """Fetch a URL with automatic learning.

    Tries all strategies until one succeeds, then stores the winning
    strategy in /memory for future use.
    """
    engine = StrategyEngine(enable_memory=not no_memory)

    # Check if we have a learned strategy
    learned = get_best_strategy_for_url(url) if not no_memory else None
    if learned and not json_output:
        console.print(f"[dim]Found learned strategy: {learned.successful_strategy} for {learned.domain}[/dim]")

    # Execute
    result = engine.exhaust_strategies(url)

    if json_output:
        output = {
            "url": result.url,
            "success": result.success,
            "winning_strategy": result.winning_strategy,
            "attempts": len(result.attempts),
        }
        if result.final_attempt:
            output["status_code"] = result.final_attempt.status_code
            output["content_verdict"] = result.final_attempt.content_verdict
            output["timing_ms"] = result.final_attempt.timing_ms
            output["file_path"] = result.final_attempt.file_path
        print(json.dumps(output, indent=2))
    else:
        if result.success:
            console.print(f"[green]Success![/green] Strategy: {result.winning_strategy}")
            if result.final_attempt:
                console.print(f"  Status: {result.final_attempt.status_code}")
                console.print(f"  Content: {result.final_attempt.content_verdict}")
                console.print(f"  Time: {result.final_attempt.timing_ms}ms")
                if result.final_attempt.file_path:
                    console.print(f"  File: {result.final_attempt.file_path}")
        else:
            console.print(f"[red]Failed[/red] after {len(result.attempts)} attempts")
            for attempt in result.attempts:
                console.print(f"  - {attempt.strategy}: {attempt.error or 'failed'}")

    sys.exit(0 if result.success else 1)


@main.command("fetch-learn-batch")
@click.argument("manifest", type=click.Path(exists=True))
@click.option("--concurrency", "-c", default=4, help="Max concurrent fetches")
@click.option("--no-memory", is_flag=True, help="Disable memory integration")
@click.option("--output", "-o", type=click.Path(), help="Output JSON file")
def fetch_learn_batch(manifest: str, concurrency: int, no_memory: bool, output: Optional[str]):
    """Fetch multiple URLs from a manifest file.

    Manifest should be a text file with one URL per line.
    """
    # Read URLs
    manifest_path = Path(manifest)
    urls = [line.strip() for line in manifest_path.read_text().splitlines() if line.strip() and not line.startswith("#")]

    if not urls:
        console.print("[yellow]No URLs found in manifest[/yellow]")
        sys.exit(0)

    console.print(f"Fetching {len(urls)} URLs with concurrency={concurrency}")

    engine = StrategyEngine(enable_memory=not no_memory)
    results = engine.fetch_batch(urls, concurrency=concurrency)

    # Summarize
    success_count = sum(1 for r in results if r.success)
    fail_count = len(results) - success_count

    console.print(f"\n[green]Success: {success_count}[/green] | [red]Failed: {fail_count}[/red]")

    # Show failures
    if fail_count > 0:
        console.print("\n[red]Failed URLs:[/red]")
        for r in results:
            if not r.success:
                console.print(f"  - {r.url}")

    # Write output
    if output:
        output_data = [
            {
                "url": r.url,
                "success": r.success,
                "winning_strategy": r.winning_strategy,
                "attempts": len(r.attempts),
            }
            for r in results
        ]
        Path(output).write_text(json.dumps(output_data, indent=2))
        console.print(f"\nResults written to: {output}")

    sys.exit(0 if fail_count == 0 else 1)


@main.command("recall")
@click.argument("domain")
@click.option("--json-output", is_flag=True, help="Output as JSON")
def recall_cmd(domain: str, json_output: bool):
    """Show learned strategies for a domain."""
    strategies = recall_strategies_for_domain(domain)

    if not strategies:
        if json_output:
            print(json.dumps({"found": False, "domain": domain, "strategies": []}))
        else:
            console.print(f"[yellow]No learned strategies for {domain}[/yellow]")
        sys.exit(0)

    if json_output:
        output = {
            "found": True,
            "domain": domain,
            "strategies": [
                {
                    "path_pattern": s.path_pattern,
                    "strategy": s.successful_strategy,
                    "success_rate": s.success_rate,
                    "timing_ms": s.timing_ms,
                }
                for s in strategies
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        table = Table(title=f"Learned Strategies for {domain}")
        table.add_column("Path Pattern")
        table.add_column("Strategy")
        table.add_column("Success Rate")
        table.add_column("Avg Time")

        for s in strategies:
            table.add_row(
                s.path_pattern,
                s.successful_strategy,
                f"{s.success_rate:.1%}",
                f"{s.timing_ms}ms",
            )

        console.print(table)


@main.command("export-learnings")
@click.option("--output", "-o", type=click.Path(), default="learnings.json", help="Output file")
def export_learnings(output: str):
    """Export all learned strategies to JSON.

    Note: This queries /memory for all fetch strategies.
    """
    from .memory_bridge import _run_memory_command

    result = _run_memory_command(["recall", "--q", "fetch strategy", "--k", "100"])

    if not result.get("found", False):
        console.print("[yellow]No learned strategies found[/yellow]")
        sys.exit(0)

    strategies = []
    for item in result.get("items", []):
        strategy = FetchStrategy.from_memory_format(item)
        if strategy:
            strategies.append({
                "domain": strategy.domain,
                "path_pattern": strategy.path_pattern,
                "strategy": strategy.successful_strategy,
                "success_rate": strategy.success_rate,
                "timing_ms": strategy.timing_ms,
                "discovered_at": strategy.discovered_at,
            })

    Path(output).write_text(json.dumps(strategies, indent=2))
    console.print(f"Exported {len(strategies)} strategies to {output}")


@main.command("status")
def status():
    """Check skill status and dependencies."""
    from .memory_bridge import MEMORY_SKILL_PATH
    from .strategy_engine import FETCHER_SKILL_PATH, YOUTUBE_SKILL_PATH

    status_data = {
        "ok": True,
        "skill": "learn-fetcher",
        "dependencies": {
            "memory_skill": MEMORY_SKILL_PATH.exists(),
            "fetcher_skill": FETCHER_SKILL_PATH.exists(),
            "youtube_skill": YOUTUBE_SKILL_PATH.exists(),
        },
    }

    if not all(status_data["dependencies"].values()):
        status_data["ok"] = False

    print(json.dumps(status_data, indent=2))


if __name__ == "__main__":
    main()
