#!/usr/bin/env python3
"""pdf-lab CLI facade.

Inputs: command-line arguments delegated to Typer commands in cli_parts.
Outputs: command-specific JSON/text/artifacts.
Failure modes: command handlers raise Typer exits for invalid inputs and runtime failures.
"""

from __future__ import annotations

from pathlib import Path


def _load_cli_parts() -> None:
    parts_dir = Path(__file__).resolve().parent / "cli_parts"
    for part in sorted(parts_dir.glob("part*.py")):
        code = compile(part.read_text(encoding="utf-8"), str(part), "exec")
        exec(code, globals())


_load_cli_parts()


if __name__ == "__main__":
    main()
