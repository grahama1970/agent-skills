#!/usr/bin/env python3
"""Normalize Watch output into an evidence-only Persona Dream observation packet."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator
from pydantic_step_gate import pydantic_error_messages


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "dream_observation_packet.v1.schema.json"
SHA256_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
ACTIVATION_RE = re.compile(r"^activation-[a-f0-9]{32}$")
EXPECTED_PROVIDER_FRAME_COUNT = 12


class ObservationBlocked(RuntimeError):
    def __init__(self, code: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.details = dict(details or {})


def require(condition: Any, code: str, **details: Any) -> None:
    if not condition:
        raise ObservationBlocked(code, details=details)


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


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def resolved_file(path: Path, code: str) -> Path:
    try:
        resolved = path.expanduser().resolve(strict=True)
    except OSError as exc:
        raise ObservationBlocked(code, details={"path": str(path), "error": str(exc)}) from exc
    require(resolved.is_file(), code, path=str(resolved))
    return resolved


def resolved_dir(path: Path, code: str) -> Path:
    try:
        resolved = path.expanduser().resolve(strict=True)
    except OSError as exc:
        raise ObservationBlocked(code, details={"path": str(path), "error": str(exc)}) from exc
    require(resolved.is_dir(), code, path=str(resolved))
    return resolved


def require_under(root: Path, path: Path, code: str) -> Path:
    resolved_root = root.resolve(strict=True)
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ObservationBlocked(
            code,
            details={"root": str(resolved_root), "path": str(resolved)},
        ) from exc
    return resolved


def run_relative(run_root: Path, path: Path) -> str:
    return require_under(run_root, path, "BLOCKED_DREAM_OBSERVATION_PATH_ESCAPE").relative_to(
        run_root.resolve(strict=True)
    ).as_posix()


def file_ref(run_root: Path, path: Path) -> dict[str, Any]:
    resolved = resolved_file(path, "BLOCKED_DREAM_OBSERVATION_EVIDENCE_MISSING")
    return {
        "path": run_relative(run_root, resolved),
        "sha256": sha256_file(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def resolve_run_reference(run_root: Path, value: str, code: str) -> Path:
    require(bool(value), code)
    candidate = (run_root / value).resolve(strict=True)
    require_under(run_root, candidate, code)
    return candidate


def number(value: Any, code: str, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ObservationBlocked(code, details={"field": field, "value": value}) from exc


def integer(value: Any, code: str, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ObservationBlocked(code, details={"field": field, "value": value}) from exc


def fixture_packet(
    watch_root: Path,
    source_video: Path,
    dream_id: str,
    revision_id: str,
) -> dict[str, Any]:
    report = read_object(watch_root / "report.json")
    transcript = read_object(watch_root / "transcript.json")
    frames_manifest = read_object(watch_root / "frames_manifest.json")
    frames = frames_manifest.get("frames") if isinstance(frames_manifest.get("frames"), list) else []
    frame_refs = [str(item.get("path")) for item in frames if isinstance(item, dict) and item.get("path")]
    frame_evidence = []
    for index, item in enumerate(frames):
        if not isinstance(item, Mapping) or not item.get("path"):
            continue
        path = Path(str(item["path"])).expanduser().resolve()
        if path.is_file():
            frame_evidence.append(
                {
                    "index": int(item.get("index", index)),
                    "timestamp_seconds": float(item.get("timestamp_seconds") or 0),
                    "path": str(path),
                    "sha256": sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
            )
    visual_descriptions = report.get("visual_descriptions") if isinstance(report.get("visual_descriptions"), list) else []
    visual_facts = []
    for index, item in enumerate(visual_descriptions):
        if not isinstance(item, dict) or not str(item.get("description") or "").strip():
            continue
        frame_ref = str(item.get("path") or item.get("frame_path") or "")
        visual_facts.append({
            "fact_id": f"visual-{index + 1:03d}",
            "statement": str(item["description"]).strip(),
            "time_range": [float(item.get("timestamp_seconds") or item.get("timestamp") or 0)] * 2,
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
    gaps: list[str] = []
    if not visual_facts:
        gaps.append("visual_descriptions_missing")
    if not transcript_facts:
        gaps.append("transcript_missing")
    if not audible_facts:
        gaps.append("sound_analysis_missing")
    return {
        "schema": "persona_dream.dream_observation_packet.v1",
        "status": "PASS_DREAM_OBSERVATION_CONTRACT_FIXTURE",
        "dream_id": dream_id,
        "run_id": None,
        "revision_id": revision_id,
        "activation_transaction_id": None,
        "request_body_sha256": None,
        "request_id": None,
        "evidence_origin": "fixture_video",
        "fixture_backed": True,
        "provider_returned": False,
        "persona_watched_provider_dream": False,
        "actual_provider_call_attempts": 0,
        "source_video": str(source_video.resolve()),
        "source_video_sha256": sha256_file(source_video),
        "source_video_size_bytes": source_video.stat().st_size,
        "duration_seconds": duration,
        "evidence_files": None,
        "provider_lineage": None,
        "watch_evidence": None,
        "audio_strategy": {
            "generate_audio": None,
            "transcript_present": True,
            "missing_audio_is_expected": False,
        },
        "frame_refs": frame_refs,
        "frame_evidence": frame_evidence,
        "visual_facts": visual_facts,
        "transcript_facts": transcript_facts,
        "audible_facts": audible_facts,
        "timing_facts": [{
            "fact_id": "timing-duration",
            "statement": f"The fixture video duration is {duration:.3f} seconds.",
            "time_range": [0.0, duration],
            "evidence_refs": [str(source_video)],
            "confidence": 1.0,
        }],
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


def provider_packet(
    watch_root: Path,
    source_video: Path,
    dream_id: str,
    revision_id: str,
    *,
    run_root: Path,
    provider_return_envelope: Path,
    download_ffprobe_receipt: Path,
    canonical_request: Path,
    visual_description_receipt: Path | None,
) -> dict[str, Any]:
    run_root = resolved_dir(run_root, "BLOCKED_DREAM_OBSERVATION_RUN_ROOT")
    envelope_path = resolved_file(provider_return_envelope, "BLOCKED_DREAM_OBSERVATION_PROVIDER_ENVELOPE_MISSING")
    download_path = resolved_file(download_ffprobe_receipt, "BLOCKED_DREAM_OBSERVATION_DOWNLOAD_RECEIPT_MISSING")
    request_path = resolved_file(canonical_request, "BLOCKED_DREAM_OBSERVATION_CANONICAL_REQUEST_MISSING")
    source_video = resolved_file(source_video, "BLOCKED_DREAM_OBSERVATION_SOURCE_VIDEO_MISSING")
    watch_root = resolved_dir(watch_root, "BLOCKED_DREAM_OBSERVATION_WATCH_ROOT_MISSING")
    visual_receipt_path = resolved_file(
        visual_description_receipt or watch_root / "visual_description_receipt.json",
        "BLOCKED_DREAM_OBSERVATION_VISUAL_RECEIPT_MISSING",
    )
    frames_path = resolved_file(watch_root / "frames_manifest.json", "BLOCKED_DREAM_OBSERVATION_FRAMES_MANIFEST_MISSING")
    report_path = resolved_file(watch_root / "report.json", "BLOCKED_DREAM_OBSERVATION_WATCH_REPORT_MISSING")

    provider_root = envelope_path.parent
    revision_root = run_root / ".persona-dream" / "revisions" / revision_id
    require_under(run_root, provider_root, "BLOCKED_DREAM_OBSERVATION_PROVIDER_ROOT_ESCAPE")
    require_under(revision_root, provider_root, "BLOCKED_DREAM_OBSERVATION_PROVIDER_ROOT_ESCAPE")
    for path in (envelope_path, download_path, source_video, watch_root):
        require_under(provider_root, path, "BLOCKED_DREAM_OBSERVATION_PROVIDER_ROOT_ESCAPE")
    for path in (frames_path, report_path, visual_receipt_path):
        require_under(watch_root, path, "BLOCKED_DREAM_OBSERVATION_WATCH_PATH_ESCAPE")
    require_under(revision_root, request_path, "BLOCKED_DREAM_OBSERVATION_CANONICAL_REQUEST_ESCAPE")

    envelope = read_object(envelope_path)
    download = read_object(download_path)
    request = read_object(request_path)
    frames_manifest = read_object(frames_path)
    report = read_object(report_path)
    visual_receipt = read_object(visual_receipt_path)

    require(envelope.get("schema") == "persona_dream.phase11_provider_return_envelope.v1", "BLOCKED_DREAM_OBSERVATION_PROVIDER_ENVELOPE_SCHEMA")
    require(envelope.get("status") == "PASS_PHASE11_PROVIDER_RETURN_RECEIVED", "BLOCKED_DREAM_OBSERVATION_PROVIDER_RETURN_STATUS")
    require(download.get("schema") == "persona_dream.phase11_download_ffprobe_receipt.v1", "BLOCKED_DREAM_OBSERVATION_DOWNLOAD_RECEIPT_SCHEMA")
    require(download.get("status") == "PASS_PHASE11_PROVIDER_RETURN_DOWNLOADED", "BLOCKED_DREAM_OBSERVATION_DOWNLOAD_RECEIPT_STATUS")
    require(request.get("schema") == "persona_dream.phase11_live_request.v1", "BLOCKED_DREAM_OBSERVATION_CANONICAL_REQUEST_SCHEMA")

    run_id = str(envelope.get("run_id") or "")
    activation_transaction_id = str(envelope.get("activation_transaction_id") or "")
    request_body_sha256 = str(envelope.get("request_body_sha256") or "")
    request_id = str(envelope.get("request_id") or "")
    require(run_id == run_root.name, "BLOCKED_DREAM_OBSERVATION_RUN_ID", expected=run_root.name, observed=run_id)
    require(revision_id and envelope.get("revision_id") == revision_id, "BLOCKED_DREAM_OBSERVATION_REVISION_ID")
    require(ACTIVATION_RE.fullmatch(activation_transaction_id) is not None, "BLOCKED_DREAM_OBSERVATION_ACTIVATION_TRANSACTION")
    require(SHA256_RE.fullmatch(request_body_sha256) is not None, "BLOCKED_DREAM_OBSERVATION_REQUEST_HASH")
    require(bool(request_id), "BLOCKED_DREAM_OBSERVATION_REQUEST_ID")

    identity_fields = {
        "run_id": run_id,
        "revision_id": revision_id,
        "activation_transaction_id": activation_transaction_id,
        "request_body_sha256": request_body_sha256,
        "request_id": request_id,
    }
    for name, expected in identity_fields.items():
        if name in download:
            require(download.get(name) == expected, f"BLOCKED_DREAM_OBSERVATION_{name.upper()}", expected=expected, observed=download.get(name))
    for name in ("run_id", "revision_id", "activation_transaction_id", "request_body_sha256"):
        require(request.get(name) == identity_fields[name], f"BLOCKED_DREAM_OBSERVATION_{name.upper()}", expected=identity_fields[name], observed=request.get(name))

    attempts = integer(envelope.get("actual_provider_call_attempts"), "BLOCKED_DREAM_OBSERVATION_PROVIDER_ATTEMPTS", "envelope")
    require(attempts == 1, "BLOCKED_DREAM_OBSERVATION_PROVIDER_ATTEMPTS", observed=attempts)
    require(integer(download.get("actual_provider_call_attempts"), "BLOCKED_DREAM_OBSERVATION_PROVIDER_ATTEMPTS", "download") == attempts, "BLOCKED_DREAM_OBSERVATION_PROVIDER_ATTEMPTS")
    require(envelope.get("provider_live") is True and envelope.get("submitted") is True, "BLOCKED_DREAM_OBSERVATION_PROVIDER_RETURN_FLAGS")
    require(envelope.get("endpoint") == download.get("endpoint") == request.get("endpoint"), "BLOCKED_DREAM_OBSERVATION_PROVIDER_ENDPOINT")

    local_video_sha = sha256_file(source_video)
    local_video_size = source_video.stat().st_size
    require(
        local_video_sha == envelope.get("downloaded_mp4_sha256") == download.get("downloaded_sha256"),
        "BLOCKED_DREAM_OBSERVATION_MP4_HASH",
        local=local_video_sha,
        envelope=envelope.get("downloaded_mp4_sha256"),
        download=download.get("downloaded_sha256"),
    )
    require(local_video_size == integer(download.get("size_bytes"), "BLOCKED_DREAM_OBSERVATION_MP4_SIZE", "size_bytes"), "BLOCKED_DREAM_OBSERVATION_MP4_SIZE")
    ffprobe = download.get("ffprobe")
    ffprobe_format = ffprobe.get("format") if isinstance(ffprobe, Mapping) else None
    require(isinstance(ffprobe_format, Mapping), "BLOCKED_DREAM_OBSERVATION_FFPROBE")
    require(local_video_size == integer(ffprobe_format.get("size"), "BLOCKED_DREAM_OBSERVATION_FFPROBE", "format.size"), "BLOCKED_DREAM_OBSERVATION_FFPROBE")
    receipt_duration = number(ffprobe_format.get("duration"), "BLOCKED_DREAM_OBSERVATION_FFPROBE", "format.duration")
    observed_duration = video_duration(source_video)
    require(abs(receipt_duration - observed_duration) <= 0.05, "BLOCKED_DREAM_OBSERVATION_DURATION", receipt=receipt_duration, observed=observed_duration)

    expected_download = resolve_run_reference(run_root, str(envelope.get("download_receipt_relative_path") or ""), "BLOCKED_DREAM_OBSERVATION_DOWNLOAD_RECEIPT_PATH")
    expected_video = resolve_run_reference(run_root, str(download.get("download_relative_path") or ""), "BLOCKED_DREAM_OBSERVATION_SOURCE_VIDEO_PATH")
    require(expected_download == download_path, "BLOCKED_DREAM_OBSERVATION_DOWNLOAD_RECEIPT_PATH")
    require(expected_video == source_video, "BLOCKED_DREAM_OBSERVATION_SOURCE_VIDEO_PATH")
    require(envelope.get("download_receipt_sha256") == sha256_file(download_path), "BLOCKED_DREAM_OBSERVATION_DOWNLOAD_RECEIPT_HASH")
    require(envelope.get("video_url") == download.get("source_url"), "BLOCKED_DREAM_OBSERVATION_PROVIDER_VIDEO_URL")

    request_body = request.get("provider_request_body")
    require(isinstance(request_body, Mapping), "BLOCKED_DREAM_OBSERVATION_CANONICAL_REQUEST_BODY")
    generate_audio = request_body.get("generate_audio")
    transcript_path = watch_root / "transcript.json"
    transcript_present = transcript_path.is_file()
    if not transcript_present:
        require(generate_audio is False, "BLOCKED_DREAM_OBSERVATION_TRANSCRIPT_REQUIRED_FOR_AUDIO_REQUEST")
    require(generate_audio is False, "BLOCKED_DREAM_OBSERVATION_PROVIDER_AUDIO_STRATEGY", observed=generate_audio)

    manifest_source = Path(str(frames_manifest.get("source") or "")).expanduser().resolve(strict=True)
    watch_report = report.get("watch_report")
    require(isinstance(watch_report, Mapping), "BLOCKED_DREAM_OBSERVATION_WATCH_REPORT_SCHEMA")
    report_source = Path(str(watch_report.get("source") or "")).expanduser().resolve(strict=True)
    require(manifest_source == source_video and report_source == source_video, "BLOCKED_DREAM_OBSERVATION_WATCH_SOURCE")
    require(watch_report.get("sampling_mode") == frames_manifest.get("sampling_mode") == "uniform-fallback", "BLOCKED_DREAM_OBSERVATION_WATCH_SAMPLING")

    frames = frames_manifest.get("frames")
    require(isinstance(frames, list) and len(frames) == EXPECTED_PROVIDER_FRAME_COUNT, "BLOCKED_DREAM_OBSERVATION_FRAME_COUNT")
    require(integer(frames_manifest.get("frame_count"), "BLOCKED_DREAM_OBSERVATION_FRAME_COUNT", "manifest.frame_count") == EXPECTED_PROVIDER_FRAME_COUNT, "BLOCKED_DREAM_OBSERVATION_FRAME_COUNT")
    require(integer(watch_report.get("frame_count"), "BLOCKED_DREAM_OBSERVATION_FRAME_COUNT", "report.frame_count") == EXPECTED_PROVIDER_FRAME_COUNT, "BLOCKED_DREAM_OBSERVATION_FRAME_COUNT")

    descriptions = report.get("visual_descriptions")
    report_frames = report.get("frames")
    scene_elements = report.get("scene_elements")
    require(isinstance(descriptions, list) and len(descriptions) == EXPECTED_PROVIDER_FRAME_COUNT, "BLOCKED_DREAM_OBSERVATION_VISUAL_DESCRIPTIONS")
    require(isinstance(report_frames, list) and len(report_frames) == EXPECTED_PROVIDER_FRAME_COUNT, "BLOCKED_DREAM_OBSERVATION_WATCH_REPORT_FRAMES")
    require(isinstance(scene_elements, list) and len(scene_elements) == EXPECTED_PROVIDER_FRAME_COUNT, "BLOCKED_DREAM_OBSERVATION_SCENE_ELEMENTS")
    require(visual_receipt.get("schema") == "watch.visual_description_receipt.v1", "BLOCKED_DREAM_OBSERVATION_VISUAL_RECEIPT_SCHEMA")
    require(visual_receipt.get("status") == "described" and visual_receipt.get("live") is True and visual_receipt.get("mocked") is False, "BLOCKED_DREAM_OBSERVATION_VISUAL_RECEIPT_STATUS")
    require(integer(visual_receipt.get("frame_count"), "BLOCKED_DREAM_OBSERVATION_FRAME_COUNT", "receipt.frame_count") == EXPECTED_PROVIDER_FRAME_COUNT, "BLOCKED_DREAM_OBSERVATION_FRAME_COUNT")
    require(integer(visual_receipt.get("described_count"), "BLOCKED_DREAM_OBSERVATION_DESCRIBED_COUNT", "receipt.described_count") == EXPECTED_PROVIDER_FRAME_COUNT, "BLOCKED_DREAM_OBSERVATION_DESCRIBED_COUNT")
    gate = visual_receipt.get("gate")
    require(isinstance(gate, Mapping) and gate.get("status") == "passed", "BLOCKED_DREAM_OBSERVATION_VISUAL_GATE")
    require(canonical_json(report.get("visual_description_receipt")) == canonical_json(visual_receipt), "BLOCKED_DREAM_OBSERVATION_VISUAL_RECEIPT_EMBEDDED_MISMATCH")
    receipt_frames = visual_receipt.get("frames")
    require(isinstance(receipt_frames, list) and len(receipt_frames) == EXPECTED_PROVIDER_FRAME_COUNT, "BLOCKED_DREAM_OBSERVATION_VISUAL_RECEIPT_FRAMES")

    requested_model = str(visual_receipt.get("requested_model") or "")
    require(bool(requested_model), "BLOCKED_DREAM_OBSERVATION_VISUAL_MODEL")
    frame_refs: list[str] = []
    frame_evidence: list[dict[str, Any]] = []
    visual_facts: list[dict[str, Any]] = []
    served_models: set[str] = set()
    seen_paths: set[Path] = set()
    for index in range(EXPECTED_PROVIDER_FRAME_COUNT):
        frame = frames[index]
        description = descriptions[index]
        report_frame = report_frames[index]
        receipt_frame = receipt_frames[index]
        require(all(isinstance(item, Mapping) for item in (frame, description, report_frame, receipt_frame)), "BLOCKED_DREAM_OBSERVATION_FRAME_SCHEMA", index=index)
        require(all(integer(item.get("index"), "BLOCKED_DREAM_OBSERVATION_FRAME_INDEX", f"index.{index}") == index for item in (frame, description, report_frame, receipt_frame)), "BLOCKED_DREAM_OBSERVATION_FRAME_INDEX", index=index)
        frame_path = resolved_file(Path(str(frame.get("path") or "")), "BLOCKED_DREAM_OBSERVATION_FRAME_MISSING")
        require_under(watch_root, frame_path, "BLOCKED_DREAM_OBSERVATION_FRAME_PATH_ESCAPE")
        require(frame_path.stat().st_size > 0, "BLOCKED_DREAM_OBSERVATION_FRAME_EMPTY", index=index)
        require(frame_path not in seen_paths, "BLOCKED_DREAM_OBSERVATION_FRAME_DUPLICATE", index=index)
        seen_paths.add(frame_path)
        for observed in (description.get("path"), report_frame.get("path"), receipt_frame.get("path")):
            require(Path(str(observed or "")).name == frame_path.name, "BLOCKED_DREAM_OBSERVATION_FRAME_PATH_BINDING", index=index)
        timestamp = number(frame.get("timestamp_seconds"), "BLOCKED_DREAM_OBSERVATION_FRAME_TIMESTAMP", f"frame.{index}")
        for item, field in ((description, "timestamp"), (report_frame, "timestamp_seconds"), (receipt_frame, "timestamp")):
            require(abs(number(item.get(field), "BLOCKED_DREAM_OBSERVATION_FRAME_TIMESTAMP", f"{field}.{index}") - timestamp) <= 0.01, "BLOCKED_DREAM_OBSERVATION_FRAME_TIMESTAMP", index=index)
        statement = str(description.get("description") or "").strip()
        require(statement and description.get("status") == "described", "BLOCKED_DREAM_OBSERVATION_VISUAL_DESCRIPTION", index=index)
        require(description.get("requested_model") == requested_model, "BLOCKED_DREAM_OBSERVATION_VISUAL_MODEL", index=index)
        served_model = str(description.get("served_model") or "").strip()
        require(bool(served_model), "BLOCKED_DREAM_OBSERVATION_VISUAL_MODEL", index=index)
        served_models.add(served_model)
        require(receipt_frame.get("status") == "described", "BLOCKED_DREAM_OBSERVATION_VISUAL_DESCRIPTION", index=index)
        attempts_list = receipt_frame.get("attempts")
        require(isinstance(attempts_list, list) and any(
            isinstance(attempt, Mapping)
            and attempt.get("status") == "described"
            and integer(attempt.get("http_status"), "BLOCKED_DREAM_OBSERVATION_VISUAL_ATTEMPT", f"http_status.{index}") == 200
            and attempt.get("requested_model") == requested_model
            and str(attempt.get("served_model") or "").strip() == served_model
            for attempt in attempts_list
        ), "BLOCKED_DREAM_OBSERVATION_VISUAL_ATTEMPT", index=index)
        relative = run_relative(run_root, frame_path)
        frame_refs.append(relative)
        frame_evidence.append({
            "index": index,
            "timestamp_seconds": timestamp,
            "path": relative,
            "sha256": sha256_file(frame_path),
            "size_bytes": frame_path.stat().st_size,
        })
        visual_facts.append({
            "fact_id": f"visual-{index + 1:03d}",
            "statement": statement,
            "time_range": [timestamp, timestamp],
            "evidence_refs": [relative],
            "confidence": 1.0,
        })
        scene = scene_elements[index]
        require(isinstance(scene, Mapping) and integer(scene.get("index"), "BLOCKED_DREAM_OBSERVATION_SCENE_ELEMENTS", f"scene.{index}") == index, "BLOCKED_DREAM_OBSERVATION_SCENE_ELEMENTS", index=index)
        require(str(scene.get("visual_description") or "").strip() == statement, "BLOCKED_DREAM_OBSERVATION_SCENE_ELEMENTS", index=index)

    metadata = watch_report.get("metadata")
    require(isinstance(metadata, Mapping), "BLOCKED_DREAM_OBSERVATION_WATCH_METADATA")
    codec = str(metadata.get("codec") or "").strip()
    width = integer(metadata.get("width"), "BLOCKED_DREAM_OBSERVATION_WATCH_METADATA", "width")
    height = integer(metadata.get("height"), "BLOCKED_DREAM_OBSERVATION_WATCH_METADATA", "height")
    require(codec and width > 0 and height > 0, "BLOCKED_DREAM_OBSERVATION_WATCH_METADATA")
    require(abs(number(watch_report.get("duration_seconds"), "BLOCKED_DREAM_OBSERVATION_DURATION", "watch_report.duration") - observed_duration) <= 0.05, "BLOCKED_DREAM_OBSERVATION_DURATION")
    require(abs(number(frames_manifest.get("duration_seconds"), "BLOCKED_DREAM_OBSERVATION_DURATION", "frames_manifest.duration") - observed_duration) <= 0.05, "BLOCKED_DREAM_OBSERVATION_DURATION")

    source_video_ref = run_relative(run_root, source_video)
    evidence_files = {
        "provider_return_envelope": file_ref(run_root, envelope_path),
        "download_ffprobe_receipt": file_ref(run_root, download_path),
        "canonical_request": file_ref(run_root, request_path),
        "frames_manifest": file_ref(run_root, frames_path),
        "watch_report": file_ref(run_root, report_path),
        "visual_description_receipt": file_ref(run_root, visual_receipt_path),
    }
    return {
        "schema": "persona_dream.dream_observation_packet.v1",
        "status": "PASS_DREAM_OBSERVATION_CONTRACT_PROVIDER_RETURN",
        "dream_id": dream_id,
        "run_id": run_id,
        "revision_id": revision_id,
        "activation_transaction_id": activation_transaction_id,
        "request_body_sha256": request_body_sha256,
        "request_id": request_id,
        "evidence_origin": "provider_return",
        "fixture_backed": False,
        "provider_returned": True,
        "persona_watched_provider_dream": True,
        "actual_provider_call_attempts": attempts,
        "source_video": source_video_ref,
        "source_video_sha256": local_video_sha,
        "source_video_size_bytes": local_video_size,
        "duration_seconds": observed_duration,
        "evidence_files": evidence_files,
        "provider_lineage": {
            "endpoint": str(envelope.get("endpoint")),
            "provider_result_sha256": str(envelope.get("provider_result_sha256")),
            "downloaded_mp4_sha256": local_video_sha,
            "download_receipt_sha256": sha256_file(download_path),
            "provider_return_envelope_sha256": sha256_file(envelope_path),
        },
        "watch_evidence": {
            "root": run_relative(run_root, watch_root),
            "sampling_mode": str(watch_report.get("sampling_mode")),
            "frame_count": EXPECTED_PROVIDER_FRAME_COUNT,
            "described_count": EXPECTED_PROVIDER_FRAME_COUNT,
            "scene_element_count": len(scene_elements),
            "requested_model": requested_model,
            "served_models": sorted(served_models),
            "gate_status": "passed",
            "codec": codec,
            "width": width,
            "height": height,
        },
        "audio_strategy": {
            "generate_audio": False,
            "transcript_present": transcript_present,
            "missing_audio_is_expected": not transcript_present,
        },
        "frame_refs": frame_refs,
        "frame_evidence": frame_evidence,
        "visual_facts": visual_facts,
        "transcript_facts": [],
        "audible_facts": [],
        "timing_facts": [{
            "fact_id": "timing-duration",
            "statement": f"The provider-return video duration is {observed_duration:.6f} seconds.",
            "time_range": [0.0, observed_duration],
            "evidence_refs": [source_video_ref],
            "confidence": 1.0,
        }],
        "coverage_gaps": [
            "transcript_absent_expected_generate_audio_false",
            "audio_stream_absent_expected_generate_audio_false",
        ] if not transcript_present else [],
        "psychological_interpretation_performed": False,
        "claims": {
            "proves": [
                "the Phase 11 provider-return envelope, download receipt, and local MP4 agree on one exact request and MP4 hash",
                "Watch analyzed the exact provider-return MP4 and passed its live visual-description gate for twelve frames",
                "the packet contains evidence-only visual observations bound to rehashed frame files",
            ],
            "does_not_prove": [
                "what the dream means psychologically",
                "audible content or a transcript",
                "synthetic-dream Memory persistence",
                "later persona behavior or identity preservation",
            ],
        },
    }


def build_packet(
    watch_root: Path,
    source_video: Path,
    dream_id: str,
    revision_id: str,
    evidence_origin: str,
    *,
    run_root: Path | None = None,
    provider_return_envelope: Path | None = None,
    download_ffprobe_receipt: Path | None = None,
    canonical_request: Path | None = None,
    visual_description_receipt: Path | None = None,
) -> dict[str, Any]:
    if evidence_origin == "fixture_video":
        return fixture_packet(watch_root, source_video, dream_id, revision_id)
    require(run_root is not None, "BLOCKED_DREAM_OBSERVATION_RUN_ROOT_REQUIRED")
    require(provider_return_envelope is not None, "BLOCKED_DREAM_OBSERVATION_PROVIDER_ENVELOPE_REQUIRED")
    require(download_ffprobe_receipt is not None, "BLOCKED_DREAM_OBSERVATION_DOWNLOAD_RECEIPT_REQUIRED")
    require(canonical_request is not None, "BLOCKED_DREAM_OBSERVATION_CANONICAL_REQUEST_REQUIRED")
    return provider_packet(
        watch_root,
        source_video,
        dream_id,
        revision_id,
        run_root=run_root,
        provider_return_envelope=provider_return_envelope,
        download_ffprobe_receipt=download_ffprobe_receipt,
        canonical_request=canonical_request,
        visual_description_receipt=visual_description_receipt,
    )


def validate_packet(packet: dict[str, Any]) -> list[str]:
    schema = read_object(SCHEMA_PATH)
    return pydantic_error_messages(schema, packet) + sorted(
        error.message for error in Draft202012Validator(schema).iter_errors(packet)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch-root", type=Path, required=True)
    parser.add_argument("--source-video", type=Path, required=True)
    parser.add_argument("--dream-id", required=True)
    parser.add_argument("--revision-id", required=True)
    parser.add_argument("--evidence-origin", choices=("fixture_video", "provider_return"), default="fixture_video")
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--provider-return-envelope", type=Path)
    parser.add_argument("--download-ffprobe-receipt", type=Path)
    parser.add_argument("--canonical-request", type=Path)
    parser.add_argument("--visual-description-receipt", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        packet = build_packet(
            args.watch_root,
            args.source_video,
            args.dream_id,
            args.revision_id,
            args.evidence_origin,
            run_root=args.run_root,
            provider_return_envelope=args.provider_return_envelope,
            download_ffprobe_receipt=args.download_ffprobe_receipt,
            canonical_request=args.canonical_request,
            visual_description_receipt=args.visual_description_receipt,
        )
        errors = validate_packet(packet)
        if errors:
            raise ObservationBlocked("BLOCKED_DREAM_OBSERVATION_PACKET_SCHEMA", details={"errors": errors})
        exit_code = 0
    except (ObservationBlocked, OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        code = exc.code if isinstance(exc, ObservationBlocked) else "BLOCKED_DREAM_OBSERVATION_CONTRACT"
        details = exc.details if isinstance(exc, ObservationBlocked) else {"error": str(exc)}
        packet = {
            "schema": "persona_dream.dream_observation_packet_error.v1",
            "status": "BLOCKED_DREAM_OBSERVATION_CONTRACT",
            "blocker": code,
            "details": details,
            "evidence_origin": args.evidence_origin,
            "fixture_backed": args.evidence_origin == "fixture_video",
            "provider_returned": False,
            "persona_watched_provider_dream": False,
            "psychological_interpretation_performed": False,
            "actual_provider_call_attempts": 0,
        }
        exit_code = 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(packet, indent=2, sort_keys=True) if args.json else packet["status"])
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
