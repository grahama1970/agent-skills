#!/usr/bin/env python3
"""validate_phase02_story_contract_prompt - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from spine_prompt_contract_validation import build_receipt, read_json, status_for, validate_phase02


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract", type=Path)
    parser.add_argument("--receipt-dir", type=Path)
    args = parser.parse_args()

    contract = read_json(args.contract)
    blockers = validate_phase02(contract)
    status = status_for("02", blockers)
    receipt = build_receipt(
        phase="02",
        contract_path=args.contract,
        status=status,
        blockers=blockers,
        exercised="phase02 typed story contract prompt, typed source context, interaction matrix, visual continuity seeds, serialized JSON text quarantine",
        unverified="story creative quality, live memory grounding, downstream script generation quality",
    )
    if args.receipt_dir:
        args.receipt_dir.mkdir(parents=True, exist_ok=True)
        (args.receipt_dir / "phase02_story_contract_prompt_validation.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(status)
    return 0 if status == "PASS_STORY_CONTRACT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
