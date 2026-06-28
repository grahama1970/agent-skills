#!/usr/bin/env python3
"""Build the planned Watch row-text materialization receipt gate."""

from __future__ import annotations

import argparse

from watch_reference_hydration import (
    build_row_text_materialization_receipt_plan,
    load_json,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track-observation", required=True, help="watch.track_observation payload JSON")
    parser.add_argument("--text-scene-corroboration-plan", required=True, help="watch.text_scene_corroboration_receipt_plan.v1 JSON")
    parser.add_argument("--out", required=True, help="Output JSON path")
    args = parser.parse_args()

    track_observation = load_json(args.track_observation)
    text_scene_corroboration_plan = load_json(args.text_scene_corroboration_plan)
    plan = build_row_text_materialization_receipt_plan(track_observation, text_scene_corroboration_plan)
    write_json(args.out, plan)
    print(
        "row_text_materialization_receipt_plan_ok",
        f"{plan['counts']['planned_source_read_count']} planned reads",
        f"{plan['counts']['blocked_source_ref_count']} blocked refs",
        f"status={plan['status']}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
