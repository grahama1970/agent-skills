"""Prediction CLI for create-regressor.

Usage:
    python scripts/predict.py pdf-duration '{"page_count": 92, "tables": 15}'
    python scripts/predict.py pdf-duration --input batch.jsonl --output predictions.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.models import PredictResult
from lib.storage import load_model

app = typer.Typer(add_completion=False)


@app.command()
def predict(
    name: str = typer.Argument(..., help="Model name to load"),
    features_json: Optional[str] = typer.Argument(None, help="JSON feature dict"),
    input_file: Optional[Path] = typer.Option(None, "--input", "-i", help="Batch input JSONL"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="Batch output JSONL"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Predict using a trained regression model."""
    reg = load_model(name)

    if input_file:
        _predict_batch(reg, name, input_file, output_file, output_json)
        return

    if not features_json:
        logger.error("Provide feature JSON or --input file")
        raise typer.Exit(1)

    fd = json.loads(features_json)
    point, interval = reg.predict(fd)

    result = PredictResult(
        prediction=round(point, 4),
        confidence_interval=[round(interval[0], 4), round(interval[1], 4)],
        features_used=list(fd.keys()),
        model_name=name,
        model_type=reg.model_type,
    )

    if output_json:
        print(result.to_json())
    else:
        print(f"Prediction: {point:.4f}")
        print(f"Confidence: [{interval[0]:.4f}, {interval[1]:.4f}]")
        print(f"Model:      {name} ({reg.model_type})")


def _predict_batch(
    reg: "Regressor",
    name: str,
    input_file: Path,
    output_file: Optional[Path],
    output_json: bool,
) -> None:
    """Run batch predictions from JSONL."""
    from lib.data import _load_jsonl

    rows = _load_jsonl(input_file)
    results = []

    for row in rows:
        point, interval = reg.predict(row)
        results.append({
            "prediction": round(point, 4),
            "confidence_interval": [round(interval[0], 4), round(interval[1], 4)],
            "input": row,
        })

    if output_file:
        with open(output_file, "w") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")
        logger.info(f"Wrote {len(results)} predictions to {output_file}")
    else:
        for r in results:
            print(json.dumps(r))


if __name__ == "__main__":
    app()
