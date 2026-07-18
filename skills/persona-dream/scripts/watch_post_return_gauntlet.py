#!/usr/bin/env python3
"""Wire the /watch skill into the Persona Dream post-return gauntlet.

Given a returned MP4 and the revision's panel/identity context, this harness:

1. Runs the /watch skill (scene-change frames, Whisper transcript on the muxed
   video, scene table) via its ``run.sh`` entry point.
2. Normalizes Watch output into a phase-12-compatible observation packet
   (``dream_observation_packet.v1.json`` with schema
   ``persona_dream.watch_gauntlet_observation_packet.v1``) under
   ``watch_gauntlet/<video_sha_prefix>/``: observed entities per frame, frame
   timestamps, coverage gaps, and hooks for immutable-goal steps 35/36/38.
3. (Optional) Runs the codex-oauth vision layer over the identity-window frames
   to independently corroborate Embry identity drift against
   ``embry_contact_sheet_v3``.
4. Validates the perception against ground-truth expectations drawn from the
   frozen historical return and emits ``watch_gauntlet_validation_receipt.v1.json``.
5. Persists a Memory record for the gauntlet + validation with an exact reread.

Live capabilities that are unavailable (e.g. per-frame VLM entities, codex
vision) degrade explicitly: the blocker is recorded per capability and the
remaining validation still runs. No output is faked.

The pure functions (``build_observation_packet``, ``validate_observation_packet``,
``evaluate_validation``) contain no live calls and are exercised by
``tests/test_watch_post_return_gauntlet.py``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import httpx
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "watch_gauntlet_observation_packet.v1.schema.json"
PACKET_SCHEMA = "persona_dream.watch_gauntlet_observation_packet.v1"
VALIDATION_SCHEMA = "persona_dream.watch_gauntlet_validation_receipt.v1"
MEMORY_COLLECTION = "persona_dream_watch_gauntlet"
WATCH_SKILL_DIR_DEFAULT = ROOT.parents[0] / "watch"
MEMORY_SERVER_FIELDS = {
    "_id", "_rev", "qdrant_collection", "qdrant_point_id", "embedding_model",
    "embedding_version", "text_hash", "semantic_sync_state",
}


# --------------------------------------------------------------------------- #
# Deterministic helpers
# --------------------------------------------------------------------------- #
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def file_ref(root: Path, path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    return {
        "path": resolved.relative_to(root.resolve()).as_posix(),
        "sha256": sha256_file(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def _in_window(ts: float, window: Sequence[float]) -> bool:
    return window[0] <= ts <= window[1]


# --------------------------------------------------------------------------- #
# Live: run the /watch skill
# --------------------------------------------------------------------------- #
def run_watch_live(
    video: Path,
    watch_out_dir: Path,
    *,
    watch_skill_dir: Path,
    scene_change: bool = True,
    max_frames: int = 100,
    resolution: int = 512,
    whisper: bool = True,
) -> dict[str, Any]:
    """Invoke watch/run.sh and return parsed frames/transcript/scenes/report."""
    watch_out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(watch_skill_dir / "run.sh"), str(video.resolve()),
        "--out-dir", str(watch_out_dir),
        "--max-frames", str(max_frames),
        "--resolution", str(resolution),
        "--json",
    ]
    cmd.append("--scene-change" if scene_change else "--no-scene-change")
    cmd.append("--whisper" if whisper else "--no-whisper")
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("VIRTUAL_") and k != "PYTHONPATH"}
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=1800)
    manifest_path = watch_out_dir / "frames_manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(
            f"watch produced no frames_manifest (rc={proc.returncode}):\n"
            f"{proc.stderr[-2000:]}"
        )
    transcript_path = watch_out_dir / "transcript.json"
    scenes_path = watch_out_dir / "scenes.json"
    report_path = watch_out_dir / "report.json"
    if not scenes_path.is_file():
        write_json(scenes_path, {"matches": []})
    if not transcript_path.is_file():
        write_json(transcript_path, {"source": None, "segments": [], "full_text": ""})
    return {
        "returncode": proc.returncode,
        "frames_manifest": read_json(manifest_path),
        "frames_manifest_path": manifest_path,
        "transcript": read_json(transcript_path),
        "transcript_path": transcript_path,
        "scenes": read_json(scenes_path),
        "scenes_path": scenes_path,
        "report": read_json(report_path) if report_path.is_file() else {},
        "report_path": report_path if report_path.is_file() else None,
    }


# --------------------------------------------------------------------------- #
# Live: codex-oauth vision identity review
# --------------------------------------------------------------------------- #
def _parse_vision_verdict(text: str) -> str:
    upper = text.upper()
    for line in upper.splitlines():
        if "VERDICT" in line:
            if "DRIFT" in line:
                return "DRIFT"
            if "CONSISTENT" in line:
                return "CONSISTENT"
    if "DRIFT" in upper:
        return "DRIFT"
    if "CONSISTENT" in upper:
        return "CONSISTENT"
    return "INDETERMINATE"


def run_vision_identity_review_live(
    reference: Path,
    frames: Sequence[Path],
    *,
    codex_skill_dir: Path,
    model: str = "gpt-5.3-codex",
    timeout: int = 420,
) -> dict[str, Any]:
    """Independently review identity-window frames for Embry drift via codex."""
    prompt = (
        "Image 1 is a qualified character reference sheet for a character named "
        "Embry. The remaining images are frames sampled from the first ~3 seconds "
        "of a generated video that is supposed to depict Embry, in ascending "
        "timestamp order. Judge whether Embry's facial identity stays consistent "
        "across those frames AND matches the reference sheet. Output exactly two "
        "lines. Line 1: 'VERDICT: DRIFT' or 'VERDICT: CONSISTENT'. Line 2: one "
        "sentence of visual justification."
    )
    cmd = [str(codex_skill_dir / "run.sh"), "reason", "--model", model,
           "--reasoning", "high", "--timeout", str(timeout)]
    # codex reason takes the prompt positionally; images go through the codex CLI.
    # Use codex exec directly with -i for image attachment (variadic -> prompt via stdin).
    exec_cmd = ["codex", "exec", "-i", str(reference.resolve())]
    for frame in frames:
        exec_cmd += ["-i", str(frame.resolve())]
    try:
        proc = subprocess.run(
            exec_cmd, input=prompt, capture_output=True, text=True,
            timeout=timeout, cwd=str(codex_skill_dir),
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return {"status": "not_performed", "reason": f"codex vision unavailable: {exc}",
                "verdict": "INDETERMINATE", "model": model}
    output = proc.stdout or ""
    verdict = _parse_vision_verdict(output)
    return {
        "status": "performed" if verdict in {"DRIFT", "CONSISTENT"} else "indeterminate",
        "verdict": verdict,
        "model": model,
        "auth": "codex-oauth",
        "returncode": proc.returncode,
        "raw_output_tail": output.strip()[-1200:],
        "reviewed_frame_count": len(frames),
    }


# --------------------------------------------------------------------------- #
# Pure: build the observation packet
# --------------------------------------------------------------------------- #
def _frame_observed_entities(report: Mapping[str, Any], index: int) -> tuple[list[str], str | None]:
    """Return (entities, gap) from watch visual descriptions, if any."""
    descriptions = report.get("visual_descriptions")
    if isinstance(descriptions, list) and index < len(descriptions):
        entry = descriptions[index]
        if isinstance(entry, Mapping):
            desc = str(entry.get("description") or "").strip()
            status = str(entry.get("status") or "")
            if desc and status not in {"not_described", "not_analyzed"}:
                return [desc], None
    return [], "per_frame_vlm_entities_unavailable"


def build_observation_packet(
    *,
    packet_root: Path,
    frames_manifest: Mapping[str, Any],
    transcript: Mapping[str, Any],
    report: Mapping[str, Any],
    frame_files: Mapping[int, Path],
    watch_artifacts: Mapping[str, dict[str, Any]],
    source_video_basename: str,
    source_video_sha256: str,
    source_video_size_bytes: int,
    duration_seconds: float,
    run_id: str,
    revision_id: str,
    source_revision_id: str,
    evidence_origin: str,
    requested_mode: str,
    identity_window: Sequence[float],
    speaker_window: Sequence[float],
    speaker: str,
    identity_reference: Mapping[str, Any],
    vision_review: Mapping[str, Any],
    observed_at: str,
    montage_command_hint: str | None = None,
) -> dict[str, Any]:
    """Assemble the phase-12 observation packet. Pure: no live calls."""
    manifest_frames = frames_manifest.get("frames") or []
    sampling_mode = str(frames_manifest.get("sampling_mode") or "unknown")
    transcript_source = transcript.get("source")

    coverage_gaps: list[str] = []
    frame_evidence: list[dict[str, Any]] = []
    identity_review_frames: list[dict[str, Any]] = []
    speaker_visibility_frames: list[dict[str, Any]] = []
    per_frame_vlm_gap = False

    for frame in manifest_frames:
        index = int(frame["index"])
        ts = float(frame["timestamp_seconds"])
        file_path = frame_files.get(index)
        if file_path is None or not file_path.is_file():
            coverage_gaps.append(f"frame_{index}_file_missing")
            continue
        rel = file_path.resolve().relative_to(packet_root.resolve()).as_posix()
        entities, gap = _frame_observed_entities(report, index)
        if gap:
            per_frame_vlm_gap = True
        in_identity = _in_window(ts, identity_window)
        in_speaker = _in_window(ts, speaker_window)
        frame_evidence.append({
            "index": index,
            "timestamp_seconds": ts,
            "path": rel,
            "sha256": sha256_file(file_path),
            "size_bytes": file_path.stat().st_size,
            "observed_entities": entities,
            "in_identity_window": in_identity,
            "in_speaker_window": in_speaker,
        })
        if in_identity:
            identity_review_frames.append({"index": index, "timestamp_seconds": ts, "path": rel})
        if in_speaker:
            speaker_visibility_frames.append({"index": index, "timestamp_seconds": ts, "path": rel})

    if per_frame_vlm_gap:
        coverage_gaps.append(
            "per_frame_vlm_entities_unavailable: watch scillm vlm frame "
            "descriptions did not resolve; per-frame entity lists are empty"
        )
    if not identity_review_frames:
        coverage_gaps.append(
            f"no_frame_in_identity_window_{identity_window[0]}_{identity_window[1]}"
        )
    if not speaker_visibility_frames:
        coverage_gaps.append(
            f"no_frame_in_speaker_window_{speaker_window[0]}_{speaker_window[1]}"
        )

    transcript_facts: list[dict[str, Any]] = []
    for i, seg in enumerate(transcript.get("segments") or []):
        text = str(seg.get("text") or "").strip()
        if not text:
            continue
        start = float(seg.get("start") or 0.0)
        end = start + float(seg.get("duration") or 0.0)
        transcript_facts.append({
            "fact_id": f"transcript_seg_{i:03d}",
            "statement": text,
            "time_range": [start, end],
            "evidence_refs": ["watch/transcript.json"],
            "confidence": 0.9 if transcript_source else 0.0,
        })

    line_at_interval = next(
        (f["statement"] for f in transcript_facts
         if f["time_range"][1] > speaker_window[0] and f["time_range"][0] < speaker_window[1]),
        None,
    )

    vision_status = str(vision_review.get("status") or "not_performed")
    if vision_status not in {"performed"}:
        capability_vision = f"degraded:{vision_review.get('reason') or vision_status}"
    else:
        capability_vision = "ok"

    status = "PASS_WATCH_GAUNTLET_OBSERVATION"
    if not frame_evidence:
        status = "BLOCKED_WATCH_GAUNTLET_OBSERVATION"
    elif coverage_gaps:
        status = "DEGRADED_WATCH_GAUNTLET_OBSERVATION"

    packet = {
        "schema": PACKET_SCHEMA,
        "status": status,
        "evidence_origin": evidence_origin,
        "run_id": run_id,
        "revision_id": revision_id,
        "source_revision_id": source_revision_id,
        "source_video": source_video_basename,
        "source_video_sha256": source_video_sha256,
        "source_video_size_bytes": source_video_size_bytes,
        "duration_seconds": duration_seconds,
        "perception": {
            "skill": "watch",
            "requested_mode": requested_mode,
            "sampling_mode": sampling_mode,
            "frame_count": len(frame_evidence),
            "transcript_source": transcript_source,
            "capabilities": {
                "frames": "ok",
                "transcript": "ok" if transcript_source else "degraded:no_transcript_source",
                "vision_identity_review": capability_vision,
            },
        },
        "watch_artifacts": {
            "frames_manifest": watch_artifacts["frames_manifest"],
            "transcript": watch_artifacts["transcript"],
            "scenes": watch_artifacts["scenes"],
            "report": watch_artifacts["report"],
        },
        "frame_evidence": frame_evidence,
        "transcript_facts": transcript_facts,
        "coverage_gaps": coverage_gaps,
        "step_hooks": {
            "step_35_frame_contact_sheet": {
                "frame_indices": [f["index"] for f in frame_evidence],
                "frame_timestamps": [f["timestamp_seconds"] for f in frame_evidence],
                "sampling_mode": sampling_mode,
                "source_frames_manifest": "watch/frames_manifest.json",
                "montage_command_hint": montage_command_hint
                or "montage <frames> -tile 4x3 -geometry 320x180+4+4 frame_contact_sheet.png",
            },
            "step_36_identity_temporal_continuity": {
                "identity_window_seconds": [identity_window[0], identity_window[1]],
                "identity_review_frames": identity_review_frames,
                "identity_reference": dict(identity_reference),
                "vision_review": dict(vision_review),
            },
            "step_38_visible_speaker_lipsync": {
                "speaker": speaker,
                "spoken_interval_seconds": [speaker_window[0], speaker_window[1]],
                "speaker_visibility_frames": speaker_visibility_frames,
                "transcript_line_at_interval": line_at_interval,
                "speaker_visibility_flagged": bool(speaker_visibility_frames),
            },
        },
        "psychological_interpretation_performed": False,
        "mocked": False,
        "live": True,
        "observed_at": observed_at,
        "claims": {
            "proves": [
                "the /watch skill extracts scene-driven frames and a Whisper "
                "transcript from a returned MP4 and localizes the identity and "
                "speaker-visibility evidence windows without the fixed 12-frame lane",
            ],
            "does_not_prove": [
                "acceptable lip synchronization",
                "stable Embry identity on any successor return",
                "deterministic face-embedding similarity",
            ],
        },
    }
    return packet


def validate_observation_packet(packet: Mapping[str, Any]) -> list[str]:
    """Return jsonschema errors (empty == valid). Pure."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    return [f"{'/'.join(str(p) for p in e.path)}: {e.message}"
            for e in sorted(validator.iter_errors(dict(packet)), key=lambda e: list(e.path))]


# --------------------------------------------------------------------------- #
# Pure: evaluate ground-truth validation
# --------------------------------------------------------------------------- #
def evaluate_validation(
    packet: Mapping[str, Any],
    ground_truth: Mapping[str, Any],
) -> dict[str, Any]:
    """Score the observation packet against historical ground-truth. Pure."""
    hooks = packet.get("step_hooks", {})
    id_hook = hooks.get("step_36_identity_temporal_continuity", {})
    sp_hook = hooks.get("step_38_visible_speaker_lipsync", {})
    transcript_facts = packet.get("transcript_facts", [])

    identity_window = ground_truth["identity_window"]
    speaker_window = ground_truth["speaker_window"]
    canonical_line = ground_truth["canonical_line"]
    fa_interval = ground_truth["forced_alignment_interval"]
    expected_verdict = ground_truth.get("expected_vision_verdict", "DRIFT")

    def _norm(text: str) -> str:
        return "".join(ch for ch in text.lower() if ch.isalnum())

    expectations: list[dict[str, Any]] = []

    id_frames = id_hook.get("identity_review_frames", [])
    id_ts = [round(f["timestamp_seconds"], 4) for f in id_frames]
    expectations.append({
        "id": "frames_cover_identity_window_00_03",
        "expectation": f"perception samples >=1 frame inside {identity_window}s (Embry identity-drift window)",
        "expected": f"frame timestamp within [{identity_window[0]}, {identity_window[1]}]",
        "watch_found": f"{len(id_frames)} frame(s) at {id_ts}",
        "verdict": "VALIDATED" if id_frames else "NOT_VALIDATED",
    })

    sp_frames = sp_hook.get("speaker_visibility_frames", [])
    sp_ts = [round(f["timestamp_seconds"], 4) for f in sp_frames]
    expectations.append({
        "id": "frames_cover_speaker_window_05_077",
        "expectation": f"perception samples >=1 frame inside {speaker_window}s (visible-speaker window)",
        "expected": f"frame timestamp within [{speaker_window[0]}, {speaker_window[1]}]",
        "watch_found": f"{len(sp_frames)} frame(s) at {sp_ts}",
        "verdict": "VALIDATED" if sp_frames else "NOT_VALIDATED",
    })

    matching = next((f for f in transcript_facts if _norm(canonical_line) in _norm(f["statement"])
                     or _norm(f["statement"]) in _norm(canonical_line)), None)
    overlaps_fa = bool(matching) and matching["time_range"][1] > fa_interval[0] and matching["time_range"][0] < fa_interval[1]
    expectations.append({
        "id": "transcript_recovers_canonical_kai_line",
        "expectation": "Whisper transcript recovers the canonical Kai line consistent with the forced-alignment receipt",
        "expected": f"text≈{canonical_line!r} overlapping forced-alignment {fa_interval}s",
        "watch_found": (
            f"{matching['statement']!r} at {[round(x,3) for x in matching['time_range']]}s"
            if matching else "canonical line not found in transcript"
        ),
        "verdict": "VALIDATED" if (matching and overlaps_fa) else "NOT_VALIDATED",
    })

    flagged = bool(sp_hook.get("speaker_visibility_flagged"))
    expectations.append({
        "id": "packet_flags_speaker_visibility_window",
        "expectation": "the observation packet flags the visible-speaker window for step 38",
        "expected": "step_38_visible_speaker_lipsync.speaker_visibility_flagged == true with frames + transcript line",
        "watch_found": (
            f"flagged={flagged}, line_at_interval={sp_hook.get('transcript_line_at_interval')!r}, "
            f"{len(sp_frames)} visibility frame(s)"
        ),
        "verdict": "VALIDATED" if (flagged and sp_hook.get("transcript_line_at_interval")) else "NOT_VALIDATED",
    })

    vision = id_hook.get("vision_review", {})
    v_verdict = str(vision.get("verdict") or "INDETERMINATE")
    v_status = str(vision.get("status") or "not_performed")
    if v_status != "performed":
        vision_result = "NOT_VALIDATED_DEGRADED"
    else:
        vision_result = "VALIDATED" if v_verdict == expected_verdict else "NOT_VALIDATED"
    expectations.append({
        "id": "vision_corroborates_embry_identity_drift_00_03",
        "expectation": f"the codex/scillm vision layer independently corroborates {expected_verdict} on the {identity_window}s Embry frames vs embry_contact_sheet_v3",
        "expected": f"independent vision VERDICT == {expected_verdict}",
        "watch_found": f"vision status={v_status}, verdict={v_verdict}, model={vision.get('model')}",
        "verdict": vision_result,
    })

    verdicts = [e["verdict"] for e in expectations]
    if all(v == "VALIDATED" for v in verdicts):
        overall = "PASS_WATCH_GAUNTLET_VALIDATED"
    elif any(v == "NOT_VALIDATED" for v in verdicts):
        overall = "FAIL_WATCH_GAUNTLET_VALIDATION"
    else:
        overall = "PASS_WATCH_GAUNTLET_VALIDATED_WITH_DEGRADED_CAPABILITIES"
    return {"expectations": expectations, "overall_status": overall}


# --------------------------------------------------------------------------- #
# Live: memory persistence
# --------------------------------------------------------------------------- #
def _contains_authored_value(observed: Any, expected: Any) -> bool:
    if isinstance(expected, Mapping):
        return isinstance(observed, Mapping) and all(
            key in observed and _contains_authored_value(observed[key], value)
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        return isinstance(observed, list) and observed == expected
    return observed == expected


def persist_memory_live(
    *,
    record_key: str,
    document: Mapping[str, Any],
    memory_base_url: str,
) -> dict[str, Any]:
    """Upsert one gauntlet record and prove an exact reread. Live."""
    timeout = httpx.Timeout(30.0, connect=2.0)
    doc = {k: v for k, v in document.items() if k not in MEMORY_SERVER_FIELDS}
    doc["_key"] = record_key
    with httpx.Client(base_url=memory_base_url, timeout=timeout) as client:
        write = client.post("/upsert", json={"collection": MEMORY_COLLECTION, "documents": [doc]})
        write.raise_for_status()
        reread = client.post("/list", json={
            "collection": MEMORY_COLLECTION, "limit": 2, "filters": {"_key": record_key},
        })
        reread.raise_for_status()
        items = reread.json().get("documents") or reread.json().get("items") or []
        if len(items) != 1:
            raise RuntimeError(f"exact reread count mismatch for {record_key}: {len(items)}")
        observed = items[0]
        for field in ("_key", "schema", "status", "source_video_sha256",
                      "observation_packet_sha256", "validation_receipt_sha256", "claims"):
            if not _contains_authored_value(observed.get(field), doc.get(field)):
                raise RuntimeError(f"exact reread field mismatch for {record_key}: {field}")
    return {"record_key": record_key, "exact_reread": True,
            "semantic_sync_state": observed.get("semantic_sync_state")}


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def _copy_frames(manifest: Mapping[str, Any], watch_out_dir: Path, dest_frames: Path) -> dict[int, Path]:
    """Copy watch frames into the packet tree; map manifest index -> copied file."""
    dest_frames.mkdir(parents=True, exist_ok=True)
    src_frames = sorted((watch_out_dir / "frames").glob("*.jpg"))
    frames = manifest.get("frames") or []
    mapping: dict[int, Path] = {}
    for pos, frame in enumerate(frames):
        index = int(frame["index"])
        src = Path(frame.get("path") or "")
        if not src.is_file() and pos < len(src_frames):
            src = src_frames[pos]
        if not src.is_file():
            continue
        dest = dest_frames / f"frame_{index:04d}.jpg"
        shutil.copy2(src, dest)
        mapping[index] = dest
    return mapping


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True, help="Returned MP4 (read-only input)")
    parser.add_argument("--out-root", type=Path, required=True,
                        help="Directory under which watch_gauntlet/<sha_prefix>/ is written")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--revision-id", required=True, help="Revision the OUTPUTS belong to")
    parser.add_argument("--source-revision-id", required=True, help="Revision the video was returned under")
    parser.add_argument("--evidence-origin", default="historical_provider_return")
    parser.add_argument("--identity-reference", type=Path, required=True,
                        help="embry_contact_sheet_v3 reference image")
    parser.add_argument("--identity-window", default="0.0,3.5",
                        help="Embry identity-drift window. Default spans the frozen receipt's "
                             "readable_appearances (0.0 setup through the 2.51-3.35s close shot).")
    parser.add_argument("--speaker", default="Kai")
    parser.add_argument("--speaker-window", default="5.0,7.7")
    parser.add_argument("--canonical-line", default="If we paddle now, we're cutting across the lineup.")
    parser.add_argument("--forced-alignment-interval", default="5.0,7.7")
    parser.add_argument("--expected-vision-verdict", default="DRIFT")
    parser.add_argument("--watch-skill-dir", type=Path, default=WATCH_SKILL_DIR_DEFAULT)
    parser.add_argument("--codex-skill-dir", type=Path, default=ROOT.parents[0] / "codex")
    parser.add_argument("--no-vision", action="store_true", help="Skip the live codex vision review")
    parser.add_argument("--memory-base-url", default="http://127.0.0.1:8601")
    parser.add_argument("--no-memory", action="store_true")
    args = parser.parse_args()

    identity_window = [float(x) for x in args.identity_window.split(",")]
    speaker_window = [float(x) for x in args.speaker_window.split(",")]
    fa_interval = [float(x) for x in args.forced_alignment_interval.split(",")]

    video = args.video.resolve()
    if not video.is_file():
        raise SystemExit(f"video missing: {video}")
    reference = args.identity_reference.resolve()
    if not reference.is_file():
        raise SystemExit(f"identity reference missing: {reference}")

    observed_at = datetime.now(timezone.utc).isoformat()
    video_sha = sha256_file(video)
    sha_prefix = video_sha.removeprefix("sha256:")[:12]
    packet_root = (args.out_root / "watch_gauntlet" / sha_prefix).resolve()
    packet_root.mkdir(parents=True, exist_ok=True)
    watch_out_dir = packet_root / "watch"

    print(f"[gauntlet] running /watch on {video.name} -> {watch_out_dir}", file=sys.stderr)
    watch_result = run_watch_live(video, watch_out_dir, watch_skill_dir=args.watch_skill_dir)
    manifest = watch_result["frames_manifest"]

    frame_files = _copy_frames(manifest, watch_out_dir, packet_root / "watch" / "frames_bound")
    duration = ffprobe_duration(video)

    identity_ts_frames = sorted(
        [f for f in manifest.get("frames", []) if _in_window(float(f["timestamp_seconds"]), identity_window)],
        key=lambda f: f["timestamp_seconds"],
    )
    id_frame_paths = [frame_files[int(f["index"])] for f in identity_ts_frames if int(f["index"]) in frame_files]

    if args.no_vision or not id_frame_paths:
        vision_review = {"status": "not_performed",
                         "reason": "vision disabled" if args.no_vision else "no identity-window frame",
                         "verdict": "INDETERMINATE"}
    else:
        print(f"[gauntlet] codex vision identity review over {len(id_frame_paths)} frame(s)", file=sys.stderr)
        vision_review = run_vision_identity_review_live(
            reference, id_frame_paths[:6], codex_skill_dir=args.codex_skill_dir,
        )

    watch_artifacts = {
        "frames_manifest": file_ref(packet_root, watch_result["frames_manifest_path"]),
        "transcript": file_ref(packet_root, watch_result["transcript_path"]),
        "scenes": file_ref(packet_root, watch_result["scenes_path"]),
        "report": file_ref(packet_root, watch_result["report_path"])
        if watch_result["report_path"] else file_ref(packet_root, watch_result["frames_manifest_path"]),
    }

    identity_reference = {
        "asset_id": "embry_contact_sheet_v3",
        "path": str(reference),
        "sha256": sha256_file(reference),
    }

    packet = build_observation_packet(
        packet_root=packet_root,
        frames_manifest=manifest,
        transcript=watch_result["transcript"],
        report=watch_result["report"],
        frame_files=frame_files,
        watch_artifacts=watch_artifacts,
        source_video_basename=video.name,
        source_video_sha256=video_sha,
        source_video_size_bytes=video.stat().st_size,
        duration_seconds=duration,
        run_id=args.run_id,
        revision_id=args.revision_id,
        source_revision_id=args.source_revision_id,
        evidence_origin=args.evidence_origin,
        requested_mode="scene-change",
        identity_window=identity_window,
        speaker_window=speaker_window,
        speaker=args.speaker,
        identity_reference=identity_reference,
        vision_review=vision_review,
        observed_at=observed_at,
    )
    errors = validate_observation_packet(packet)
    if errors:
        raise SystemExit("observation packet failed schema validation:\n" + "\n".join(errors))
    packet_path = write_json(packet_root / "dream_observation_packet.v1.json", packet)
    packet_sha = sha256_file(packet_path)

    ground_truth = {
        "identity_window": identity_window,
        "speaker_window": speaker_window,
        "canonical_line": args.canonical_line,
        "forced_alignment_interval": fa_interval,
        "expected_vision_verdict": args.expected_vision_verdict,
    }
    scored = evaluate_validation(packet, ground_truth)
    validation_receipt = {
        "schema": VALIDATION_SCHEMA,
        "status": scored["overall_status"],
        "run_id": args.run_id,
        "revision_id": args.revision_id,
        "source_revision_id": args.source_revision_id,
        "source_video": video.name,
        "source_video_sha256": video_sha,
        "observation_packet": {"path": packet_path.relative_to(packet_root).as_posix(),
                               "sha256": packet_sha},
        "ground_truth_expectations": ground_truth,
        "expectations": scored["expectations"],
        "overall_status": scored["overall_status"],
        "degraded_capabilities": [
            name for name, val in packet["perception"]["capabilities"].items()
            if str(val).startswith("degraded")
        ],
        "mocked": False,
        "live": True,
        "observed_at": observed_at,
        "claims": {
            "proves": [
                "the /watch perception lane, from scene-driven sampling, "
                "independently captures the identity-drift and visible-speaker "
                "evidence windows that the fixed 12-frame contact sheet was used to catch",
            ],
            "does_not_prove": [
                "phase 12 is complete (no successor provider return exists)",
                "acceptable lip synchronization or stable Embry identity on a repair",
            ],
        },
    }
    validation_path = write_json(packet_root / "watch_gauntlet_validation_receipt.v1.json", validation_receipt)
    validation_sha = sha256_file(validation_path)

    memory_result: dict[str, Any] = {"persisted": False}
    if not args.no_memory:
        record_key = hashlib.sha256(
            f"{args.run_id}:{args.revision_id}:watch_gauntlet:{sha_prefix}".encode()
        ).hexdigest()[:32]
        document = {
            "schema": "persona_dream.watch_gauntlet_memory_record.v1",
            "status": scored["overall_status"],
            "run_id": args.run_id,
            "revision_id": args.revision_id,
            "source_revision_id": args.source_revision_id,
            "source_video_sha256": video_sha,
            "observation_packet_sha256": packet_sha,
            "validation_receipt_sha256": validation_sha,
            "sampling_mode": packet["perception"]["sampling_mode"],
            "transcript_source": packet["perception"]["transcript_source"],
            "vision_verdict": vision_review.get("verdict"),
            "expectation_verdicts": {e["id"]: e["verdict"] for e in scored["expectations"]},
            "retrieval_text": (
                f"Persona Dream {args.run_id} {args.revision_id} watch post-return gauntlet "
                f"validated on historical Kling return {sha_prefix} status {scored['overall_status']}; "
                f"GOAL.md steps 35/36/38 perception hooks; vision verdict {vision_review.get('verdict')}"
            ),
            "tags": [
                "persona-dream", f"run:{args.run_id}", f"revision:{args.revision_id}",
                "watch-gauntlet", "phase-12", f"status:{scored['overall_status'].lower()}",
            ],
            "observed_at": observed_at,
            "mocked": False,
            "live": True,
            "claims": validation_receipt["claims"],
        }
        try:
            memory_result = {"persisted": True, **persist_memory_live(
                record_key=record_key, document=document, memory_base_url=args.memory_base_url,
            )}
        except Exception as exc:  # noqa: BLE001 - degrade explicitly
            memory_result = {"persisted": False, "blocker": f"memory persistence failed: {exc}"}

    summary = {
        "gauntlet_script": str(Path(__file__).resolve()),
        "packet_dir": str(packet_root),
        "observation_packet_path": str(packet_path),
        "observation_packet_status": packet["status"],
        "validation_receipt_path": str(validation_path),
        "validation_status": scored["overall_status"],
        "sampling_mode": packet["perception"]["sampling_mode"],
        "frame_count": packet["perception"]["frame_count"],
        "vision_verdict": vision_review.get("verdict"),
        "expectations": {e["id"]: e["verdict"] for e in scored["expectations"]},
        "coverage_gaps": packet["coverage_gaps"],
        "memory": memory_result,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
