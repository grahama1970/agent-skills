#!/usr/bin/env python3
"""Build the planned Watch text/scene corroboration receipt gate."""

from __future__ import annotations

import argparse

from watch_reference_hydration import (
    build_text_scene_corroboration_receipt_plan,
    load_json,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crop-reference-similarity-plan", required=True, help="watch.crop_reference_similarity_receipt_plan.v1 JSON")
    parser.add_argument("--evidence-case-payload", required=True, help="watch_evidence_cases upsert payload or case JSON")
    parser.add_argument("--out", required=True, help="Output JSON path")
    args = parser.parse_args()

    crop_reference_similarity_plan = load_json(args.crop_reference_similarity_plan)
    evidence_case_payload = load_json(args.evidence_case_payload)
    plan = build_text_scene_corroboration_receipt_plan(crop_reference_similarity_plan, evidence_case_payload)
    write_json(args.out, plan)
    print(
        "text_scene_corroboration_receipt_plan_ok",
        f"{plan['counts']['entity_plan_count']} entities",
        f"{plan['counts']['materialized_text_channel_count']}/{plan['counts']['required_text_channel_count']} text channels",
        f"status={plan['status']}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
