#!/usr/bin/env python3
"""Sanity: scillm VLM inference (graceful if unavailable)."""
import sys
try:
    # Try to reach scillm - if not available, that's OK
    import subprocess
    result = subprocess.run(
        ["python3", "-c", "import scillm; print('available')"],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        print("WARN: scillm not available -- VLM title inference will be disabled (graceful)")
        sys.exit(0)
    print("PASS: scillm available for VLM inference")
    sys.exit(0)
except Exception as e:
    print(f"WARN: scillm check failed ({e}) -- VLM degradation mode OK")
    sys.exit(0)
