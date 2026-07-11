#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from persona_dream_av_bakeoff.contract import (  # noqa: E402
    assert_contract_policy,
    find_dialogue_shot,
    load_contract,
    write_contract_copy,
)
from persona_dream_av_bakeoff.io_utils import write_json  # noqa: E402
from persona_dream_av_bakeoff.lipsync import generate_lipsync  # noqa: E402
from persona_dream_av_bakeoff.report import write_reports  # noqa: E402
from persona_dream_av_bakeoff.tts_eleven import generate_elevenlabs_tts  # noqa: E402
from persona_dream_av_bakeoff.tts_wavtts import generate_wavtts_tts  # noqa: E402
from persona_dream_av_bakeoff.verify import compare_lanes, verify_lane  # noqa: E402
from persona_dream_av_bakeoff.video import generate_or_use_base_video  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a controlled ElevenLabs vs WavTTS + lip-sync bake-off."
    )
    parser.add_argument("--out-dir", required=True, help="Run output directory.")
    parser.add_argument("--contract", default=None, help="Contract JSON path. Defaults to sample Embry contract.")
    parser.add_argument("--base-video-url", default=None, help="Use an existing 2-10s visible-face base video URL.")
    parser.add_argument(
        "--visual-model",
        default="fal-ai/kling-video/v3/standard/text-to-video",
        help="fal text-to-video model for shared base video.",
    )
    parser.add_argument(
        "--lipsync-model",
        default="fal-ai/kling-video/lipsync/audio-to-video",
        help="fal lipsync model.",
    )
    parser.add_argument("--eleven-voice", default=None, help="Override ElevenLabs voice name/id.")
    parser.add_argument("--skip-elevenlabs", action="store_true", help="Skip ElevenLabs lane.")
    parser.add_argument("--skip-wavtts", action="store_true", help="Skip WavTTS lane.")
    parser.add_argument("--ref-audio", default=None, help="Consented WavTTS reference audio path.")
    parser.add_argument("--ref-text", default=None, help="Exact transcript of WavTTS reference audio.")
    parser.add_argument("--wavtts-cwd", default=None, help="WavTTS repo root / search root for output WAV.")
    parser.add_argument("--wavtts-audio-path", default=None, help="Existing local WavTTS WAV/MP3 output.")
    parser.add_argument(
        "--confirm-voice-consent",
        action="store_true",
        help="Required for WavTTS: confirms reference voice is owned/licensed/consented.",
    )
    parser.add_argument("--no-logs", action="store_true", help="Disable fal queue logs.")
    args = parser.parse_args()

    if args.skip_elevenlabs and args.skip_wavtts:
        raise SystemExit("At least one lane must run.")

    with_logs = not args.no_logs
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    contract = load_contract(args.contract)
    assert_contract_policy(contract)
    shot = find_dialogue_shot(contract)
    contract_path = write_contract_copy(contract, out_dir)

    print(f"[contract] {contract_path}")
    print("[base-video] generating or using shared base video")
    base_video = generate_or_use_base_video(
        contract=contract,
        shot=shot,
        out_dir=out_dir,
        base_video_url=args.base_video_url,
        model_id=args.visual_model,
        with_logs=with_logs,
    )

    lane_receipts: dict[str, dict[str, Any]] = {}
    lane_artifacts: dict[str, dict[str, Any]] = {}

    if not args.skip_elevenlabs:
        print("[lane:elevenlabs] generating TTS")
        lane_dir = out_dir / "lanes" / "elevenlabs"
        tts = generate_elevenlabs_tts(
            contract=contract,
            shot=shot,
            out_dir=lane_dir,
            voice_override=args.eleven_voice,
            with_logs=with_logs,
        )

        print("[lane:elevenlabs] generating lip-sync")
        lipsync = generate_lipsync(
            contract=contract,
            shot=shot,
            lane="elevenlabs",
            out_dir=lane_dir,
            base_video_url=base_video["video_url"],
            audio_url=tts["audio_url"],
            model_id=args.lipsync_model,
            with_logs=with_logs,
        )

        print("[lane:elevenlabs] verifying")
        receipt = verify_lane(
            lane="elevenlabs",
            contract=contract,
            shot=shot,
            base_video=base_video,
            tts=tts,
            lipsync=lipsync,
            out_dir=lane_dir,
            with_logs=with_logs,
        )
        lane_receipts["elevenlabs"] = receipt
        lane_artifacts["elevenlabs"] = {"tts": tts, "lipsync": lipsync}

    if not args.skip_wavtts:
        print("[lane:wavtts] generating/uploading TTS")
        lane_dir = out_dir / "lanes" / "wavtts"
        tts = generate_wavtts_tts(
            contract=contract,
            shot=shot,
            out_dir=lane_dir,
            ref_audio=args.ref_audio,
            ref_text=args.ref_text,
            confirm_voice_consent=args.confirm_voice_consent,
            wavtts_cwd=args.wavtts_cwd,
            wavtts_audio_path=args.wavtts_audio_path,
            upload_to_fal=True,
        )

        print("[lane:wavtts] generating lip-sync")
        lipsync = generate_lipsync(
            contract=contract,
            shot=shot,
            lane="wavtts",
            out_dir=lane_dir,
            base_video_url=base_video["video_url"],
            audio_url=tts["audio_url"],
            model_id=args.lipsync_model,
            with_logs=with_logs,
        )

        print("[lane:wavtts] verifying")
        receipt = verify_lane(
            lane="wavtts",
            contract=contract,
            shot=shot,
            base_video=base_video,
            tts=tts,
            lipsync=lipsync,
            out_dir=lane_dir,
            with_logs=with_logs,
        )
        lane_receipts["wavtts"] = receipt
        lane_artifacts["wavtts"] = {"tts": tts, "lipsync": lipsync}

    comparison = compare_lanes(lane_receipts)
    machine_verdict = "pass" if all(
        lr.get("machine_verdict") == "pass" for lr in lane_receipts.values()
    ) else (
        "needs_review"
        if all(lr.get("machine_verdict") in ("pass", "needs_review") for lr in lane_receipts.values())
        else "fail"
    )

    overall = "needs_manual_review" if machine_verdict == "pass" else machine_verdict

    receipt = {
        "schema_version": "persona_dream_av_bakeoff_receipt.v0.2",
        "overall": overall,
        "machine_verdict": machine_verdict,
        "contract_path": str(contract_path),
        "base_video": base_video,
        "lane_artifacts": lane_artifacts,
        "lane_receipts": lane_receipts,
        "comparison": comparison,
        "manual_review_required": [
            "Watch both final videos.",
            "Score voice persona fit.",
            "Score visible lip-sync quality.",
            "Check whether either lane changes visual/persona lore beyond the source-grounded contract.",
            "Choose winner only after manual review; machine_winner is a screening signal.",
        ],
        "no_write_assertions": {
            "memory_write": False,
            "arango_upsert": False,
            "qdrant_upsert": False,
        },
    }

    write_json(out_dir / "bakeoff_receipt.json", receipt)
    write_reports(receipt, out_dir)

    print("")
    print(f"[done] receipt: {out_dir / 'bakeoff_receipt.json'}")
    print(f"[done] report:  {out_dir / 'report.html'}")
    print(f"[done] machine_verdict={machine_verdict}")
    print(f"[done] machine_winner={comparison.get('machine_winner')}")


if __name__ == "__main__":
    main()
