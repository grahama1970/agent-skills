#!/usr/bin/env python3
"""Build the planned Watch identity reinforcement loop."""

from __future__ import annotations

import argparse

from watch_reference_hydration import (
    build_identity_reinforcement_plan,
    load_json,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-manifest", required=True, help="watch.identity_reference_manifest.v1 JSON")
    parser.add_argument("--graph-vector-plan", required=True, help="watch.graph_vector_persistence_plan.v1 JSON")
    parser.add_argument("--recall-verification-plan", required=True, help="watch.memory_recall_verification_plan.v1 JSON")
    parser.add_argument("--out", required=True, help="Output JSON path")
    args = parser.parse_args()

    reference_manifest = load_json(args.reference_manifest)
    graph_vector_plan = load_json(args.graph_vector_plan)
    recall_verification_plan = load_json(args.recall_verification_plan)
    plan = build_identity_reinforcement_plan(reference_manifest, graph_vector_plan, recall_verification_plan)
    write_json(args.out, plan)
    print(
        "identity_reinforcement_plan_ok",
        f"{plan['counts']['entity_plan_count']} entities",
        f"{plan['counts']['review_crop_count']} crops",
        f"status={plan['status']}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
