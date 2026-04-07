"""CLI entry point for learn-datalake skill."""

import sys
from typing import Annotated

import typer
from loguru import logger
from rich.console import Console

from . import __version__
from .orchestrator import harvest_strategy_outcomes, run_learning_cycle, run_table_loop

# Initialize Typer
app = typer.Typer(
    name="learn-datalake",
    help="Orchestrate datalake self-improvement loops.",
    add_completion=False,
)
console = Console()


def version_callback(value: bool):
    if value:
        console.print(f"learn-datalake v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool, typer.Option("--version", callback=version_callback, is_eager=True)
    ] = False,
):
    """Orchestrate datalake self-improvement loops."""
    # Configure Loguru
    logger.remove()
    logger.add(
        sys.stderr,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        level="INFO",
    )


@app.command()
def loop(
    loop_type: Annotated[str, typer.Argument(help="The improvement loop to run (e.g., 'table')")],
    glob: Annotated[str, typer.Option(help="File pattern to target")] = "**/*_clean.pdf",
    dry_run: Annotated[
        bool, typer.Option(help="Simulate the loop without executing changes")
    ] = False,
    monitor: Annotated[bool, typer.Option(help="Enable task monitor reporting")] = True,
):
    """Run a specified self-improvement loop on the corpus."""
    if loop_type == "table":
        logger.info(f"Starting 'table' improvement loop (glob='{glob}', dry_run={dry_run})")
        run_table_loop(glob_pattern=glob, dry_run=dry_run, monitor=monitor)
    else:
        logger.error(f"Unknown loop type: {loop_type}. Supported: 'table'")
        raise typer.Exit(code=1)


@app.command()
def harvest(
    data_root: Annotated[
        str, typer.Option(help="Root directory containing extraction data")
    ] = "",
):
    """Harvest S05 strategy outcomes into training JSONL."""
    from pathlib import Path

    root = Path(data_root) if data_root else None
    count = harvest_strategy_outcomes(data_root=root)
    console.print(f"Harvested {count} training records")


@app.command("learn-cycle")
def learn_cycle(
    data_root: Annotated[
        str, typer.Option(help="Root directory containing extraction data")
    ] = "",
):
    """Run full Shadow-LEGO learning cycle: harvest → train → register → promote."""
    from pathlib import Path
    import json as _json

    root = Path(data_root) if data_root else None
    summary = run_learning_cycle(data_root=root)
    console.print(_json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    app()
