"""FFmpeg frame extraction with scene-change detection and auto-scaled frame budgets.

Core innovation: uses ffmpeg `select='gt(scene,T)'` to extract one frame per
detected visual cut instead of uniform N-second sampling. Falls back to uniform
sampling when scene changes are too few (static/talking-head videos).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


MAX_FPS = 2.0
MAX_FRAMES = 100
SCENE_THRESHOLD = 0.3
UNIFORM_FALLBACK_MIN = 10


def parse_time(value: str | float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    parts = s.split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except ValueError:
        pass
    raise SystemExit(f"Cannot parse time: {value!r} (use SS, MM:SS, or HH:MM:SS)")


def format_time(seconds: float) -> str:
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, sec = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"


def get_metadata(video_path: str) -> dict:
    if shutil.which("ffprobe") is None:
        raise RuntimeError("ffprobe not found on PATH. Install ffmpeg.")
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams",
         str(Path(video_path).resolve())],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr.strip()}")
    data = json.loads(result.stdout or "{}")
    streams = data.get("streams", [])
    fmt = data.get("format", {})
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = float(fmt.get("duration") or video_stream.get("duration") or 0)
    return {
        "duration_seconds": duration,
        "width": video_stream.get("width"),
        "height": video_stream.get("height"),
        "codec": video_stream.get("codec_name"),
        "size_bytes": int(fmt.get("size") or 0),
        "has_audio": audio_stream is not None,
    }


def auto_fps(duration_seconds: float, max_frames: int = MAX_FRAMES) -> tuple[float, int]:
    if duration_seconds <= 0:
        return 1.0, 1
    if duration_seconds <= 30:
        target = min(max_frames, max(12, int(round(duration_seconds))))
    elif duration_seconds <= 60:
        target = min(max_frames, 40)
    elif duration_seconds <= 180:
        target = min(max_frames, 60)
    elif duration_seconds <= 600:
        target = min(max_frames, 80)
    else:
        target = max_frames
    fps = min(target / duration_seconds, MAX_FPS)
    target = min(max_frames, max(1, int(round(fps * duration_seconds))))
    return fps, target


def auto_fps_focus(duration_seconds: float, max_frames: int = MAX_FRAMES) -> tuple[float, int]:
    if duration_seconds <= 0:
        return min(MAX_FPS, 2.0), 2
    if duration_seconds <= 5:
        target = min(max_frames, max(10, int(round(duration_seconds * 6))))
    elif duration_seconds <= 15:
        target = min(max_frames, max(30, int(round(duration_seconds * 4))))
    elif duration_seconds <= 30:
        target = min(max_frames, 60)
    elif duration_seconds <= 60:
        target = min(max_frames, 80)
    elif duration_seconds <= 180:
        target = max_frames
    else:
        target = max_frames
    fps = min(target / duration_seconds, MAX_FPS)
    target = min(max_frames, max(1, int(round(fps * duration_seconds))))
    return fps, target


def extract_uniform(
    video_path: str,
    out_dir: Path,
    fps: float,
    resolution: int = 512,
    max_frames: int = MAX_FRAMES,
    start_seconds: float | None = None,
    end_seconds: float | None = None,
) -> list[dict]:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH.")
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in out_dir.glob("frame_*.jpg"):
        f.unlink()

    output_pattern = str(out_dir / "frame_%04d.jpg")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if start_seconds is not None:
        cmd += ["-ss", f"{start_seconds:.3f}"]
    if end_seconds is not None:
        cmd += ["-to", f"{end_seconds:.3f}"]
    cmd += [
        "-i", str(Path(video_path).resolve()),
        "-vf", f"fps={fps},scale={resolution}:-2",
        "-frames:v", str(max_frames),
        "-q:v", "4",
        output_pattern,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg uniform extraction failed: {result.stderr.strip()}")

    offset = start_seconds or 0.0
    sorted_frames = sorted(out_dir.glob("frame_*.jpg"))
    return [
        {"index": i, "timestamp_seconds": round(offset + (i / fps if fps > 0 else 0.0), 2), "path": str(p)}
        for i, p in enumerate(sorted_frames)
    ]


def extract_scene_change(
    video_path: str,
    out_dir: Path,
    scene_threshold: float = SCENE_THRESHOLD,
    resolution: int = 512,
    max_frames: int = MAX_FRAMES,
    uniform_fallback_min: int = UNIFORM_FALLBACK_MIN,
    start_seconds: float | None = None,
    end_seconds: float | None = None,
) -> list[dict]:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH.")
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in out_dir.glob("frame_*.jpg"):
        f.unlink()

    select_expr = f"eq(n\\,0)+gt(scene\\,{scene_threshold})"
    vf = f"select='{select_expr}',metadata=mode=print:file=-,scale={resolution}:-2"
    output_pattern = str(out_dir / "frame_%04d.jpg")
    # Single-pass scene detection without frame limit, then subsample to max_frames
    meta = get_metadata(video_path)
    total_dur = meta["duration_seconds"]
    eff_start = start_seconds or 0.0
    eff_end = end_seconds or total_dur
    eff_duration = max(0.1, eff_end - eff_start)

    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if start_seconds is not None:
        cmd += ["-ss", f"{start_seconds:.3f}"]
    if end_seconds is not None:
        cmd += ["-to", f"{end_seconds:.3f}"]
    cmd += [
        "-i", str(Path(video_path).resolve()),
        "-vf", vf,
        "-vsync", "vfr",
        "-q:v", "4",
        output_pattern,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    pts_times: list[float] = []
    for stream in (result.stdout, result.stderr):
        for line in stream.splitlines():
            line = line.strip()
            if "pts_time" in line:
                for tok in line.split():
                    if tok.startswith("pts_time:") or tok.startswith("pts_time="):
                        try:
                            val = tok.split(":", 1)[1] if ":" in tok else tok.split("=", 1)[1]
                            pts_times.append(float(val))
                        except ValueError:
                            pass

    sorted_frames = sorted(out_dir.glob("frame_*.jpg"))

    if len(sorted_frames) >= uniform_fallback_min:
        offset = start_seconds or 0.0
        if len(pts_times) < len(sorted_frames):
            pts_times += [0.0] * (len(sorted_frames) - len(pts_times))

        # If we have more scene changes than max_frames, subsample evenly
        if len(sorted_frames) > max_frames:
            step = len(sorted_frames) / max_frames
            indices = [int(i * step) for i in range(max_frames)]
            indices = [min(i, len(sorted_frames) - 1) for i in indices]
            return [
                {"index": i, "timestamp_seconds": round(offset + pts_times[idx], 2),
                 "path": str(sorted_frames[idx]), "source": "scene-change"}
                for i, idx in enumerate(indices)
            ]

        return [
            {"index": i, "timestamp_seconds": round(offset + pts_times[i], 2), "path": str(p), "source": "scene-change"}
            for i, p in enumerate(sorted_frames)
        ]

    # Fallback: uniform sampling
    for f in out_dir.glob("frame_*.jpg"):
        f.unlink()
    fps, _ = auto_fps(eff_duration, max_frames=max_frames)
    return extract_uniform(
        video_path, out_dir, fps=fps, resolution=resolution,
        max_frames=max_frames, start_seconds=start_seconds, end_seconds=end_seconds,
    )


def _extract_at_pts(video_path: str, pts_list: list[float], out_dir: Path,
                    resolution: int = 512, offset: float = 0.0) -> list[dict]:
    """Extract one frame at each PTS timestamp using fast seeking."""
    frames: list[dict] = []
    for i, pts in enumerate(pts_list):
        out_path = out_dir / f"frame_{i + 1:04d}.jpg"
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{pts:.3f}",
            "-i", str(Path(video_path).resolve()),
            "-vf", f"scale={resolution}:-2",
            "-vframes", "1",
            "-q:v", "4",
            str(out_path),
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if out_path.exists():
            frames.append({
                "index": i,
                "timestamp_seconds": round(offset + pts, 2),
                "path": str(out_path),
                "source": "keyframe",
            })
    return frames


def extract_frames(
    video_path: str,
    out_dir: Path,
    use_scene_change: bool = True,
    fps: float | None = None,
    resolution: int = 512,
    max_frames: int = MAX_FRAMES,
    start_seconds: float | None = None,
    end_seconds: float | None = None,
) -> tuple[list[dict], str]:
    if fps is not None:
        frames = extract_uniform(video_path, out_dir, fps, resolution, max_frames, start_seconds, end_seconds)
        return frames, "uniform"

    if use_scene_change:
        frames = extract_scene_change(
            video_path, out_dir, resolution=resolution, max_frames=max_frames,
            start_seconds=start_seconds, end_seconds=end_seconds,
        )
        sampling = "scene-change" if frames and frames[0].get("source") == "scene-change" else "uniform-fallback"
        return frames, sampling

    meta = get_metadata(video_path)
    full_duration = meta["duration_seconds"]
    eff_start = start_seconds if start_seconds is not None else 0.0
    eff_end = end_seconds if end_seconds is not None else full_duration
    eff_duration = max(0.1, eff_end - eff_start)
    focused = start_seconds is not None or end_seconds is not None
    calc_fps, _ = auto_fps_focus(eff_duration, max_frames) if focused else auto_fps(eff_duration, max_frames)
    frames = extract_uniform(video_path, out_dir, calc_fps, resolution, max_frames, start_seconds, end_seconds)
    return frames, "uniform"
