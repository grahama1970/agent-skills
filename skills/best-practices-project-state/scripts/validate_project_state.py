#!/usr/bin/env python3
"""Validate receipt-backed PROJECT_STATE.md reports.

Inputs are a Markdown report path and an optional JSON output flag. The command
prints either a human-readable pass/fail line or a small JSON object containing
the path, success state, and validation errors. It fails closed for missing
files, missing required sections, absent receipt language, or malformed command
usage.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated

import typer


REQUIRED_SECTIONS = [
    "# Project State:",
    "## Executive Summary",
    "## Evidence Receipts",
    "## What Works",
    "## Outstanding Gaps",
    "## Aspirational Or Stale Material",
    "## Missing Or Regressed Capabilities",
    "## Competitive And Research Landscape",
    "## Project Positioning",
    "## Risks And Unknowns",
    "## Recommended Next Actions",
]

RECEIPT_PATTERNS = [
    re.compile(r"\.artifacts/"),
    re.compile(r"\.ask_artifacts/"),
    re.compile(r"dogpile", re.IGNORECASE),
    re.compile(r"browser-oracle", re.IGNORECASE),
    re.compile(r"summary\.json"),
    re.compile(r"receipt", re.IGNORECASE),
]


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"missing file: {path}"]
    text = path.read_text(encoding="utf-8", errors="replace")
    for section in REQUIRED_SECTIONS:
        if section not in text:
            errors.append(f"missing required section: {section}")
    evidence_section = ""
    marker = "## Evidence Receipts"
    if marker in text:
        evidence_section = text.split(marker, 1)[1].split("\n## ", 1)[0]
    if not any(pattern.search(evidence_section) for pattern in RECEIPT_PATTERNS):
        errors.append(
            "Evidence Receipts section lacks recognizable receipt paths or review artifacts"
        )
    if "not established" not in text.lower() and "receipt" not in text.lower():
        errors.append("report does not use receipt/not-established claim language")
    return errors


def main(
    path: Annotated[Path, typer.Argument(help="Path to PROJECT_STATE.md")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable validation result."),
    ] = False,
) -> None:
    errors = validate(path)
    result = {"path": str(path), "ok": not errors, "errors": errors}
    if json_output:
        typer.echo(json.dumps(result, indent=2, sort_keys=True))
    elif errors:
        for error in errors:
            typer.echo(f"[FAIL] {error}", err=True)
    else:
        typer.echo("[PASS] PROJECT_STATE.md minimum contract satisfied")
    if errors:
        raise typer.Exit(1)


if __name__ == "__main__":
    typer.run(main)
