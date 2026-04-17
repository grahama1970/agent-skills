#!/usr/bin/env python3
"""N-way concurrent tournament. Two strategies enter, one strategy leaves.

Flow:
1. Analyze dataset
2. /dogpile for initial research
3. Pick N strategies from pool
4. Run all N concurrently (direct subprocess)
5. Read F1 from output files on disk
6. /dogpile with full context on failure
7. Pick next N strategies, repeat
"""
from __future__ import annotations

import json
from pathlib import Path

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from .diagnosis import diagnose_round, round_dogpile
from .dispatch import dispatch_strategies
from .manifest import load_manifest
from .research import analyze_dataset, dogpile_research, pick_strategies
from .scoring import RoundResult, detect_plateau, detect_regression, score_round
from .tracking import recall_prior, store_dogpile, store_round

app = typer.Typer(name="thunderdome", no_args_is_help=True)
console = Console()


@app.command()
def run(
    manifest_path: str = typer.Argument(..., help="Path to manifest YAML"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Run a tournament."""
    manifest = load_manifest(manifest_path)
    data_dir = str(manifest.data_dir)
    gate = manifest.scoring.gate_threshold
    max_rounds = manifest.convergence.max_rounds
    n = manifest.convergence.n_strategies

    logger.info(f"{'=' * 50}")
    logger.info(f"THUNDERDOME: {manifest.name}")
    logger.info(f"  Data: {data_dir}")
    logger.info(f"  Gate: F1 >= {gate}")
    logger.info(f"  Rounds: {max_rounds}, Strategies/round: {n}")
    logger.info(f"{'=' * 50}")

    # Step 1: Analyze dataset
    analytics = analyze_dataset(data_dir)
    logger.info(f"Analytics: {json.dumps(analytics, indent=2)}")

    if dry_run:
        strategies = manifest.strategies if manifest.strategies else pick_strategies(n, round_num=1)
        for s in strategies:
            logger.info(f"Strategy '{s.name}': {s.modality} {s.backbones} lr={s.lr} epochs={s.epochs}")
        console.print(f"[green]DRY RUN[/] — {len(strategies)} strategies ready")
        return

    # Step 2: /dogpile research
    query = (
        f"Training classifier for: {manifest.description or manifest.name}. "
        f"Dataset: {analytics.get('total_samples')} samples, "
        f"{analytics.get('n_classes')} classes, "
        f"images {', '.join(analytics.get('image_sizes', ['?']))}. "
        f"Target: F1>={gate}. Recommend approaches with specific HPs."
    )
    insights = dogpile_research(query, manifest.memory_scope)
    if insights:
        store_dogpile(manifest.name, query, insights, 0, "pre-tournament",
                      manifest.memory_scope)
        logger.info(f"Research: {len(insights)} chars")

    # Step 3: Check /memory for prior runs
    prior = recall_prior(manifest.name, manifest.memory_scope)
    if prior:
        logger.info(f"Found {len(prior)} prior tournament records")

    # Convergence loop
    all_rounds: list[RoundResult] = []
    converged = False

    for round_num in range(1, max_rounds + 1):
        # Pick strategies
        strategies = manifest.strategies if manifest.strategies else pick_strategies(n, round_num)
        logger.info(f"{'─' * 40}")
        logger.info(f"Round {round_num}/{max_rounds} — {len(strategies)} strategies")

        # Run all concurrently
        results = dispatch_strategies(strategies, data_dir, round_num)

        # Score
        scored = [(r.name, r.f1, r.raw_json) for r in results]
        rr = score_round(scored, gate, round_num)
        rr.plateau_detected = detect_plateau(all_rounds + [rr],
                                              manifest.convergence.plateau_window,
                                              manifest.convergence.plateau_epsilon)
        rr.regression_detected = detect_regression(all_rounds + [rr])

        if not rr.gate_passed:
            rr.diagnosis = diagnose_round(rr, all_rounds, manifest)
            logger.warning(f"Gate FAILED: {rr.winner_name}={rr.winner_score:.4f} < {gate}")
        else:
            logger.info(f"Gate PASSED: {rr.winner_name}={rr.winner_score:.4f} >= {gate}")

        all_rounds.append(rr)
        store_round(manifest.name, rr, manifest.memory_scope)

        if rr.gate_passed:
            converged = True
            break

        # /dogpile with full context
        if manifest.dogpile_on_failure:
            round_dogpile(rr, all_rounds, manifest)

        if rr.plateau_detected:
            logger.warning("PLATEAU detected")

    # Final report
    best_score = max((r.winner_score for r in all_rounds), default=0.0)
    best_name = max(all_rounds, key=lambda r: r.winner_score).winner_name if all_rounds else ""

    _print_table(manifest.name, all_rounds, converged)

    report = {
        "tournament": manifest.name,
        "status": "CONVERGED" if converged else "FAILED",
        "rounds": len(all_rounds),
        "best_score": best_score,
        "best_strategy": best_name,
        "gate_threshold": gate,
        "gap_to_gate": round(gate - best_score, 4) if not converged else 0,
        "round_scores": [{"round": r.round_num, "winner": r.winner_name,
                          "score": r.winner_score} for r in all_rounds],
    }

    if not converged:
        logger.error(f"{'=' * 50}")
        logger.error(f"FAILED: {manifest.name}")
        logger.error(f"  Best: {best_name} at {best_score:.4f} (gate={gate})")
        logger.error(f"  Gap: {report['gap_to_gate']:.4f}")
        logger.error(f"{'=' * 50}")

    print(json.dumps(report, indent=2))


@app.command()
def status(name: str = typer.Argument(...)) -> None:
    """Show tournament status from artifacts."""
    from .tracking import ARTIFACTS_DIR
    artifacts = sorted(ARTIFACTS_DIR.glob(f"round_{name}_*.json"))
    if not artifacts:
        console.print(f"[yellow]No artifacts for '{name}'[/]")
        return
    _print_artifacts(name, artifacts)


@app.command(name="list")
def list_cmd() -> None:
    """List tournaments."""
    from .tracking import ARTIFACTS_DIR
    if not ARTIFACTS_DIR.exists():
        console.print("[yellow]No artifacts[/]")
        return
    tournaments: dict[str, int] = {}
    for p in ARTIFACTS_DIR.glob("round_*.json"):
        d = json.loads(p.read_text())
        tournaments[d.get("tournament", "?")] = tournaments.get(d.get("tournament", "?"), 0) + 1
    table = Table(title="Tournaments")
    table.add_column("Name"); table.add_column("Rounds")
    for n, c in sorted(tournaments.items()):
        table.add_row(n, str(c))
    console.print(table)


def _print_table(name: str, rounds: list[RoundResult], converged: bool) -> None:
    table = Table(title=f"{'CONVERGED' if converged else 'FAILED'}: {name}")
    table.add_column("Round"); table.add_column("Winner"); table.add_column("F1")
    table.add_column("Gate"); table.add_column("Notes")
    for r in rounds:
        gate = "[green]PASS[/]" if r.gate_passed else "[red]FAIL[/]"
        notes = []
        if r.plateau_detected: notes.append("PLATEAU")
        if r.regression_detected: notes.append("REGRESSION")
        table.add_row(str(r.round_num), r.winner_name, f"{r.winner_score:.4f}",
                      gate, " ".join(notes))
    console.print(table)


def _print_artifacts(name: str, artifacts: list[Path]) -> None:
    table = Table(title=f"Tournament: {name}")
    table.add_column("Round"); table.add_column("Winner"); table.add_column("F1")
    table.add_column("Gate")
    for p in artifacts:
        d = json.loads(p.read_text())
        gate = "[green]PASS[/]" if d.get("gate_passed") else "[red]FAIL[/]"
        table.add_row(str(d.get("round")), d.get("winner_name", "?"),
                      f"{d.get('winner_score', 0):.4f}", gate)
    console.print(table)


if __name__ == "__main__":
    app()
