#!/usr/bin/env python3
"""build_pctom_evidence_scope_ledger - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pctom_r2_phase1_lib import ROOT_DEFAULT, build_evidence_scope_ledger


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the PCTOM-R2 evidence scope ledger.")
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    ledger = build_evidence_scope_ledger(args.root, args.out)
    if args.json:
        print(json.dumps(ledger, indent=2, sort_keys=True))
    else:
        print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
