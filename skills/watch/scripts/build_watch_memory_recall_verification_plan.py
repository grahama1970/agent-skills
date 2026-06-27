#!/usr/bin/env python3
"""Build planned $memory recall probes for Watch graph/vector persistence."""

from __future__ import annotations

import argparse

from watch_reference_hydration import (
    build_memory_recall_verification_plan,
    load_json,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph-vector-plan", required=True, help="watch.graph_vector_persistence_plan.v1 JSON")
    parser.add_argument("--out", required=True, help="Output JSON path")
    args = parser.parse_args()

    graph_vector_plan = load_json(args.graph_vector_plan)
    plan = build_memory_recall_verification_plan(graph_vector_plan)
    write_json(args.out, plan)
    print(
        "memory_recall_verification_plan_ok",
        f"{len(plan['recall_requests'])} requests",
        f"status={plan['verification_status']}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
