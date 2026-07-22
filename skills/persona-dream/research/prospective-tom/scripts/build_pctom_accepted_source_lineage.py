#!/usr/bin/env python3
"""Build PCTOM-R2 Phase 3 accepted-source lineage evidence from Gate 0 fixtures."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pctom_phase3_lineage_lib import build_lineage_evidence
from pctom_r2_phase1_lib import ROOT_DEFAULT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--case-root", type=Path, default=None)
    parser.add_argument("--evidence-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    case_root = args.case_root or args.root / "fixtures/gate0/positive/lineage_ok"
    evidence = build_lineage_evidence(args.root, case_root, args.evidence_out)
    if args.json:
        print(json.dumps(evidence, indent=2, sort_keys=True))
    else:
        print(evidence["status"])
        print(args.evidence_out)
    return 0 if not evidence.get("build_errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
