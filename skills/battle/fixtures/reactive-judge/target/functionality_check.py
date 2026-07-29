"""Functional regression check for the fixture service."""

from __future__ import annotations

import subprocess


proc = subprocess.run(
    ["python", "service.py", "example.com"],
    capture_output=True,
    text=True,
    check=False,
)
if proc.returncode == 0 and "lookup:example.com" in proc.stdout:
    raise SystemExit(0)
raise SystemExit(1)
