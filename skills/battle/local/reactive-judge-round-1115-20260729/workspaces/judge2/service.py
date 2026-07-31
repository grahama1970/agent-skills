"""Patched fixture service for Battle Judge replay."""

from __future__ import annotations

import re
import sys


SAFE_HOST = re.compile(r"^[A-Za-z0-9.-]{1,253}$")


def lookup(host: str) -> str:
    if not SAFE_HOST.fullmatch(host):
        raise ValueError("invalid host")
    return f"lookup:{host}\n"


if __name__ == "__main__":
    print(lookup(sys.argv[1] if len(sys.argv) > 1 else "example.com"), end="")
