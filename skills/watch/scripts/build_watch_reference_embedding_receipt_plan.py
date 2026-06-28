#!/usr/bin/env python3
"""Build the planned Watch reference-image embedding receipt gate."""

from __future__ import annotations

import argparse

from watch_reference_hydration import (
    build_reference_embedding_receipt_plan,
    load_json,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-manifest", required=True, help="watch.identity_reference_manifest.v1 JSON")
    parser.add_argument("--identity-reinforcement-plan", required=True, help="watch.identity_reinforcement_plan.v1 JSON")
    parser.add_argument("--out", required=True, help="Output JSON path")
    args = parser.parse_args()

    reference_manifest = load_json(args.reference_manifest)
    identity_reinforcement_plan = load_json(args.identity_reinforcement_plan)
    plan = build_reference_embedding_receipt_plan(reference_manifest, identity_reinforcement_plan)
    write_json(args.out, plan)
    print(
        "reference_embedding_receipt_plan_ok",
        f"{plan['counts']['entity_requirement_count']} entities",
        f"{plan['counts']['planned_reference_image_slot_count']} reference slots",
        f"status={plan['status']}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
