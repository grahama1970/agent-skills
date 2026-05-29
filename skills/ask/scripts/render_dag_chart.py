#!/usr/bin/env python3
"""Thin wrapper: delegate DAG chart rendering to $phart-dag-chart skill."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2] / "phart-dag-chart"
RUN_SH = SKILL_DIR / "run.sh"


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: render_dag_chart.py <dag.json>", file=sys.stderr)
        return 2
    if not RUN_SH.is_file():
        print("error: phart-dag-chart skill not found", file=sys.stderr)
        return 2
    proc = subprocess.run([str(RUN_SH), "chart", sys.argv[1]], check=False)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
