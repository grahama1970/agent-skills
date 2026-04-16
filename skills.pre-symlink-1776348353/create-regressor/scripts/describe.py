"""Data description CLI for create-regressor.

Usage:
    python scripts/describe.py data.jsonl
    python scripts/describe.py data.csv --json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.data import describe_data

app = typer.Typer(add_completion=False)


@app.command()
def describe(
    input_file: Path = typer.Argument(..., help="Data file to describe"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Describe schema and statistics of a data file."""
    info = describe_data(input_file)

    if output_json:
        print(json.dumps(info, indent=2))
        return

    print(f"\nData: {input_file}")
    print(f"Rows: {info['rows']}")
    print(f"Columns: {len(info['columns'])}\n")

    for col in info["columns"]:
        name = col["name"]
        ctype = col.get("type", "unknown")
        non_null = col.get("non_null", 0)

        if ctype == "numeric":
            print(
                f"  {name:<30} numeric  "
                f"non_null={non_null}  "
                f"min={col.get('min', '?'):.4g}  "
                f"max={col.get('max', '?'):.4g}  "
                f"mean={col.get('mean', '?'):.4g}"
            )
        else:
            unique = col.get("unique", "?")
            vals = col.get("values", [])
            vals_str = f"  values={vals}" if vals else ""
            print(f"  {name:<30} categorical  non_null={non_null}  unique={unique}{vals_str}")


if __name__ == "__main__":
    app()
