#!/usr/bin/env python3
"""Build a Watch reference-hydration plan for movie or stream assets."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from watch_reference_hydration import build_reference_hydration_plan, load_json, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", required=True, help="Asset metadata JSON")
    parser.add_argument("--reference-candidates", help="Movie reference candidate JSON")
    parser.add_argument("--source-manifest", help="Source-provided stream reference manifest JSON")
    parser.add_argument("--out", required=True, help="Output plan JSON path")
    args = parser.parse_args()

    asset = load_json(args.asset)
    candidates = load_json(args.reference_candidates) if args.reference_candidates else None
    manifest = load_json(args.source_manifest) if args.source_manifest else None
    plan = build_reference_hydration_plan(asset, reference_candidates=candidates, source_manifest=manifest)
    write_json(args.out, plan)
    print("reference_hydration_plan_ok", plan["state"])
    print("fail_closed", plan["fail_closed"]["active"])
    print("can_promote_identity", plan["gates"]["can_promote_identity"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
