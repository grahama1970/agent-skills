#!/usr/bin/env python3
"""Write a hash-bound post-mux voice handoff plan for an active revision."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from audio_strategy_gate import VOICE_HANDOFF_RELATIVE, VOICE_HANDOFF_SCHEMA, assess_revision_audio_strategy

KAI_AMBIENT_WAV = Path(
    "/mnt/storage12tb/media/personas/shared/embry_kai/assets/youtube/ocean_raw_surfing_audio_2min.wav"
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def build_plan(revision_root: Path, ambient_wav: Path = KAI_AMBIENT_WAV) -> dict[str, Any]:
    transcript_path = revision_root / "phase_06_script/timed_transcript.json"
    audition_path = revision_root / "phase_05_voices/kai_voice_audition.json"
    request_path = revision_root / "phase_11_submit_return/canonical/phase11_live_request.v1.json"
    for required in (transcript_path, audition_path, request_path, ambient_wav):
        if not required.is_file():
            raise SystemExit(f"required handoff source missing: {required}")

    transcript = read_json(transcript_path)
    audition = read_json(audition_path)
    request = read_json(request_path)
    request_sha = str((request.get("approval_bindings") or {}).get("request_body_sha256") or "")
    reference_path = Path(str(audition.get("output_wav") or ""))
    if not reference_path.is_file():
        raise SystemExit(f"Kai conditioning reference missing: {reference_path}")

    lines = []
    for entry in transcript:
        if isinstance(entry, Mapping) and entry.get("speaker") and entry.get("text"):
            lines.append(
                {
                    "speaker": str(entry["speaker"]),
                    "text": str(entry["text"]),
                    "start_s": float(entry["start_s"]),
                    "end_s": float(entry["end_s"]),
                    "voice_direction": str(entry.get("voice_direction") or ""),
                    "render_status": "PENDING_EXACT_LINE_RENDER",
                    "rendered_audio": None,
                }
            )
    if not lines:
        raise SystemExit("timed transcript has no spoken lines")

    audition_text = str(audition.get("tts_render_text") or "")
    exact_match = len(lines) == 1 and audition_text == lines[0]["text"]
    plan = {
        "schema": VOICE_HANDOFF_SCHEMA,
        "status": "BLOCKED_AWAITING_EXACT_LINE_RENDER",
        "run_id": "pipeline-complete",
        "revision_id": revision_root.name,
        "strategy": "post_mux",
        "delivery_mode": "post_mux",
        "provider_request": {
            "request_body_sha256": request_sha,
            "generate_audio": False,
            "dialogue_in_provider_prompts": False,
        },
        "timed_transcript": {
            "revision_relative_path": "phase_06_script/timed_transcript.json",
            "sha256": sha256_file(transcript_path),
            "source_of_truth": True,
        },
        "lines": lines,
        "voice_bindings": {
            "Kai": {
                "engine": str((audition.get("chatterbox_receipt") or {}).get("engine") or "chatterbox_turbo"),
                "source_receipt_relative_path": "phase_05_voices/kai_voice_audition.json",
                "source_receipt_sha256": sha256_file(audition_path),
                "conditioning_reference": {
                    "path": str(reference_path),
                    "sha256": sha256_file(reference_path),
                    "size_bytes": reference_path.stat().st_size,
                    "role": "conditioning_reference_only",
                },
                "audition_text": audition_text,
                "canonical_line_match": exact_match,
                "reuse_audition_as_final_dialogue": False,
            }
        },
        "ambient_beds": [
            {
                "path": str(ambient_wav),
                "sha256": sha256_file(ambient_wav),
                "size_bytes": ambient_wav.stat().st_size,
                "role": "ocean_surf_wind_reference_and_mix_bed",
            }
        ],
        "required_outputs": [
            "exact_line_render.wav",
            "exact_line_render_ffprobe_receipt.json",
            "audio_mix.wav",
            "audio_mix_receipt.json",
            "muxed_provider_return.mp4",
            "ffmpeg_mux_receipt.json",
            "muxed_provider_return_ffprobe_receipt.json",
            "audible_output_review_receipt.json",
        ],
        "gates": {
            "pre_submit": [
                "provider request generate_audio=false",
                "timed transcript path and hash verify",
                "every voice and ambient reference path and hash verify",
            ],
            "post_return": [
                "exact rendered line equals timed transcript text",
                "final MP4 contains an audio stream",
                "final MP4 has audible output",
                "mux and ffprobe receipts bind final MP4 hash",
            ],
        },
        "optional_lipsync": {
            "enabled": False,
            "endpoint": "fal-ai/kling-video/lipsync/audio-to-video",
            "requires_separate_paid_authorization": True,
        },
        "mocked": False,
        "live": True,
        "claims": {
            "proves": [
                "the post-mux strategy is explicit and bound to the active revision, exact transcript, provider request, voice reference, and ambient bed"
            ],
            "does_not_prove": [
                "the canonical line has been rendered",
                "the active repaired Kling request has been submitted",
                "audio has been mixed or muxed",
                "the final video has audible output",
            ],
        },
    }
    return plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("revision_root", type=Path)
    parser.add_argument("--ambient-wav", type=Path, default=KAI_AMBIENT_WAV)
    args = parser.parse_args()
    revision_root = args.revision_root.expanduser().resolve()
    output = revision_root / VOICE_HANDOFF_RELATIVE
    atomic_write_json(output, build_plan(revision_root, args.ambient_wav.expanduser().resolve()))
    assessment = assess_revision_audio_strategy(revision_root)
    print(json.dumps({"path": str(output), "sha256": sha256_file(output), "assessment": assessment.to_dict()}, indent=2))
    return 0 if assessment.voice_handoff_valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
