#!/usr/bin/env python3
"""Thin delegate to `run.sh spacing` — single source of the layout law.

Kept for callers that predate the CLI. Requires uv (run.sh provides the
packaged environment with svgelements/typer). Exit mirrors the CLI.
"""
import os
import pathlib
import sys

run_sh = pathlib.Path(__file__).resolve().parents[1] / "run.sh"
os.execv(str(run_sh), [str(run_sh), "spacing", *sys.argv[1:]])
