#!/usr/bin/env python3
"""Compatibility shim for validate_gate.py.

The canonical implementation now lives in pipeline/s06_gate/validate_gate.py.
This shim preserves existing callers while the refactor proceeds.
"""
import sys
import runpy
from pathlib import Path

new_path = Path(__file__).resolve().parents[1] / "pipeline" / "s06_gate" / "validate_gate.py"
if not new_path.exists():
    print(f"validate_gate.py shim: canonical script not found at {new_path}", file=sys.stderr)
    sys.exit(1)

sys.argv[0] = str(new_path)
runpy.run_path(str(new_path), run_name="__main__")
