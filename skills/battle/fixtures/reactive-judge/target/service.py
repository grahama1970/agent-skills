"""Intentionally vulnerable fixture service for Battle Judge replay."""

from __future__ import annotations

import subprocess
import sys


def lookup(host: str) -> str:
    command = f"echo lookup:{host}"
    proc = subprocess.run(command, shell=True, capture_output=True, text=True, check=False)
    return proc.stdout


if __name__ == "__main__":
    print(lookup(sys.argv[1] if len(sys.argv) > 1 else "example.com"), end="")
