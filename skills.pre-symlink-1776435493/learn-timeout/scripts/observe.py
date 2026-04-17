"""Record actual outcome for feedback loop."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import typer
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

app = typer.Typer(add_completion=False)

OBSERVATIONS_PATH = Path(__file__).resolve().parent.parent / "data" / "observations.jsonl"


@app.command()
def main(
    task_id: str = typer.Option(..., help="Unique task identifier"),
    actual_seconds: float = typer.Option(..., help="Actual duration in seconds"),
    timed_out: bool = typer.Option(False, help="Whether the task timed out"),
    task_type: str = typer.Option("pdf_extraction", help="Task type"),
    page_count: int = typer.Option(0, help="Page count (if applicable)"),
    file_size_mb: float = typer.Option(0.0, help="File size in MB"),
    table_pages: int = typer.Option(0, help="Table pages count"),
    domain: str = typer.Option("general", help="Document domain"),
    source: str = typer.Option("unknown", help="Document source"),
    features_json: str = typer.Option("", help="Full features as JSON string"),
) -> None:
    """Append an observation to the feedback log."""
    OBSERVATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Build features dict
    if features_json:
        features = json.loads(features_json)
    else:
        features = {
            "task_type": task_type,
            "page_count": page_count,
            "file_size_mb": file_size_mb,
            "table_pages": table_pages,
            "domain": domain,
            "source": source,
        }

    observation = {
        "task_id": task_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "actual_seconds": actual_seconds,
        "timed_out": timed_out,
        "features": features,
    }

    with open(OBSERVATIONS_PATH, "a") as f:
        f.write(json.dumps(observation) + "\n")

    logger.info(
        f"Observation recorded: task_id={task_id}, "
        f"actual={actual_seconds:.1f}s, timed_out={timed_out}"
    )

    # Count total observations
    count = sum(1 for _ in OBSERVATIONS_PATH.read_text().splitlines() if _.strip())
    print(f"Total observations: {count}")


if __name__ == "__main__":
    app()
