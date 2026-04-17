#!/usr/bin/env python3
"""doc2qra skill - convert documents to QRA pairs with summaries.

This file enables running as a module:
    python -m doc2qra distill --file paper.pdf --scope research
    python -m doc2qra recall-source --source-title "Pavur PhD"

Backward compat: omitting 'distill' auto-inserts it, so
    python -m doc2qra --file paper.pdf
still works.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add parent to path so 'doc2qra' package is importable
SCRIPT_DIR = Path(__file__).parent
PARENT_DIR = SCRIPT_DIR.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

# Import from cli module
from doc2qra.cli import app, _SUBCOMMANDS

if __name__ == "__main__":
    # Backward compat: if first arg is not a known subcommand, default to "distill"
    if len(sys.argv) > 1 and sys.argv[1] not in _SUBCOMMANDS:
        sys.argv.insert(1, "distill")
    app()
