#!/usr/bin/env python3
"""Script wrapper for the Battle reactive Judge proof.

Inputs are a target authorization manifest and output directory. Output is the
same round receipt written by ``battle_skill.reactive_judge_round``. This wrapper
exists so ticket proof commands have a stable script path as well as the Typer
CLI entrypoint.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from battle_skill.reactive_judge_round import run_reactive_judge_round


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Battle reactive Judge proof")
    parser.add_argument("--authorization-manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest = args.authorization_manifest
    if not manifest.exists() and not manifest.is_absolute():
        repo_relative = Path(__file__).resolve().parents[3] / manifest
        if repo_relative.exists():
            manifest = repo_relative
    receipt = run_reactive_judge_round(
        authorization_manifest=manifest,
        out_dir=args.out,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
