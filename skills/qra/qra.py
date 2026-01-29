#!/usr/bin/env python3
"""QRA CLI wrapper - runs the qra package.

This thin wrapper allows running `python qra.py` directly.
The actual CLI logic is in __main__.py.

Usage:
    python qra.py --file document.md --scope research
    python -m qra --file document.md --scope research  # also works
"""

import sys
from pathlib import Path

if __name__ == "__main__":
    # Get paths
    script_dir = Path(__file__).parent
    parent_dir = script_dir.parent

    # Remove current dir from path to avoid importing this file as 'qra'
    # when we want the qra package
    sys.path = [p for p in sys.path if p not in ("", ".", str(script_dir))]

    # Add parent so 'qra' package can be found
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))

    # Now import and run
    from qra.__main__ import main
    sys.exit(main())
