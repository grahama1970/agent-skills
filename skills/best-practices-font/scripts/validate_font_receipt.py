#!/usr/bin/env python3
"""Validate a bounded font proof receipt."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import typer
except ImportError:  # pragma: no cover - exercised by sanity environment if missing
    print("FAIL: typer is required for this CLI", file=sys.stderr)
    raise

app = typer.Typer(add_completion=False)

VALID_STATUSES = {"PASS", "FAIL", "NOT_TESTED", "BLOCKED"}
REQUIRED_GATES = tuple(f"F{i}" for i in range(10))


@dataclass(frozen=True)
class FontReceipt:
    data: dict[str, Any]

    def validate(self) -> list[str]:
        failures: list[str] = []
        if self.data.get("schema") != "font.proof_receipt.v1":
            failures.append("schema must be font.proof_receipt.v1")
        if not self.data.get("world_model"):
            failures.append("world_model is required")
        if not self.data.get("type_position"):
            failures.append("type_position is required")
        roles = self.data.get("roles")
        if not isinstance(roles, dict):
            failures.append("roles must be an object")
        else:
            for role in ("display", "reading", "utility", "data", "code"):
                if role not in roles:
                    failures.append(f"roles.{role} is required")
        assets = self.data.get("assets")
        if not isinstance(assets, list) or not assets:
            failures.append("assets must be a non-empty list")
        else:
            for index, asset in enumerate(assets):
                if not isinstance(asset, dict):
                    failures.append(f"assets[{index}] must be an object")
                    continue
                for key in ("family", "path_or_url", "source", "license", "hosting"):
                    if not asset.get(key):
                        failures.append(f"assets[{index}].{key} is required")
        evidence = self.data.get("evidence")
        if not isinstance(evidence, dict):
            failures.append("evidence must be an object")
        else:
            for key in ("commands", "screenshots", "computed_styles"):
                if key not in evidence:
                    failures.append(f"evidence.{key} is required")
        gates = self.data.get("gates")
        if not isinstance(gates, dict):
            failures.append("gates must be an object")
        else:
            for gate in REQUIRED_GATES:
                status = gates.get(gate)
                if status not in VALID_STATUSES:
                    failures.append(f"gates.{gate} must be one of {sorted(VALID_STATUSES)}")
        if not self.data.get("does_not_prove"):
            failures.append("does_not_prove must name remaining unproved claims")
        return failures


@app.command()
def main(receipt: Path) -> None:
    """Validate RECEIPT and exit non-zero on contract drift."""
    data = json.loads(receipt.read_text(encoding="utf-8"))
    failures = FontReceipt(data).validate()
    if failures:
        typer.echo(f"FAIL: {len(failures)} font receipt issue(s)")
        for failure in failures:
            typer.echo(f"  {failure}")
        raise typer.Exit(1)
    typer.echo("OK: font receipt validates")


if __name__ == "__main__":
    app()
