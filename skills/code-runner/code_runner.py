#!/usr/bin/env python3
"""Compatibility entrypoint for the packaged code-runner CLI."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"


def main() -> None:
    """Dispatch to ``python -m code_runner.cli`` without root-module shadowing."""

    sys.path.insert(0, str(SRC))
    runpy.run_module("code_runner.cli", run_name="__main__")


if __name__ == "__main__":
    main()
