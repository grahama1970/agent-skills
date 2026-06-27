#!/usr/bin/env python3
"""Validate Watch reference-hydration fail-closed contract outputs."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from watch_reference_hydration import load_json, validate_hydration_plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, help="Hydration plan JSON")
    parser.add_argument("--expect-fail-closed", action="store_true")
    args = parser.parse_args()

    plan = load_json(args.plan)
    errors = validate_hydration_plan(plan, expect_fail_closed=args.expect_fail_closed)
    if errors:
        print("reference_hydration_contract_invalid")
        for error in errors:
            print(error)
        return 1
    print("reference_hydration_contract_ok", plan.get("state"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
