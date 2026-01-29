#!/usr/bin/env python3
"""doc2qra skill - convert documents to QRA pairs with summaries.

This file enables running as a module:
    python -m doc2qra --file paper.pdf --scope research

The actual implementation is in the doc2qra/ package modules.
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
from doc2qra.cli import main, distill

if __name__ == "__main__":
    sys.exit(main())
