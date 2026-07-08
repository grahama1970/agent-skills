#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from spine_prompt_contract_validation import build_receipt, read_json, status_for, validate_phase01


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract", type=Path)
    parser.add_argument("--receipt-dir", type=Path)
    args = parser.parse_args()

    contract = read_json(args.contract)
    blockers = validate_phase01(contract)
    status = status_for("01", blockers)
    receipt = build_receipt(
        phase="01",
        contract_path=args.contract,
        status=status,
        blockers=blockers,
        exercised="phase01 typed memory residue prompt contract, source ids/hashes, media hashes, prompt-safe text, serialized JSON text quarantine",
        unverified="live memory DB recall/write, recall quality, UI display, downstream story quality",
    )
    if args.receipt_dir:
        args.receipt_dir.mkdir(parents=True, exist_ok=True)
        (args.receipt_dir / "phase01_memory_residue_contract_validation.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(status)
    return 0 if status == "PASS_MEMORY_RESIDUE_CONTRACT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
