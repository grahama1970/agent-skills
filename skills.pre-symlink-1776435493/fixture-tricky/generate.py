#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pymupdf>=1.23.0",
#     "reportlab>=4.0.0",
#     "typer>=0.9.0",
# ]
# ///
"""
Generate adversarial PDF content that breaks extractors.

Assembles all CLI commands from split modules.
"""
import sys
from pathlib import Path

# Ensure this directory is importable when running as a script
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gen_app import app

# Import modules to register trick data and CLI commands
import gen_tricks_core  # noqa: F401
import gen_tricks_ext  # noqa: F401
import gen_generators  # noqa: F401
import gen_cli  # noqa: F401


if __name__ == "__main__":
    app()
