#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pctom_r2_phase1_lib import PASS_ARCHIVE_STATUS, ROOT_DEFAULT, audit_archive_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the PCTOM-R2 archive manifest.")
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = audit_archive_manifest(args.manifest, args.root, args.receipt_out)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(args.receipt_out)
    return 0 if receipt["status"] == PASS_ARCHIVE_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
