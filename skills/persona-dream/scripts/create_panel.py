#!/usr/bin/env python3
"""Compatibility shim for create_panel.py.

The canonical implementation now lives in pipeline/s05_panels/create_panel.py.
This shim preserves existing callers while the refactor proceeds.
"""
import sys
import runpy
from pathlib import Path

new_path = Path(__file__).resolve().parents[1] / "pipeline" / "s05_panels" / "create_panel.py"
if not new_path.exists():
    print(f"create_panel.py shim: canonical script not found at {new_path}", file=sys.stderr)
    sys.exit(1)

sys.argv[0] = str(new_path)
runpy.run_path(str(new_path), run_name="__main__")
