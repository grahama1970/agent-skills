#!/usr/bin/env python3
"""Build the planned Watch crop/reference similarity receipt gate."""

from __future__ import annotations

import argparse

from watch_reference_hydration import (
    build_crop_reference_similarity_receipt_plan,
    load_json,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crop-manifest", required=True, help="watch.tracking_crop_manifest.v1 JSON")
    parser.add_argument("--reference-embedding-receipt-plan", required=True, help="watch.reference_embedding_receipt_plan.v1 JSON")
    parser.add_argument("--out", required=True, help="Output JSON path")
    args = parser.parse_args()

    crop_manifest = load_json(args.crop_manifest)
    reference_embedding_receipt_plan = load_json(args.reference_embedding_receipt_plan)
    plan = build_crop_reference_similarity_receipt_plan(crop_manifest, reference_embedding_receipt_plan)
    write_json(args.out, plan)
    print(
        "crop_reference_similarity_receipt_plan_ok",
        f"{plan['counts']['entity_plan_count']} entities",
        f"{plan['counts']['candidate_crop_count']} crops",
        f"{plan['counts']['planned_similarity_comparison_count']} comparisons",
        f"status={plan['status']}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
