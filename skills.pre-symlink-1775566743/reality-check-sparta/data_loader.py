"""Database access utilities for SPARTA Reality Check.

Handles DuckDB connection management, including copying the database
to avoid locking issues during read-only analysis.
"""

import os
import shutil
import sys
from pathlib import Path


def get_db_copy(db_path: Path) -> Path:
    """Create a read-only copy of the database (handles locks).

    Args:
        db_path: Path to the original DuckDB database

    Returns:
        Path to the copy (or original if copy fails)
    """
    copy_path = Path(f"/tmp/sparta_reality_check_{os.getpid()}.duckdb")
    try:
        shutil.copy(db_path, copy_path)
        return copy_path
    except Exception as e:
        print(f"WARNING: Could not copy DB: {e}", file=sys.stderr)
        return db_path
