"""CLI entry point for /qra-review."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

app = typer.Typer(help="Human-in-the-loop QRA assessment TUI")

# Ensure graph_memory is importable
_mem_src = str(Path(__file__).parent.parent.parent.parent.parent.parent / "memory" / "src")
if _mem_src not in sys.path:
    sys.path.insert(0, _mem_src)


@app.command()
def main(
    framework: Optional[str] = typer.Option(None, "--framework", "-f", help="Filter by framework (SPARTA, NIST, CWE, D3FEND)"),
    limit: int = typer.Option(50, "--limit", "-l", help="Max candidates to load"),
    mode: str = typer.Option("tui", "--mode", "-m", help="tui or batch"),
    auto_reject_below: Optional[float] = typer.Option(None, "--auto-reject-below", help="Batch mode: reject grounding below threshold"),
    reviewer: str = typer.Option("human", "--reviewer", "-r", help="Reviewer name for audit trail"),
) -> None:
    """Launch QRA review interface."""
    try:
        from graph_memory.candidate_bridge import CandidateBridge
        cb = CandidateBridge()
    except Exception as e:
        logger.error(f"Cannot connect to ArangoDB: {e}")
        raise typer.Exit(1)

    pending = cb.pending_count()
    if pending == 0:
        typer.echo("No pending candidates to review.")
        raise typer.Exit(0)

    typer.echo(f"Found {pending} pending candidates")

    if mode == "batch":
        _run_batch(cb, framework, limit, auto_reject_below, reviewer)
    else:
        _run_tui(cb, framework, limit, reviewer)


def _run_batch(
    cb, framework: Optional[str], limit: int,
    auto_reject_below: Optional[float], reviewer: str,
) -> None:
    """Batch mode: auto-reject below threshold."""
    from rich.console import Console
    console = Console()

    candidates = cb.get_pending(limit=limit, framework=framework)
    console.print(f"[cyan]Loaded {len(candidates)} candidates[/cyan]")

    if auto_reject_below is not None:
        rejected = 0
        for c in candidates:
            grounding = c.get("grounding_score", 0) or c.get("assessment_grounding", 0)
            if grounding < auto_reject_below:
                cb.reject(c["_key"], reviewer, f"auto-reject: grounding {grounding:.3f} < {auto_reject_below}")
                rejected += 1
        console.print(f"[red]Rejected {rejected}[/red] with grounding < {auto_reject_below}")
    else:
        # Just show stats
        stats = cb.get_stats()
        console.print(stats)


def _run_tui(cb, framework: Optional[str], limit: int, reviewer: str) -> None:
    """Launch Textual TUI."""
    from .tui import QRAReviewApp

    candidates = cb.get_pending(limit=limit, framework=framework)
    if not candidates:
        typer.echo("No pending candidates match filter.")
        raise typer.Exit(0)

    app = QRAReviewApp(candidates=candidates, bridge=cb, reviewer=reviewer)
    app.run()


if __name__ == "__main__":
    app()
