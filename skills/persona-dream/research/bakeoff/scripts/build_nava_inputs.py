#!/usr/bin/env python3
"""build_nava_inputs - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from persona_dream_nava_lane.io_utils import read_json  # noqa: E402
from persona_dream_nava_lane.prompt import write_nava_inputs  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build NAVA JSONL inputs from a persona-dream packet.")
    parser.add_argument("--dream-packet", required=True, help="Path to story_assets/dream_packet.json.")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--speaker-wav", default=None, help="Optional consented reference voice WAV for NAVA timbre control.")
    parser.add_argument("--first-frame-image", default=None, help="Optional first-frame image/reference panel for I2AV.")
    args = parser.parse_args()

    packet = read_json(args.dream_packet)
    manifest = write_nava_inputs(
        packet=packet,
        out_dir=args.out_dir,
        speaker_wav=args.speaker_wav,
        first_frame_image=args.first_frame_image,
    )

    print(f"[nava-inputs] {manifest['jsonl_path']}")
    print(f"[nava-inputs] records={len(manifest['records'])}")


if __name__ == "__main__":
    main()
