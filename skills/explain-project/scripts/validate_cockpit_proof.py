#!/usr/bin/env python3
"""Validate a deterministic explain-project cockpit proof artifact."""

from __future__ import annotations

from pathlib import Path

import typer

from explain_project_core.cli import validate_proof_command


def main(
    path: Path,
    expect_valid: bool = typer.Option(
        False,
        "--expect-valid",
    ),
) -> None:
    validate_proof_command(
        path,
        expect_valid,
    )


if __name__ == "__main__":
    typer.run(main)
