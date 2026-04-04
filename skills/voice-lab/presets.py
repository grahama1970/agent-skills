"""Preset storage for persona RVC parameter tuning.

Presets are per-persona JSON files storing the winning parameter combinations
from sweep runs.

Merged from hum-lab/src/presets.py.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

from evaluate import EvalScores
from sweep import SweepRun, find_latest_sweep

console = Console()

STORAGE_ROOT = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "media"


def _presets_dir(persona: str) -> Path:
    return STORAGE_ROOT / "personas" / persona / "hum-cache" / "presets"


def save_preset(
    persona: str,
    name: str,
    params: dict,
    scores: Optional[EvalScores] = None,
    reference_track: str = "",
) -> Path:
    """Save a parameter preset for a persona."""
    presets_dir = _presets_dir(persona)
    presets_dir.mkdir(parents=True, exist_ok=True)

    preset = {
        "persona": persona,
        "name": name,
        "params": params,
        "reference_track": reference_track,
        "created": datetime.now().isoformat(),
    }
    if scores:
        preset["scores"] = scores.to_dict()

    path = presets_dir / f"{name}.json"
    with open(path, "w") as f:
        json.dump(preset, f, indent=2)

    console.print(f"[green]Preset saved:[/green] {path}")
    return path


def load_preset(persona: str, name: str = "default") -> Optional[dict]:
    """Load a parameter preset. Returns the params dict or None."""
    path = _presets_dir(persona) / f"{name}.json"
    if not path.exists():
        return None

    with open(path) as f:
        data = json.load(f)
    return data.get("params")


def list_presets(persona: str) -> list[dict]:
    """List all presets for a persona."""
    presets_dir = _presets_dir(persona)
    if not presets_dir.exists():
        return []

    presets = []
    for p in sorted(presets_dir.glob("*.json")):
        with open(p) as f:
            data = json.load(f)
        presets.append(data)
    return presets


def print_presets(persona: str) -> None:
    """Display presets in a table."""
    presets = list_presets(persona)
    if not presets:
        console.print(f"[yellow]No presets for {persona}[/yellow]")
        return

    table = Table(title=f"Presets for {persona}")
    table.add_column("Name", style="bold")
    table.add_column("Pitch")
    table.add_column("F0 Method")
    table.add_column("Index Rate")
    table.add_column("Filter Radius")
    table.add_column("Protect")
    table.add_column("Overall", justify="right")
    table.add_column("Track")

    for p in presets:
        params = p.get("params", {})
        scores = p.get("scores", {})
        overall = scores.get("overall", "")
        if overall:
            overall = f"{overall:.3f}"

        table.add_row(
            p.get("name", "?"),
            str(params.get("pitch", "")),
            str(params.get("f0method", "")),
            str(params.get("index_rate", "")),
            str(params.get("filter_radius", "")),
            str(params.get("protect", "")),
            overall,
            p.get("reference_track", ""),
        )

    console.print(table)


def save_winner(
    persona: str,
    track: Optional[str] = None,
    name: str = "default",
) -> Optional[Path]:
    """Save the winning parameters from the latest sweep as a preset."""
    sweep_path = find_latest_sweep(persona, track)
    if sweep_path is None:
        console.print(f"[red]No sweep results found for {persona}[/red]")
        return None

    run = SweepRun.load(sweep_path)
    ranked = run.ranked()

    if not ranked:
        console.print("[red]No scored results in sweep[/red]")
        return None

    winner = None
    for r in ranked:
        passed, _ = r.scores.passes_gates()
        if passed:
            winner = r
            break

    if winner is None:
        winner = ranked[0]
        console.print(
            "[yellow]Warning: No result passes all quality gates. "
            "Saving best overall.[/yellow]"
        )

    console.print(f"[bold]Winner:[/bold] {winner.params}")
    console.print(f"  Overall: {winner.scores.overall:.3f}")

    return save_preset(
        persona=persona,
        name=name,
        params=winner.params,
        scores=winner.scores,
        reference_track=run.track,
    )
