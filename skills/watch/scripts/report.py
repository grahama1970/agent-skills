"""Structured report generation for watch skill."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def write_report(
    out_path: Path,
    source: str,
    title: str,
    duration_seconds: float,
    sampling_mode: str,
    frames: list[dict],
    transcript: dict | None = None,
    scenes: list[dict] | None = None,
    emotion_analysis: dict | None = None,
    metadata: dict | None = None,
) -> Path:
    report = {
        "watch_report": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "title": title,
            "duration_seconds": duration_seconds,
            "duration_formatted": _format_duration(duration_seconds),
            "sampling_mode": sampling_mode,
            "frame_count": len(frames),
        }
    }

    if metadata:
        report["watch_report"]["metadata"] = metadata

    report["frames"] = [
        {
            "index": f["index"],
            "timestamp_seconds": f["timestamp_seconds"],
            "timestamp_formatted": _format_ts(f["timestamp_seconds"]),
            "path": f["path"],
            "source": f.get("source", sampling_mode),
        }
        for f in frames
    ]

    if transcript:
        report["transcript"] = {
            "source": transcript.get("source", "unknown"),
            "segment_count": len(transcript.get("segments", [])),
            "full_text_length": len(transcript.get("full_text", "")),
            "segments": transcript.get("segments", []),
        }

    if scenes:
        report["scenes"] = {
            "match_count": len(scenes),
            "matches": scenes,
        }

    if emotion_analysis:
        report["emotion_analysis"] = emotion_analysis

    out_path.write_text(json.dumps(report, indent=2))
    return out_path


def write_markdown_report(
    out_path: Path,
    source: str,
    title: str,
    duration_seconds: float,
    sampling_mode: str,
    frames: list[dict],
    transcript: dict | None = None,
    scenes: list[dict] | None = None,
    emotion_analysis: dict | None = None,
    focused_range: str | None = None,
) -> Path:
    lines = []

    lines.append(f"# Watch Report: {title}")
    lines.append("")
    lines.append(f"- **Source:** {source}")
    lines.append(f"- **Duration:** {_format_duration(duration_seconds)}")
    lines.append(f"- **Sampling mode:** {sampling_mode}")
    lines.append(f"- **Frames extracted:** {len(frames)}")
    if focused_range:
        lines.append(f"- **Focus range:** {focused_range}")
    lines.append("")

    if frames:
        lines.append("## Frames")
        lines.append("")
        lines.append("Read each frame with the Read tool:")
        lines.append("")
        for f in frames:
            ts = _format_ts(f["timestamp_seconds"])
            lines.append(f"- `{f['path']}` (t={ts})")
        lines.append("")

    if transcript and transcript.get("segments"):
        lines.append("## Transcript")
        lines.append("")
        lines.append(f"_Source: {transcript.get('source', 'unknown')}_")
        lines.append("")
        lines.append("```")
        for seg in transcript["segments"]:
            ts = _format_ts(seg["start"])
            lines.append(f"[{ts}] {seg['text']}")
        lines.append("```")
        lines.append("")

    if emotion_analysis:
        lines.append("## Emotion Analysis")
        lines.append("")
        for emotion, count in emotion_analysis.get("emotion_counts", {}).items():
            lines.append(f"- **{emotion}:** {count} occurrences")
        if emotion_analysis.get("tag_counts"):
            lines.append("")
            lines.append("### Tags Found")
            lines.append("")
            for tag, count in emotion_analysis["tag_counts"].items():
                lines.append(f"- `{tag}`: {count}")
        lines.append("")

    if scenes:
        lines.append("## Matched Scenes")
        lines.append("")
        for i, s in enumerate(scenes, 1):
            start_ts = _format_ts(s["start"])
            end_ts = _format_ts(s["end"])
            lines.append(f"### Scene {i} [{start_ts} → {end_ts}]")
            lines.append("")
            lines.append(f"**Text:** {s.get('text', '')[:200]}")
            if s.get("tags"):
                lines.append(f"**Tags:** {', '.join(s['tags'])}")
            lines.append("")

    lines.append("---")
    lines.append(f"_Report generated: {datetime.now(timezone.utc).isoformat()}_")
    lines.append("")

    out_path.write_text("\n".join(lines))
    return out_path


def write_frames_manifest(frames: list[dict], out_path: Path, **extra) -> Path:
    manifest = dict(extra)
    manifest["frame_count"] = len(frames)
    manifest["frames"] = frames
    out_path.write_text(json.dumps(manifest, indent=2))
    return out_path


def _format_duration(seconds: float) -> str:
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, sec = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m {sec}s"
    if minutes:
        return f"{minutes}m {sec}s"
    return f"{sec}s"


def _format_ts(seconds: float) -> str:
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, sec = divmod(rem, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"
