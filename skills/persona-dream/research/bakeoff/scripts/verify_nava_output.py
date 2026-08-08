#!/usr/bin/env python3
"""verify_nava_output - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import argparse
import difflib
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from persona_dream_nava_lane.io_utils import read_json, write_json  # noqa: E402
from persona_dream_nava_lane.media import ffprobe_duration_seconds, sha256_file  # noqa: E402


def normalize(text: str) -> str:
    keep = []
    for ch in text.lower():
        if ch.isalnum() or ch.isspace():
            keep.append(ch)
    return " ".join("".join(keep).split())


def sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def first_dialogue(packet: dict[str, Any]) -> str:
    for scene in packet.get("scenes", []):
        for shot in scene.get("shots", []):
            if shot.get("dialogue"):
                return shot["dialogue"]
    raise ValueError("No dialogue found in dream packet.")


def upload_to_fal(path: Path) -> str:
    import fal_client

    fal_key = os.getenv("FAL_KEY") or os.getenv("FAL_API_KEY")
    if not fal_key:
        raise RuntimeError("FAL_KEY or FAL_API_KEY is required for --upload-to-fal.")
    os.environ.setdefault("FAL_KEY", fal_key)
    return fal_client.upload_file(str(path))


def transcribe_with_fal(url: str) -> dict[str, Any]:
    import fal_client

    return fal_client.subscribe(
        "fal-ai/whisper",
        arguments={
            "audio_url": url,
            "task": "transcribe",
            "language": "en",
            "chunk_level": "word",
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a NAVA joint-AV output against the dream packet.")
    parser.add_argument("--dream-packet", required=True)
    parser.add_argument("--video-path", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--upload-to-fal", action="store_true", help="Upload output video and run fal Whisper transcript check.")
    args = parser.parse_args()

    packet = read_json(args.dream_packet)
    video_path = Path(args.video_path).expanduser().resolve()
    if not video_path.exists():
        raise FileNotFoundError(video_path)

    expected = first_dialogue(packet)
    duration = ffprobe_duration_seconds(video_path)
    video_url = None
    asr = None
    asr_text = None
    transcript_similarity = None

    if args.upload_to_fal:
        video_url = upload_to_fal(video_path)
        asr = transcribe_with_fal(video_url)
        asr_text = asr.get("text", "")
        transcript_similarity = sim(expected, asr_text)

    checks = {
        "video_exists": True,
        "duration_known": duration is not None,
        "dialogue_expected_present": bool(expected),
        "transcript_similarity_ge_0_82": None if transcript_similarity is None else transcript_similarity >= 0.82,
    }

    machine_verdict = "needs_review"
    if transcript_similarity is not None:
        machine_verdict = "pass" if transcript_similarity >= 0.82 else "fail"

    receipt = {
        "schema_version": "persona_dream_nava_receipt.v0.1",
        "lane": "nava_joint_av",
        "machine_verdict": machine_verdict,
        "video_path": str(video_path),
        "video_sha256": sha256_file(video_path),
        "video_url": video_url,
        "duration_sec": duration,
        "dialogue": {
            "expected": expected,
            "asr_text": asr_text,
            "similarity": transcript_similarity,
            "asr_raw": asr,
        },
        "checks": checks,
        "manual_review_required": [
            "Judge whether NAVA preserved exact dialogue.",
            "Judge whether voice/timbre fits persona.",
            "Judge whether generated visuals match the source-grounded scene contract.",
            "Judge whether NAVA adds unsupported lore or on-screen text.",
            "Judge true audio/action/lip alignment.",
        ],
        "no_write_assertions": {
            "memory_write": False,
            "arango_upsert": False,
            "qdrant_upsert": False,
        },
    }

    write_json(args.out, receipt)
    print(f"[nava-verify] wrote {args.out}")
    print(f"[nava-verify] machine_verdict={machine_verdict}")


if __name__ == "__main__":
    main()
