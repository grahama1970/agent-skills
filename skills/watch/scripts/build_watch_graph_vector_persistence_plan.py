#!/usr/bin/env python3
"""Build planned Arango/Qdrant persistence records for Watch live windows."""

from __future__ import annotations

import argparse

from watch_reference_hydration import (
    build_graph_vector_persistence_plan,
    load_json,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-window-plan", required=True, help="watch.live_tracking_memory_window_plan.v1 JSON")
    parser.add_argument("--out", required=True, help="Output JSON path")
    args = parser.parse_args()

    live_window_plan = load_json(args.live_window_plan)
    plan = build_graph_vector_persistence_plan(live_window_plan)
    write_json(args.out, plan)
    counts = plan["counts"]
    print(
        "graph_vector_persistence_plan_ok",
        f"{counts['track_observations']} observations",
        f"{counts['evidence_cases']} cases",
        f"{counts['qdrant_point_plans']} qdrant_point_plans",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
