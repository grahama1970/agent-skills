"""Feature importance CLI for create-regressor.

Usage:
    python scripts/importance.py pdf-duration
    python scripts/importance.py pdf-duration --top 10 --json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.storage import load_model

app = typer.Typer(add_completion=False)


@app.command()
def importance(
    name: str = typer.Argument(..., help="Model name"),
    top: int = typer.Option(0, "--top", "-k", help="Show top N features (0=all)"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Show feature importance for a trained model."""
    reg = load_model(name)
    imp = reg.feature_importance()

    if not imp:
        print("No feature importance available for this model type.")
        raise typer.Exit(0)

    if top > 0:
        imp = dict(list(imp.items())[:top])

    if output_json:
        print(json.dumps(imp, indent=2))
        return

    print(f"\nFeature importance: {name} ({reg.model_type})\n")
    max_val = max(imp.values()) if imp else 1.0
    for feat, val in imp.items():
        bar_len = int(40 * val / max_val) if max_val > 0 else 0
        bar = "█" * bar_len
        print(f"  {feat:<40} {val:>10.4f}  {bar}")


if __name__ == "__main__":
    app()
