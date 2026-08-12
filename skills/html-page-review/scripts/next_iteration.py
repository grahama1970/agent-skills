#!/usr/bin/env python3
"""Return the next zero-padded iteration id for a session directory.

RECONSTRUCTED 2026-08-12 from cpython-312 bytecode after the .py source was lost.
Faithful to the disassembly. Now TRACKED.
"""
from __future__ import annotations

import pathlib
import re

import typer


def main(session: pathlib.Path) -> None:
    """Return the next zero-padded iteration id for a session directory."""
    if not session.exists():
        print("0001")
        raise typer.Exit()
    iterations = session / "iterations"
    if not iterations.exists():
        print("0001")
        raise typer.Exit()
    nums = []
    for p in iterations.iterdir():
        if p.is_dir() and re.fullmatch(r"\d{4}", p.name):
            nums.append(int(p.name))
    print(f"{(max(nums) + 1) if nums else 1:04d}")


if __name__ == "__main__":
    typer.run(main)
