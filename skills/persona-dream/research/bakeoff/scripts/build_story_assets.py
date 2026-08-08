#!/usr/bin/env python3
"""build_story_assets - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from persona_dream_av_bakeoff.contract import assert_contract_policy, load_contract  # noqa: E402
from persona_dream_av_bakeoff.story import build_dream_packet, write_story_assets  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build short story, YAML/JSON scenes, and contact-sheet prompt assets.")
    parser.add_argument("--contract", default=None, help="Contract JSON path. Defaults to sample Embry contract.")
    parser.add_argument("--out-dir", required=True, help="Output directory for story assets.")
    args = parser.parse_args()

    contract = load_contract(args.contract)
    assert_contract_policy(contract)
    packet = build_dream_packet(contract)
    paths = write_story_assets(packet, args.out_dir)

    print("[story-assets] wrote:")
    for key, value in paths.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
