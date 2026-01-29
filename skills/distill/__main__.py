#!/usr/bin/env python3
"""Distill skill - thin wrapper that imports from the modular package.

This file exists for backwards compatibility with scripts that run:
    python distill.py --file ...

The actual implementation is in the distill/ package modules.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add parent to path so 'distill' package is importable
SCRIPT_DIR = Path(__file__).parent
PARENT_DIR = SCRIPT_DIR.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

# Import from cli module
from distill.cli import main, distill

if __name__ == "__main__":
    sys.exit(main())
