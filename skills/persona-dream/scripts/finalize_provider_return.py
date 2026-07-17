#!/usr/bin/env python3
"""Build inspectable frames and post-mux audio for one exact provider return."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from audio_strategy_gate import assess_revision_audio_strategy, blockers_for_provider_return
from dialogue_alignment_gate import verify_with_whisper

PLAN_RELATIVE = Path("phase_11_submit_return/preflight/voice_handoff_plan.json")
FRAME_COUNT = 12


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, text=True, capture_output=True)


def ffprobe(path: Path) -> dict[str, Any]:
    result = run([
        "ffprobe", "-v", "error", "-show_streams", "-show_format",
        "-of", "json", str(path),
    ])
    return json.loads(result.stdout)


def video_duration(probe: dict[str, Any]) -> float:
    return float(probe["format"]["duration"])


def binding(revision_root: Path, request_sha256: str) -> tuple[dict[str, Any], Path, Path]:
    plan = read_json(revision_root / PLAN_RELATIVE)
    bound_sha = str(plan.get("provider_request", {}).get("request_body_sha256") or "")
    if bound_sha != request_sha256:
        raise SystemExit(f"request hash does not match voice handoff: {request_sha256} != {bound_sha}")
    return_dir = revision_root / "phase_11_submit_return/provider_return" / request_sha256.removeprefix("sha256:")
    source_video = return_dir / "provider_return.mp4"
    download_receipt = read_json(return_dir / "phase11_download_ffprobe_receipt.v1.json")
    if not source_video.is_file() or sha256_file(source_video) != download_receipt.get("downloaded_sha256"):
        raise SystemExit("provider return is missing or does not match its download receipt")
    return plan, return_dir, source_video


def build_frames(revision_root: Path, request_sha256: str) -> dict[str, Any]:
    plan, return_dir, source_video = binding(revision_root, request_sha256)
    probe = ffprobe(source_video)
    duration = video_duration(probe)
    frames_dir = return_dir / "watch-codex-vision/frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    frames: list[dict[str, Any]] = []
    for index in range(FRAME_COUNT):
        timestamp = round(index * duration / FRAME_COUNT, 6)
        output = frames_dir / f"frame_{index + 1:04d}.jpg"
        run([
            "ffmpeg", "-y", "-ss", f"{timestamp:.6f}", "-i", str(source_video),
            "-frames:v", "1", "-vf", "scale=768:-2", "-q:v", "2", str(output),
        ])
        frames.append({
            "index": index,
            "timestamp_seconds": timestamp,
            "path": str(output),
            "sha256": sha256_file(output),
        })
    manifest_path = return_dir / "watch-codex-vision/frames_manifest.json"
    manifest = {
        "source": str(source_video),
        "source_sha256": sha256_file(source_video),
        "sampling_mode": "uniform",
        "frame_count": FRAME_COUNT,
        "resolution": 768,
        "duration_seconds": duration,
        "frames": frames,
    }
    write_json(manifest_path, manifest)

    contact_sheet = return_dir / "frame_contact_sheet.png"
    montage_command = [
        "montage", *[item["path"] for item in frames], "-tile", "4x3",
        "-geometry", "320x180+4+4", "-background", "#111111", str(contact_sheet),
    ]
    run(montage_command)
    dimensions = run(["identify", "-format", "%w %h", str(contact_sheet)]).stdout.split()
    receipt = {
        "schema": "persona_dream.frame_contact_sheet_receipt.v1",
        "status": "PASS_FRAME_CONTACT_SHEET",
        "run_id": plan["run_id"],
        "revision_id": plan["revision_id"],
        "request_body_sha256": request_sha256,
        "source_video": source_video.name,
        "source_video_sha256": sha256_file(source_video),
        "source_video_duration_seconds": duration,
        "source_frames_manifest": str(manifest_path.relative_to(return_dir)),
        "source_frames_manifest_sha256": sha256_file(manifest_path),
        "frame_count": FRAME_COUNT,
        "layout": {"columns": 4, "rows": 3, "tile_geometry": "320x180+4+4"},
        "output_path": contact_sheet.name,
        "output_sha256": sha256_file(contact_sheet),
        "output_width": int(dimensions[0]),
        "output_height": int(dimensions[1]),
        "command": " ".join(montage_command),
        "mocked": False,
        "live": True,
        "claims": {
            "proves": [
                "twelve timestamped frames were extracted from the hash-bound live provider return",
                "the contact sheet is bound to the frame manifest and exact provider-return MP4",
            ],
            "does_not_prove": ["visual continuity", "persona identity", "final acceptance"],
        },
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    receipt_path = return_dir / "frame_contact_sheet_receipt.v1.json"
    write_json(receipt_path, receipt)
    return {"contact_sheet": str(contact_sheet), "receipt": str(receipt_path), **receipt}


def build_mux(revision_root: Path, request_sha256: str) -> dict[str, Any]:
    plan, return_dir, source_video = binding(revision_root, request_sha256)
    assessment = assess_revision_audio_strategy(revision_root)
    if not assessment.voice_handoff_valid or assessment.delivery_mode != "post_mux":
        raise SystemExit(f"invalid post-mux handoff: {assessment.validation_errors}")
    lines = plan.get("lines") or []
    if len(lines) != 1 or lines[0].get("render_status") != "PASS_EXACT_LINE_RENDER":
        raise SystemExit("exactly one completed rendered line is required")
    rendered = lines[0]["rendered_audio"]
    dialogue = Path(rendered["path"])
    ambience = Path(plan["ambient_beds"][0]["path"])
    if sha256_file(dialogue) != rendered.get("sha256"):
        raise SystemExit("rendered dialogue hash mismatch")
    if sha256_file(ambience) != plan["ambient_beds"][0].get("sha256"):
        raise SystemExit("ambient bed hash mismatch")
    delivery_receipt = read_json(return_dir / "voice_delivery_review_receipt.json")
    if (
        delivery_receipt.get("status") != "PASS_VOICE_DELIVERY_CONTRACT"
        or delivery_receipt.get("rendered_wav_sha256") != sha256_file(dialogue)
    ):
        raise SystemExit("voice delivery contract is missing, failed, or bound to another WAV")
    probe = ffprobe(source_video)
    duration = video_duration(probe)
    line_start = float(lines[0].get("start_s"))
    line_end = float(lines[0].get("end_s"))
    rendered_duration = float(rendered.get("duration_seconds"))
    beat_id = str(lines[0].get("storyboard_beat_id") or "")
    beat_start = float(lines[0].get("storyboard_beat_start_s"))
    beat_end = float(lines[0].get("storyboard_beat_end_s"))
    if not beat_id or not beat_start <= line_start < beat_end:
        raise SystemExit("dialogue onset is not bound inside its storyboard beat")
    if abs((line_end - line_start) - rendered_duration) > 0.05:
        raise SystemExit("dialogue interval does not match rendered WAV duration")
    if line_end > duration:
        raise SystemExit("dialogue interval extends beyond the provider return")
    delay_ms = round(line_start * 1000)

    mix_path = return_dir / "audio_mix.wav"
    mix_command = [
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(ambience), "-i", str(dialogue),
        "-filter_complex",
        (
            f"[0:a]atrim=0:{duration:.6f},asetpts=PTS-STARTPTS,volume=0.18[amb];"
            f"[1:a]adelay={delay_ms}|{delay_ms},volume=1.0[voice];"
            "[amb][voice]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.95[mix]"
        ),
        "-map", "[mix]", "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(mix_path),
    ]
    run(mix_command)
    mix_probe = ffprobe(mix_path)
    mix_receipt = {
        "schema": "persona_dream.audio_mix_receipt.v1",
        "status": "PASS_EXACT_DIALOGUE_AND_AMBIENCE_MIX",
        "request_body_sha256": request_sha256,
        "dialogue_text": lines[0]["text"],
        "dialogue_path": str(dialogue),
        "dialogue_sha256": sha256_file(dialogue),
        "dialogue_delay_ms": delay_ms,
        "ambient_path": str(ambience),
        "ambient_sha256": sha256_file(ambience),
        "ambient_gain": 0.18,
        "output_path": mix_path.name,
        "output_sha256": sha256_file(mix_path),
        "ffprobe": mix_probe,
        "command": mix_command,
        "mocked": False,
        "live": True,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(return_dir / "audio_mix_receipt.json", mix_receipt)
    sync_receipt = {
        "schema": "persona_dream.dialogue_sync_receipt.v1",
        "status": "PASS_DIALOGUE_STORYBOARD_SYNC",
        "request_body_sha256": request_sha256,
        "storyboard_beat_id": beat_id,
        "storyboard_beat_start_s": beat_start,
        "storyboard_beat_end_s": beat_end,
        "dialogue_start_s": line_start,
        "dialogue_end_s": line_end,
        "dialogue_delay_ms": delay_ms,
        "rendered_audio_duration_seconds": rendered_duration,
        "rendered_audio_sha256": sha256_file(dialogue),
        "audio_mix_sha256": sha256_file(mix_path),
        "checks": {
            "onset_inside_bound_storyboard_beat": beat_start <= line_start < beat_end,
            "interval_matches_rendered_audio": abs((line_end - line_start) - rendered_duration) <= 0.05,
            "dialogue_ends_within_video": line_end <= duration,
        },
        "mocked": False,
        "live": True,
        "claims": {
            "proves": ["the rendered dialogue onset is aligned to its declared storyboard beat"],
            "does_not_prove": ["lip synchronization", "subjective timing acceptance"],
        },
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(return_dir / "dialogue_sync_receipt.json", sync_receipt)

    alignment_receipt = verify_with_whisper(
        dialogue_path=dialogue,
        canonical_text=str(lines[0]["text"]),
        timeline_offset_seconds=line_start,
        expected_start_seconds=line_start,
        expected_end_seconds=line_end,
        output_dir=return_dir / "whisper_alignment",
    )
    alignment_receipt["request_body_sha256"] = request_sha256
    alignment_receipt["storyboard_beat_id"] = beat_id
    alignment_path = return_dir / "dialogue_forced_alignment_receipt.v1.json"
    write_json(alignment_path, alignment_receipt)
    if alignment_receipt["status"] != "PASS_FORCED_DIALOGUE_ALIGNMENT":
        raise SystemExit(f"forced dialogue alignment failed: {alignment_receipt['checks']}")

    muxed = return_dir / "muxed_provider_return.mp4"
    mux_command = [
        "ffmpeg", "-y", "-i", str(source_video), "-i", str(mix_path),
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
        "-b:a", "192k", "-t", f"{duration:.6f}", "-movflags", "+faststart", str(muxed),
    ]
    run(mux_command)
    mux_probe = ffprobe(muxed)
    has_audio = any(stream.get("codec_type") == "audio" for stream in mux_probe.get("streams", []))
    volume = run(["ffmpeg", "-i", str(muxed), "-af", "volumedetect", "-f", "null", "-"])
    volume_text = volume.stderr
    mean_match = re.search(r"mean_volume:\s*(-?[\d.]+) dB", volume_text)
    max_match = re.search(r"max_volume:\s*(-?[\d.]+) dB", volume_text)
    mean_db = float(mean_match.group(1)) if mean_match else None
    max_db = float(max_match.group(1)) if max_match else None
    audible = has_audio and mean_db is not None and max_db is not None and mean_db > -60 and max_db > -40
    mux_receipt = {
        "schema": "persona_dream.ffmpeg_mux_receipt.v1",
        "status": "PASS_POST_MUX" if audible else "FAILED_POST_MUX_AUDIBILITY",
        "request_body_sha256": request_sha256,
        "source_video_sha256": sha256_file(source_video),
        "audio_mix_sha256": sha256_file(mix_path),
        "output_path": muxed.name,
        "output_sha256": sha256_file(muxed),
        "command": mux_command,
        "mocked": False,
        "live": True,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    mux_receipt_path = return_dir / "ffmpeg_mux_receipt.json"
    write_json(mux_receipt_path, mux_receipt)
    ffprobe_receipt = {
        "schema": "persona_dream.muxed_provider_return_ffprobe_receipt.v1",
        "status": "PASS_MUXED_RETURN_HAS_AUDIO_STREAM" if has_audio else "FAILED_MUXED_RETURN_MISSING_AUDIO_STREAM",
        "output_path": muxed.name,
        "output_sha256": sha256_file(muxed),
        "ffprobe": mux_probe,
        "mocked": False,
        "live": True,
    }
    write_json(return_dir / "muxed_provider_return_ffprobe_receipt.json", ffprobe_receipt)
    audio_receipt = {
        "schema": "persona_dream.audible_output_review_receipt.v1",
        "status": "PASS_DETERMINISTIC_NON_SILENCE" if audible else "FAILED_DETERMINISTIC_NON_SILENCE",
        "output_path": muxed.name,
        "output_sha256": sha256_file(muxed),
        "has_audio_stream": has_audio,
        "mean_volume_db": mean_db,
        "max_volume_db": max_db,
        "thresholds": {"mean_volume_db_gt": -60, "max_volume_db_gt": -40},
        "review_method": "ffprobe audio stream inspection plus FFmpeg volumedetect",
        "mocked": False,
        "live": True,
        "claims": {
            "proves": ["the final MP4 contains non-silent audio above the declared deterministic thresholds"],
            "does_not_prove": ["subjective voice quality", "lip synchronization", "human listening acceptance"],
        },
    }
    write_json(return_dir / "audible_output_review_receipt.json", audio_receipt)
    blockers = blockers_for_provider_return(
        assessment, mp4_has_audio_stream=has_audio, mux_receipt_present=mux_receipt_path.is_file()
    )
    if blockers or not audible:
        raise SystemExit(f"post-mux gate failed: {blockers or audio_receipt['status']}")
    return {
        "muxed_video": str(muxed),
        "muxed_video_sha256": sha256_file(muxed),
        "forced_alignment_receipt": str(alignment_path),
        "forced_alignment_status": alignment_receipt["status"],
        **audio_receipt,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("frames", "mux", "all"))
    parser.add_argument("revision_root", type=Path)
    parser.add_argument("--request-sha256", required=True)
    args = parser.parse_args()
    revision_root = args.revision_root.expanduser().resolve()
    output: dict[str, Any] = {}
    if args.action in {"frames", "all"}:
        output["frames"] = build_frames(revision_root, args.request_sha256)
    if args.action in {"mux", "all"}:
        output["mux"] = build_mux(revision_root, args.request_sha256)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
