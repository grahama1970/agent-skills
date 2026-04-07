"""Status CLI for create-regressor.

Usage:
    python scripts/status.py
    python scripts/status.py --json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.storage import list_models

app = typer.Typer(add_completion=False)


@app.command()
def status(
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """List all trained regression models."""
    models = list_models()

    if not models:
        print("No trained models found.")
        raise typer.Exit(0)

    if output_json:
        print(json.dumps(models, indent=2))
        return

    print(f"\nTrained models ({len(models)}):\n")
    print(f"{'Name':<25} {'Type':<15} {'MAE':>10} {'R2':>10} {'Samples':>10} {'Version':<20}")
    print("-" * 95)
    for m in models:
        print(
            f"{m.get('model_name', '?'):<25} "
            f"{m.get('model_type', '?'):<15} "
            f"{m.get('mae', 0):>10.3f} "
            f"{m.get('r2', 0):>10.4f} "
            f"{m.get('samples', 0):>10} "
            f"{m.get('version', '?'):<20}"
        )


if __name__ == "__main__":
    app()
