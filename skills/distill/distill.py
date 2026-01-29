#!/usr/bin/env python3
"""Distill skill entry point - wrapper for backwards compatibility.

Usage:
    python distill.py --file doc.pdf --scope research

The actual implementation is in the distill package modules.
This file makes 'python distill.py' work from this directory.
"""

if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Add parent (skills) directory to path for package imports
    PARENT_DIR = Path(__file__).parent.parent
    if str(PARENT_DIR) not in sys.path:
        sys.path.insert(0, str(PARENT_DIR))

    from distill.cli import main
    sys.exit(main())
