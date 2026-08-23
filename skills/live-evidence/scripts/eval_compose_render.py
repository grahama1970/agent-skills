#!/usr/bin/env python3
"""Prove the compose RENDER node: the final node of a compose DAG renders a
REAL D3 figure from a metrics table via the create-figure skill.

This is the execute half of the compose feature (case compose-action-wiring
covers the propose half). It invokes create-figure for real and checks bytes on
disk -- no mock. It also checks the spoken-metrics extractor and graceful
handling when there are no numbers to plot.

create-figure missing -> INFRA_BLOCKED, never a fake pass.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "src"))

from live_evidence.actions import _extract_metrics, render_composition

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{name}: {'PASS' if ok else 'FAIL'}{f' ({detail})' if detail else ''}")
    if not ok:
        FAILURES.append(name)


def main() -> int:
    if not (SKILL.parent / "create-figure" / "run.sh").is_file():
        print("compose render: INFRA_BLOCKED (create-figure not installed)")
        return 0

    metrics = _extract_metrics(
        "graph our latest numbers: coverage 72, supply chain 58, freshness 91")
    check("spoken metrics are extracted into a table",
          metrics == {"Coverage": 72.0, "Supply Chain": 58.0, "Freshness": 91.0},
          f"metrics={metrics}")

    render = render_composition(metrics, Path(tempfile.mkdtemp(prefix="le-compose-render-")))
    figure = render.get("figure_path")
    on_disk = bool(figure) and Path(figure).is_file() and Path(figure).stat().st_size > 10_000
    check("compose render produces a REAL figure via create-figure",
          bool(render.get("ok")) and on_disk,
          f"bytes={render.get('bytes')} renderer={render.get('renderer')}")

    empty = render_composition({}, Path(tempfile.mkdtemp(prefix="le-compose-empty-")))
    check("no numeric metrics -> nothing rendered (graceful, not a crash)",
          empty.get("ok") is False, f"reason={empty.get('reason')}")

    print()
    if FAILURES:
        print(f"compose render: FAIL ({len(FAILURES)} failed: {', '.join(FAILURES)})")
        return 1
    print("compose render: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
