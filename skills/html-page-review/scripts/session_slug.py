#!/usr/bin/env python3
"""Create a stable review session slug from a URL or path.

RECONSTRUCTED 2026-08-12 from cpython-312 bytecode after the .py source was lost.
Faithful to the disassembly. Now TRACKED.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import typer


def slugify(value: str) -> str:
    parsed = urlparse(value)
    base = f"{parsed.netloc}{parsed.path}" if parsed.netloc else value
    base = base.strip().strip("/") or "page"
    base = re.sub("[^A-Za-z0-9._-]+", "-", base)
    base = re.sub("-+", "-", base).strip("-._")
    return (base or "page")[:80]


def main(value: str) -> None:
    """Create a stable review session slug from a URL or path."""
    print(slugify(value))


if __name__ == "__main__":
    typer.run(main)
