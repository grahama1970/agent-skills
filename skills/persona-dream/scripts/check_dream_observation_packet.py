#!/usr/bin/env python3
"""Validate one Persona Dream observation packet and independently rehash its evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from write_dream_observation_packet import (
    EXPECTED_PROVIDER_FRAME_COUNT,
    read_object,
    sha256_file,
    validate_packet,
)


def _resolve_under(root: Path, relative: str, label: str, errors: list[str]) -> Path | None:
    try:
        resolved_root = root.resolve(strict=True)
        candidate = (resolved_root / relative).resolve(strict=True)
        candidate.relative_to(resolved_root)
    except (OSError, ValueError):
        errors.append(f"{label}: path missing or escapes run root")
        return None
    return candidate


def _check_ref(run_root: Path, ref: Any, label: str, errors: list[str]) -> Path | None:
    if not isinstance(ref, Mapping):
        errors.append(f"{label}: reference missing")
        return None
    relative = str(ref.get("path") or "")
    path = _resolve_under(run_root, relative, label, errors)
    if path is None or not path.is_file():
        errors.append(f"{label}: file missing")
        return None
    if sha256_file(path) != ref.get("sha256"):
        errors.append(f"{label}: sha256 mismatch")
    if path.stat().st_size != ref.get("size_bytes"):
        errors.append(f"{label}: size mismatch")
    return path


def provider_evidence_errors(packet: Mapping[str, Any], run_root: Path) -> list[str]:
    errors: list[str] = []
    evidence_files = packet.get("evidence_files")
    if not isinstance(evidence_files, Mapping):
        return ["provider packet evidence_files missing"]
    paths = {
        name: _check_ref(run_root, evidence_files.get(name), name, errors)
        for name in (
            "provider_return_envelope",
            "download_ffprobe_receipt",
            "canonical_request",
            "frames_manifest",
            "watch_report",
            "visual_description_receipt",
        )
    }
    source_path = _resolve_under(run_root, str(packet.get("source_video") or ""), "source_video", errors)
    if source_path is None or not source_path.is_file():
        errors.append("source_video: file missing")
    else:
        if sha256_file(source_path) != packet.get("source_video_sha256"):
            errors.append("source_video: sha256 mismatch")
        if source_path.stat().st_size != packet.get("source_video_size_bytes"):
            errors.append("source_video: size mismatch")

    if any(path is None for path in paths.values()) or source_path is None:
        return sorted(set(errors))
    envelope = read_object(paths["provider_return_envelope"])
    download = read_object(paths["download_ffprobe_receipt"])
    request = read_object(paths["canonical_request"])
    frames_manifest = read_object(paths["frames_manifest"])
    report = read_object(paths["watch_report"])
    visual_receipt = read_object(paths["visual_description_receipt"])

    expected_identity = {
        "run_id": packet.get("run_id"),
        "revision_id": packet.get("revision_id"),
        "activation_transaction_id": packet.get("activation_transaction_id"),
        "request_body_sha256": packet.get("request_body_sha256"),
        "request_id": packet.get("request_id"),
    }
    for source_name, source in (("envelope", envelope), ("download", download)):
        for field, expected in expected_identity.items():
            if field in source and source.get(field) != expected:
                errors.append(f"{source_name}: {field} mismatch")
    for field in ("run_id", "revision_id", "activation_transaction_id", "request_body_sha256"):
        if request.get(field) != expected_identity[field]:
            errors.append(f"canonical_request: {field} mismatch")
    if envelope.get("status") != "PASS_PHASE11_PROVIDER_RETURN_RECEIVED":
        errors.append("provider_return_envelope: status mismatch")
    if download.get("status") != "PASS_PHASE11_PROVIDER_RETURN_DOWNLOADED":
        errors.append("download_ffprobe_receipt: status mismatch")
    if envelope.get("downloaded_mp4_sha256") != packet.get("source_video_sha256"):
        errors.append("provider_return_envelope: MP4 hash mismatch")
    if download.get("downloaded_sha256") != packet.get("source_video_sha256"):
        errors.append("download_ffprobe_receipt: MP4 hash mismatch")
    if envelope.get("download_receipt_sha256") != sha256_file(paths["download_ffprobe_receipt"]):
        errors.append("provider_return_envelope: download receipt hash mismatch")
    if envelope.get("actual_provider_call_attempts") != packet.get("actual_provider_call_attempts"):
        errors.append("provider_return_envelope: attempt count mismatch")
    if download.get("actual_provider_call_attempts") != packet.get("actual_provider_call_attempts"):
        errors.append("download_ffprobe_receipt: attempt count mismatch")
    request_body = request.get("provider_request_body")
    if not isinstance(request_body, Mapping) or request_body.get("generate_audio") is not False:
        errors.append("canonical_request: generate_audio must be false for silent coverage gap")

    watch_evidence = packet.get("watch_evidence")
    if not isinstance(watch_evidence, Mapping):
        errors.append("watch_evidence missing")
        return sorted(set(errors))
    watch_root = _resolve_under(run_root, str(watch_evidence.get("root") or ""), "watch_root", errors)
    if watch_root is None or not watch_root.is_dir():
        errors.append("watch_root missing")
        return sorted(set(errors))
    for name in ("frames_manifest", "watch_report", "visual_description_receipt"):
        path = paths[name]
        try:
            path.relative_to(watch_root)
        except ValueError:
            errors.append(f"{name}: path escapes watch root")

    frames = frames_manifest.get("frames")
    descriptions = report.get("visual_descriptions")
    receipt_frames = visual_receipt.get("frames")
    if not isinstance(frames, list) or len(frames) != EXPECTED_PROVIDER_FRAME_COUNT:
        errors.append("frames_manifest: frame count mismatch")
        frames = []
    if not isinstance(descriptions, list) or len(descriptions) != EXPECTED_PROVIDER_FRAME_COUNT:
        errors.append("watch_report: visual description count mismatch")
        descriptions = []
    if not isinstance(receipt_frames, list) or len(receipt_frames) != EXPECTED_PROVIDER_FRAME_COUNT:
        errors.append("visual_description_receipt: frame count mismatch")
    if visual_receipt.get("described_count") != EXPECTED_PROVIDER_FRAME_COUNT:
        errors.append("visual_description_receipt: described_count mismatch")
    gate = visual_receipt.get("gate")
    if not isinstance(gate, Mapping) or gate.get("status") != "passed":
        errors.append("visual_description_receipt: gate did not pass")

    packet_frames = packet.get("frame_evidence")
    if not isinstance(packet_frames, list) or len(packet_frames) != EXPECTED_PROVIDER_FRAME_COUNT:
        errors.append("packet: frame_evidence count mismatch")
        packet_frames = []
    for index, frame_ref in enumerate(packet_frames):
        if not isinstance(frame_ref, Mapping):
            errors.append(f"frame_evidence[{index}]: invalid")
            continue
        frame_path = _check_ref(run_root, frame_ref, f"frame_evidence[{index}]", errors)
        if frame_path is None:
            continue
        try:
            frame_path.relative_to(watch_root)
        except ValueError:
            errors.append(f"frame_evidence[{index}]: path escapes watch root")
        if frame_ref.get("index") != index:
            errors.append(f"frame_evidence[{index}]: index mismatch")
        if index < len(frames) and Path(str(frames[index].get("path") or "")).name != frame_path.name:
            errors.append(f"frame_evidence[{index}]: manifest path mismatch")
        if index < len(descriptions) and not str(descriptions[index].get("description") or "").strip():
            errors.append(f"frame_evidence[{index}]: description missing")

    return sorted(set(errors))


def check_packet(packet: Mapping[str, Any], run_root: Path | None) -> list[str]:
    errors = validate_packet(dict(packet))
    if packet.get("fixture_backed") is True:
        for key in ("provider_returned", "persona_watched_provider_dream", "psychological_interpretation_performed"):
            if packet.get(key) is not False:
                errors.append(f"fixture packet requires {key}=false")
        if packet.get("actual_provider_call_attempts") != 0:
            errors.append("fixture packet requires actual_provider_call_attempts=0")
    elif packet.get("evidence_origin") == "provider_return":
        if run_root is None:
            errors.append("provider packet requires --run-root")
        else:
            errors.extend(provider_evidence_errors(packet, run_root))
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    packet = read_object(args.packet)
    errors = check_packet(packet, args.run_root)
    is_provider = packet.get("evidence_origin") == "provider_return"
    receipt = {
        "schema": "persona_dream.dream_observation_packet_check_receipt.v1",
        "status": packet.get("status") if not errors else "BLOCKED_DREAM_OBSERVATION_CONTRACT",
        "packet": str(args.packet.resolve()),
        "packet_sha256": sha256_file(args.packet),
        "errors": errors,
        "mocked": bool(packet.get("fixture_backed")),
        "live": bool(is_provider and not packet.get("fixture_backed")),
        "provider_live": bool(packet.get("provider_returned")),
        "provider_returned": bool(packet.get("provider_returned")),
        "persona_watched_provider_dream": bool(packet.get("persona_watched_provider_dream")),
        "frame_count": len(packet.get("frame_evidence") or []),
        "described_count": len(packet.get("visual_facts") or []),
        "actual_provider_call_attempts": int(packet.get("actual_provider_call_attempts") or 0),
    }
    print(json.dumps(receipt, indent=2, sort_keys=True) if args.json else receipt["status"])
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
