#!/usr/bin/env python3
"""Build a planned memory window from Watch live tracker events."""

from __future__ import annotations

import argparse

from watch_reference_hydration import (
    build_live_tracking_memory_window_plan,
    load_json,
    load_jsonl,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", required=True, help="Asset metadata JSON")
    parser.add_argument("--events", required=True, help="watch.live_track_update.v1 JSONL")
    parser.add_argument("--out", required=True, help="Output JSON path")
    parser.add_argument("--sample-fps", type=float, default=5.0)
    args = parser.parse_args()

    asset = load_json(args.asset)
    events = load_jsonl(args.events)
    plan = build_live_tracking_memory_window_plan(asset, events, sample_fps=args.sample_fps)
    write_json(args.out, plan)
    print(f"live_tracking_memory_window_plan_ok {plan['track_window_count']} windows {plan['event_count']} events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
