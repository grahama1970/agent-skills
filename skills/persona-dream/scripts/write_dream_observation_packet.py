#!/usr/bin/env python3
"""Normalize Watch output into an evidence-only Persona Dream observation packet."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "dream_observation_packet.v1.schema.json"


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def video_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def build_packet(
    watch_root: Path,
    source_video: Path,
    dream_id: str,
    revision_id: str,
    evidence_origin: str,
) -> dict[str, Any]:
    report = read_object(watch_root / "report.json")
    transcript = read_object(watch_root / "transcript.json")
    frames_manifest = read_object(watch_root / "frames_manifest.json")
    frames = frames_manifest.get("frames") if isinstance(frames_manifest.get("frames"), list) else []
    frame_refs = [str(item.get("path")) for item in frames if isinstance(item, dict) and item.get("path")]
    visual_descriptions = report.get("visual_descriptions") if isinstance(report.get("visual_descriptions"), list) else []
    visual_facts = []
    for index, item in enumerate(visual_descriptions):
        if not isinstance(item, dict) or not str(item.get("description") or "").strip():
            continue
        frame_ref = str(item.get("path") or item.get("frame_path") or "")
        visual_facts.append({
            "fact_id": f"visual-{index + 1:03d}",
            "statement": str(item["description"]).strip(),
            "time_range": [float(item.get("timestamp_seconds") or 0), float(item.get("timestamp_seconds") or 0)],
            "evidence_refs": [frame_ref] if frame_ref else frame_refs[index:index + 1],
            "confidence": float(item.get("confidence") or 0.5),
        })
    transcript_segments = transcript.get("segments") if isinstance(transcript.get("segments"), list) else []
    transcript_facts = []
    for index, item in enumerate(transcript_segments):
        if not isinstance(item, dict) or not str(item.get("text") or "").strip():
            continue
        start = float(item.get("start") or 0)
        end = start + float(item.get("duration") or 0)
        transcript_facts.append({
            "fact_id": f"transcript-{index + 1:03d}",
            "statement": str(item["text"]).strip(),
            "time_range": [start, end],
            "evidence_refs": [f"transcript.json#/segments/{index}"],
            "confidence": 1.0,
        })
    scene_elements = report.get("scene_elements") if isinstance(report.get("scene_elements"), list) else []
    audible_facts = []
    for index, item in enumerate(scene_elements):
        if not isinstance(item, dict):
            continue
        sound = str(item.get("sound") or "").strip()
        if not sound or sound in {fact["statement"] for fact in audible_facts}:
            continue
        audible_facts.append({
            "fact_id": f"audible-{index + 1:03d}",
            "statement": sound,
            "time_range": [float(index), float(index + 1)],
            "evidence_refs": [f"report.json#/scene_elements/{index}"],
            "confidence": 0.8,
        })
    duration = video_duration(source_video)
    timing_facts = [{
        "fact_id": "timing-duration",
        "statement": f"The fixture video duration is {duration:.3f} seconds.",
        "time_range": [0.0, duration],
        "evidence_refs": [str(source_video)],
        "confidence": 1.0,
    }]
    gaps: list[str] = []
    if not visual_facts:
        gaps.append("visual_descriptions_missing")
    if not transcript_facts:
        gaps.append("transcript_missing")
    if not audible_facts:
        gaps.append("sound_analysis_missing")
    fixture_backed = evidence_origin == "fixture_video"
    return {
        "schema": "persona_dream.dream_observation_packet.v1",
        "status": "PASS_DREAM_OBSERVATION_CONTRACT_FIXTURE" if fixture_backed else "BLOCKED_DREAM_OBSERVATION_CONTRACT",
        "dream_id": dream_id,
        "revision_id": revision_id,
        "evidence_origin": evidence_origin,
        "fixture_backed": fixture_backed,
        "provider_returned": evidence_origin == "provider_return",
        "persona_watched_provider_dream": False,
        "source_video": str(source_video.resolve()),
        "source_video_sha256": sha256_file(source_video),
        "duration_seconds": duration,
        "frame_refs": frame_refs,
        "visual_facts": visual_facts,
        "transcript_facts": transcript_facts,
        "audible_facts": audible_facts,
        "timing_facts": timing_facts,
        "coverage_gaps": gaps,
        "psychological_interpretation_performed": False,
        "claims": {
            "proves": ["Persona Dream normalized concrete Watch artifacts from a local fixture video"],
            "does_not_prove": [
                "a provider returned this video",
                "the persona watched a provider-returned dream",
                "visual appearance when visual_descriptions_missing is present",
                "psychological interpretation",
            ],
        },
    }


def validate_packet(packet: dict[str, Any]) -> list[str]:
    schema = read_object(SCHEMA_PATH)
    return sorted(error.message for error in Draft202012Validator(schema).iter_errors(packet))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch-root", type=Path, required=True)
    parser.add_argument("--source-video", type=Path, required=True)
    parser.add_argument("--dream-id", required=True)
    parser.add_argument("--revision-id", required=True)
    parser.add_argument("--evidence-origin", choices=("fixture_video", "provider_return"), default="fixture_video")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    packet = build_packet(args.watch_root, args.source_video, args.dream_id, args.revision_id, args.evidence_origin)
    errors = validate_packet(packet)
    if errors:
        packet["status"] = "BLOCKED_DREAM_OBSERVATION_CONTRACT"
        packet["validation_errors"] = errors
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(packet, indent=2, sort_keys=True))
    else:
        print(packet["status"])
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
