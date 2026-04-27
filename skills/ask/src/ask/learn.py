"""Thin CLI entrypoint for the ask learning pipeline."""

#!/usr/bin/env python3
"""
/ask learn entry point -- delegates to pipeline module.

This file exists so that `run.sh learn` can call the Typer entry point
while the actual implementation lives in the split modules.
"""

from .pipeline import app

if __name__ == "__main__":
    app()
