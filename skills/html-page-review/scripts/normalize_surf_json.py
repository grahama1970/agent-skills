#!/usr/bin/env python3
"""Normalize surf js output into valid JSON.

Different surf builds may print raw JSON, a quoted JSON string, or a short
wrapper. This utility extracts the largest plausible JSON object and writes
pretty JSON.

RECONSTRUCTED 2026-08-12 from cpython-312 bytecode after the .py source was lost.
Faithful to the disassembly. Now TRACKED.
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
from typing import Any

import typer


def try_load(s: str) -> Any:
    s = s.strip()
    if not s:
        raise ValueError("empty input")
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    try:
        val = ast.literal_eval(s)
        if isinstance(val, str):
            return json.loads(val)
        return val
    except Exception:
        pass
    starts = [m.start() for m in re.finditer(r"\{", s)]
    ends = [m.end() for m in re.finditer(r"\}", s)]
    last_err: Exception | None = None
    for start in starts:
        for end in reversed(ends):
            if end <= start:
                continue
            candidate = s[start:end]
            try:
                return json.loads(candidate)
            except Exception as exc:
                last_err = exc
    raise ValueError(f"Could not parse surf JSON output: {last_err}")


def main(input: pathlib.Path) -> None:
    """Normalize surf js output into valid JSON and pretty-print to stdout."""
    raw = input.read_text(encoding="utf-8", errors="replace")
    data = try_load(raw)
    if isinstance(data, str):
        data = json.loads(data)
    print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    typer.run(main)
