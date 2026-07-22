#!/usr/bin/env python3
"""Build PCTOM-R2 Phase 4 deterministic scoring and abstention surface."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pctom_phase4_scoring_lib import build_surface, default_phase4_paths, write_abstention_fixture
from pctom_r2_phase1_lib import ROOT_DEFAULT
from reveal_and_score_trial import PASS_STATUS, build_receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--evidence-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    paths = default_phase4_paths(args.root)
    write_abstention_fixture(args.root, paths["abstained_commitments"])
    covered_receipt = build_receipt(
        paths["corpus"],
        paths["distributions"],
        paths["branches"],
        paths["covered_commitments"],
        paths["outcome"],
        paths["covered_receipt"],
    )
    abstained_receipt = build_receipt(
        paths["corpus"],
        paths["distributions"],
        paths["branches"],
        paths["abstained_commitments"],
        paths["outcome"],
        paths["abstained_receipt"],
    )
    surface = build_surface(args.root, args.evidence_out, covered_receipt, abstained_receipt)
    if args.json:
        print(json.dumps(surface, indent=2, sort_keys=True))
    else:
        print(surface["status"])
        print(args.evidence_out)
    return 0 if covered_receipt.get("status") == PASS_STATUS and abstained_receipt.get("status") == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
