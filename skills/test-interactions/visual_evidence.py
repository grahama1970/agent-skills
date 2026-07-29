"""Structured visual evidence and visual-finding helpers for test-interactions.

The functions in this module preserve deterministic interaction verdicts while
producing replayable visual artifacts for downstream review. They do not call an
LLM and they fail closed when candidate findings do not match the v1 schema.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

from cdp_client import CDPClient

VISUAL_EVIDENCE_SCHEMA = "test-interactions.visual-evidence.v1"
VISUAL_FINDING_SCHEMA = "test-interactions.visual-finding.v1"

REQUIRED_FINDING_FIELDS = {
    "schema",
    "finding_id",
    "fingerprint",
    "run_id",
    "surface",
    "element",
    "interaction_step",
    "finding_kind",
    "confidence",
    "observed_state",
    "expected_state",
    "reproduction",
    "deterministic_status",
    "evidence",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def qid_from_selector(selector: str) -> str:
    for quote in ("'", '"'):
        prefix = f"[data-qid={quote}"
        suffix = f"{quote}]"
        if selector.startswith(prefix) and selector.endswith(suffix):
            return selector[len(prefix) : -len(suffix)]
    return ""


def _scale_rect(rect: dict[str, float], scale_x: float, scale_y: float, padding: int) -> tuple[int, int, int, int]:
    x0 = math.floor((rect["x"] - padding) * scale_x)
    y0 = math.floor((rect["y"] - padding) * scale_y)
    x1 = math.ceil((rect["x"] + rect["width"] + padding) * scale_x)
    y1 = math.ceil((rect["y"] + rect["height"] + padding) * scale_y)
    return x0, y0, x1, y1


def _clamp_box(box: tuple[int, int, int, int], width: int, height: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    x0 = max(0, min(width - 1, x0))
    y0 = max(0, min(height - 1, y0))
    x1 = max(x0 + 1, min(width, x1))
    y1 = max(y0 + 1, min(height, y1))
    return x0, y0, x1, y1


def _write_crop(
    image: Image.Image,
    rect: dict[str, float],
    viewport: dict[str, float],
    output_path: Path,
    *,
    padding: int,
) -> dict[str, Any]:
    scale_x = image.width / max(1.0, float(viewport.get("width") or image.width))
    scale_y = image.height / max(1.0, float(viewport.get("height") or image.height))
    box = _clamp_box(_scale_rect(rect, scale_x, scale_y, padding), image.width, image.height)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.crop(box).save(output_path)
    return {
        "path": str(output_path),
        "padding": padding,
        "image_box": {"x0": box[0], "y0": box[1], "x1": box[2], "y1": box[3]},
        "scale": {"x": scale_x, "y": scale_y},
    }


def _enlarge_image(source: Path, output_path: Path, scale: int) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as img:
        enlarged = img.resize((img.width * scale, img.height * scale), Image.Resampling.LANCZOS)
        enlarged.save(output_path)
        return {"path": str(output_path), "scale": scale, "width": enlarged.width, "height": enlarged.height}


def capture_step_visual_evidence(
    cdp: CDPClient,
    *,
    source_screenshot: Path,
    output_dir: Path,
    surface: str,
    element: str,
    action: str,
    description: str,
    step_index: int,
    interaction: dict[str, Any],
    deterministic_status: str,
    run_id: str,
) -> dict[str, Any]:
    """Create QID crop, semantic-container crop, enlarged crop, and metadata."""
    target_selector = str(
        interaction.get("review_target")
        or interaction.get("focus")
        or interaction.get("target")
        or ""
    ).strip()
    if not target_selector:
        return {}

    target_rect = cdp.get_bounding_rect(target_selector)
    if not target_rect:
        return {
            "schema": VISUAL_EVIDENCE_SCHEMA,
            "status": "missing_target",
            "target_selector": target_selector,
        }

    qid = cdp.get_attribute(target_selector, "data-qid") or qid_from_selector(target_selector)
    viewport = cdp.viewport()
    semantic_selector = str(
        interaction.get("semantic_container")
        or interaction.get("review_pane")
        or interaction.get("container")
        or ""
    ).strip()
    semantic_rect = cdp.get_bounding_rect(semantic_selector) if semantic_selector else None
    if not semantic_rect:
        semantic = cdp.nearest_semantic_container(target_selector)
        if semantic:
            semantic_selector = semantic.get("selector") or ""
            semantic_rect = semantic.get("rect")

    padding = int(interaction.get("visual_crop_padding", interaction.get("review_crop_padding", 24)))
    semantic_padding = int(interaction.get("visual_semantic_padding", 12))
    enlarge_scale = int(interaction.get("visual_enlarge_scale", 2))
    evidence_dir = output_dir / "visual-evidence"
    stem = f"{step_index:04d}_{surface}_{element}_{action}".replace("/", "_")

    with Image.open(source_screenshot).convert("RGB") as image:
        target_crop = _write_crop(
            image,
            target_rect,
            viewport,
            evidence_dir / f"{stem}_target-crop.png",
            padding=padding,
        )
        enlarged = _enlarge_image(
            Path(target_crop["path"]),
            evidence_dir / f"{stem}_target-crop-{enlarge_scale}x.png",
            enlarge_scale,
        )
        semantic_crop = {}
        if semantic_rect:
            semantic_crop = _write_crop(
                image,
                semantic_rect,
                viewport,
                evidence_dir / f"{stem}_semantic-container.png",
                padding=semantic_padding,
            )

    metadata_path = evidence_dir / f"{stem}_metadata.json"
    metadata = {
        "schema": VISUAL_EVIDENCE_SCHEMA,
        "run_id": run_id,
        "generated_at": utc_now(),
        "surface": surface,
        "element": element,
        "action": action,
        "description": description,
        "interaction_step": step_index,
        "deterministic_status": deterministic_status,
        "source_image": str(source_screenshot),
        "qid": qid,
        "target_selector": target_selector,
        "semantic_container_selector": semantic_selector,
        "target_bbox": {k: round(float(v), 3) for k, v in target_rect.items()},
        "semantic_container_bbox": {k: round(float(v), 3) for k, v in (semantic_rect or {}).items()},
        "viewport": {k: round(float(v), 3) for k, v in viewport.items()},
        "artifacts": {
            "target_crop": target_crop,
            "target_crop_enlarged": enlarged,
            "semantic_container_crop": semantic_crop,
        },
    }
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    metadata["metadata_path"] = str(metadata_path)
    return metadata


def _capture_animation_frames(
    cdp: CDPClient,
    *,
    target_selector: str,
    frame_dir: Path,
    frame_count: int,
    interval_ms: int,
) -> list[dict[str, Any]]:
    frame_dir.mkdir(parents=True, exist_ok=True)
    frames: list[dict[str, Any]] = []
    start = time.monotonic()
    for index in range(frame_count):
        path = frame_dir / f"frame_{index:03d}.png"
        cdp.screenshot(str(path))
        clip = cdp.clipping_status(target_selector)
        frames.append(
            {
                "index": index,
                "timestamp_ms": int((time.monotonic() - start) * 1000),
                "path": str(path),
                "clipping": clip,
            }
        )
        if index < frame_count - 1:
            time.sleep(interval_ms / 1000.0)
    return frames


def _write_playable_video(frame_dir: Path, output_path: Path, interval_ms: int) -> dict[str, Any]:
    frames = sorted(frame_dir.glob("frame_*.png"))
    if not frames:
        return {"status": "no_frames"}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        fps = max(1, round(1000 / max(1, interval_ms)))
        cmd = [
            ffmpeg,
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frame_dir / "frame_%03d.png"),
            "-c:v",
            "libvpx-vp9",
            "-pix_fmt",
            "yuva420p",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and output_path.is_file() and output_path.stat().st_size > 0:
            return {"status": "ok", "path": str(output_path), "format": "webm", "fps": fps}
        return {
            "status": "ffmpeg_failed",
            "path": str(output_path),
            "stdout": result.stdout[-1000:],
            "stderr": result.stderr[-1000:],
        }

    gif_path = output_path.with_suffix(".gif")
    images = [Image.open(frame).convert("RGB") for frame in frames]
    images[0].save(gif_path, save_all=True, append_images=images[1:], duration=interval_ms, loop=0)
    for image in images:
        image.close()
    return {"status": "ok", "path": str(gif_path), "format": "gif", "fps": max(1, round(1000 / max(1, interval_ms)))}


def capture_animation_evidence(
    cdp: CDPClient,
    *,
    output_dir: Path,
    step_index: int,
    surface: str,
    element: str,
    action: str,
    interaction: dict[str, Any],
) -> dict[str, Any]:
    target_selector = str(interaction.get("target") or interaction.get("review_target") or "").strip()
    if not target_selector:
        return {}
    frame_count = int(interaction.get("animation_frames", interaction.get("burst_frames", 10)))
    interval_ms = int(interaction.get("animation_interval_ms", interaction.get("burst_interval_ms", 100)))
    stem = f"{step_index:04d}_{surface}_{element}_{action}".replace("/", "_")
    frame_dir = output_dir / "visual-evidence" / f"{stem}_animation_frames"
    frames = _capture_animation_frames(
        cdp,
        target_selector=target_selector,
        frame_dir=frame_dir,
        frame_count=frame_count,
        interval_ms=interval_ms,
    )
    video = _write_playable_video(frame_dir, output_dir / "visual-evidence" / f"{stem}_animation.webm", interval_ms)
    metadata_path = output_dir / "visual-evidence" / f"{stem}_animation_metadata.json"
    clipped_frames = [frame for frame in frames if (frame.get("clipping") or {}).get("clipped")]
    metadata = {
        "schema": "test-interactions.animation-evidence.v1",
        "generated_at": utc_now(),
        "surface": surface,
        "element": element,
        "action": action,
        "interaction_step": step_index,
        "target_selector": target_selector,
        "target_qid": cdp.get_attribute(target_selector, "data-qid") or qid_from_selector(target_selector),
        "frame_count": len(frames),
        "interval_ms": interval_ms,
        "frames": frames,
        "video": video,
        "time_range_ms": {
            "start": frames[0]["timestamp_ms"] if frames else 0,
            "end": frames[-1]["timestamp_ms"] if frames else 0,
        },
        "clipped_frame_count": len(clipped_frames),
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    metadata["metadata_path"] = str(metadata_path)
    return metadata


def finding_fingerprint(finding: dict[str, Any]) -> str:
    payload = {
        "run_id": finding.get("run_id"),
        "surface": finding.get("surface"),
        "element": finding.get("element"),
        "interaction_step": finding.get("interaction_step"),
        "qid": finding.get("qid"),
        "finding_kind": finding.get("finding_kind"),
        "expected_state": finding.get("expected_state"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]


def validate_visual_finding(finding: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    missing = sorted(REQUIRED_FINDING_FIELDS - set(finding))
    if missing:
        errors.append(f"missing fields: {', '.join(missing)}")
    if finding.get("schema") != VISUAL_FINDING_SCHEMA:
        errors.append(f"schema must be {VISUAL_FINDING_SCHEMA}")
    confidence = finding.get("confidence")
    if not isinstance(confidence, (int, float)) or not (0 <= float(confidence) <= 1):
        errors.append("confidence must be a number in [0, 1]")
    evidence = finding.get("evidence")
    if not isinstance(evidence, dict):
        errors.append("evidence must be an object")
    elif not any(evidence.get(key) for key in ("screenshot", "target_crop", "video")):
        errors.append("evidence must include screenshot, target_crop, or video")
    if finding.get("deterministic_status") not in {"PASS", "FAIL", "WARN", "SKIP"}:
        errors.append("deterministic_status must be PASS, FAIL, WARN, or SKIP")
    return not errors, errors


def build_animation_clipping_finding(
    *,
    run_id: str,
    surface: str,
    element: str,
    step_index: int,
    qid: str,
    deterministic_status: str,
    visual_evidence: dict[str, Any],
    animation_evidence: dict[str, Any],
    expected_state: str,
    reproduction: str,
) -> dict[str, Any]:
    evidence_paths = {
        "screenshot": visual_evidence.get("source_image"),
        "target_crop": ((visual_evidence.get("artifacts") or {}).get("target_crop") or {}).get("path"),
        "target_crop_enlarged": ((visual_evidence.get("artifacts") or {}).get("target_crop_enlarged") or {}).get("path"),
        "semantic_container_crop": ((visual_evidence.get("artifacts") or {}).get("semantic_container_crop") or {}).get("path"),
        "crop_metadata": visual_evidence.get("metadata_path"),
        "video": (animation_evidence.get("video") or {}).get("path"),
        "video_metadata": animation_evidence.get("metadata_path"),
    }
    finding = {
        "schema": VISUAL_FINDING_SCHEMA,
        "finding_id": "",
        "fingerprint": "",
        "run_id": run_id,
        "surface": surface,
        "element": element,
        "interaction_step": step_index,
        "qid": qid,
        "finding_kind": "animation_clipping",
        "confidence": 0.95,
        "observed_state": f"{animation_evidence.get('clipped_frame_count', 0)} animation frame(s) clipped by an ancestor viewport",
        "expected_state": expected_state or "Animated target should remain visibly inside its semantic container during transition.",
        "reproduction": reproduction,
        "deterministic_status": deterministic_status,
        "evidence": {k: v for k, v in evidence_paths.items() if v},
        "video_time_range_ms": animation_evidence.get("time_range_ms") or {},
    }
    finding["fingerprint"] = finding_fingerprint(finding)
    finding["finding_id"] = f"vfind-{finding['fingerprint']}"
    return finding


def parse_analyst_findings(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse JSON/JSONL analyst output and return only schema-valid findings."""
    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    try:
        parsed = json.loads(text)
        candidates = parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        candidates = []
        for line_no, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                candidates.append(json.loads(line))
            except json.JSONDecodeError as exc:
                invalid.append({"line": line_no, "error": str(exc), "raw": line})
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            invalid.append({"index": index, "error": "candidate is not an object", "raw": candidate})
            continue
        ok, errors = validate_visual_finding(candidate)
        if ok:
            valid.append(candidate)
        else:
            invalid.append({"index": index, "errors": errors, "raw": candidate})
    return valid, invalid


def write_findings_jsonl(path: Path, findings: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for finding in findings:
            ok, errors = validate_visual_finding(finding)
            if not ok:
                raise ValueError(f"invalid visual finding: {errors}")
            fh.write(json.dumps(finding, sort_keys=True) + "\n")
