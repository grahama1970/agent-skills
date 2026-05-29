#!/usr/bin/env python3
"""Entry point for bin/cursor-copy and bin/ccopy."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from ccopy.cli import run

if __name__ == "__main__":
    raise SystemExit(run())
