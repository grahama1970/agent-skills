#!/usr/bin/env python3
"""Build PCTOM-R2 Phase 5 crash-safe transition evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pctom_phase5_transition_lib import build_surface, default_phase5_paths
from pctom_r2_phase1_lib import ROOT_DEFAULT
from run_reliability_surface import PASS_STATUS as GATE8_PASS_STATUS, build_receipt as build_gate8_receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--evidence-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    paths = default_phase5_paths(args.root)
    gate8_receipt = build_gate8_receipt(paths["gate8_surface"], paths["gate8_receipt"])
    surface = build_surface(args.root, args.evidence_out, gate8_receipt)
    if args.json:
        print(json.dumps(surface, indent=2, sort_keys=True))
    else:
        print(surface["status"])
        print(args.evidence_out)
    return 0 if gate8_receipt.get("status") == GATE8_PASS_STATUS and not surface.get("build_errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
