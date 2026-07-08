#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from spine_prompt_contract_validation import build_receipt, read_json, status_for, validate_phase06


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract", type=Path)
    parser.add_argument("--receipt-dir", type=Path)
    args = parser.parse_args()

    contract = read_json(args.contract)
    blockers = validate_phase06(contract)
    status = status_for("06", blockers)
    receipt = build_receipt(
        phase="06",
        contract_path=args.contract,
        status=status,
        blockers=blockers,
        exercised="phase06 typed script prompt contract, timed beats, transcript, entity environment table, hard asset usage, interaction matrix coverage",
        unverified="dialogue quality, performance quality, storyboard identity success, live image generation",
    )
    if args.receipt_dir:
        args.receipt_dir.mkdir(parents=True, exist_ok=True)
        (args.receipt_dir / "phase06_script_prompt_contract_validation.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(status)
    return 0 if status == "PASS_SCRIPT_CONTRACT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
