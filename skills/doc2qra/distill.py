#!/usr/bin/env python3
"""DEPRECATED: Use doc2qra instead.

This file exists for backwards compatibility.
The actual implementation is in cli.py.
"""

if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Add parent (skills) directory to path for package imports
    PARENT_DIR = Path(__file__).parent.parent
    if str(PARENT_DIR) not in sys.path:
        sys.path.insert(0, str(PARENT_DIR))

    from doc2qra.cli import main
    sys.exit(main())
