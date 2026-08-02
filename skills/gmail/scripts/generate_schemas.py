#!/usr/bin/env python3
"""Generate or verify committed Gmail operation JSON Schemas.

Inputs: the Pydantic plan and receipt models in ``gmail_skill.models``.
Outputs: deterministic JSON Schema files under ``references/``.
Failure modes: exits nonzero when ``--check`` finds schema drift.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from gmail_skill.models import OperationPlan, OperationReceipt


app = typer.Typer(add_completion=False)


def generated_schemas() -> dict[str, dict]:
    """Return the canonical schema documents keyed by committed filename."""

    return {
        "operation-plan.schema.json": OperationPlan.model_json_schema(by_alias=True),
        "operation-receipt.schema.json": OperationReceipt.model_json_schema(by_alias=True),
    }


@app.command()
def main(
    check: bool = typer.Option(False, "--check", help="Fail instead of writing on drift."),
) -> None:
    """Write schemas or prove that committed schemas match the models."""

    references = Path(__file__).resolve().parent.parent / "references"
    references.mkdir(parents=True, exist_ok=True)
    drift: list[str] = []
    for filename, schema in generated_schemas().items():
        path = references / filename
        rendered = json.dumps(schema, indent=2, sort_keys=True) + "\n"
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != rendered:
                drift.append(filename)
        else:
            path.write_text(rendered, encoding="utf-8")
    if drift:
        typer.echo(f"schema drift: {', '.join(drift)}", err=True)
        raise typer.Exit(code=1)
    typer.echo("schemas: PASS" if check else "schemas: written")


if __name__ == "__main__":
    app()
