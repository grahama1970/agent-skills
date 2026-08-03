#!/usr/bin/env python3
"""audit_pctom_powered_trial_protocol - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pctom_phase7_protocol_lib import DEFAULT_PROTOCOL_PATH, PASS_STATUS, audit_protocol


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the sealed PCTOM-R2 powered-trial protocol.")
    parser.add_argument("--root", type=Path, default=Path("skills/persona-dream/research/prospective-tom"))
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    protocol = args.protocol or args.root / DEFAULT_PROTOCOL_PATH
    receipt = audit_protocol(args.root, protocol, args.receipt_out)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(args.receipt_out)
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
