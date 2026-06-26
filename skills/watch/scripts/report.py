"""Structured report generation for watch skill."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from diff_intelligence import build_diff_intelligence, get_row_diff


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
    gaps: list[str] | None = None,
    visual_descriptions: list[dict] | None = None,
    audio_path: str | None = None,
    captions: dict | None = None,
    diff_intelligence: dict | None = None,
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

    if gaps:
        report["watch_report"]["gaps"] = gaps

    scene_elements = build_scene_elements(frames, duration_seconds, transcript, visual_descriptions, audio_path, captions)
    report["scene_elements"] = scene_elements

    if diff_intelligence:
        report["diff_intelligence"] = diff_intelligence

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

    if captions:
        report["captions"] = {
            "source": captions.get("source", "unknown"),
            "segment_count": len(captions.get("segments", [])),
            "full_text_length": len(captions.get("full_text", "")),
            "segments": captions.get("segments", []),
        }
        if captions.get("alignment"):
            report["captions"]["alignment"] = captions["alignment"]

    if scenes:
        report["scenes"] = {
            "match_count": len(scenes),
            "matches": scenes,
        }

    if emotion_analysis:
        report["emotion_analysis"] = emotion_analysis

    if visual_descriptions is not None:
        report["visual_descriptions"] = visual_descriptions

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
    gaps: list[str] | None = None,
    visual_descriptions: list[dict] | None = None,
    audio_path: str | None = None,
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
    if gaps:
        lines.append(f"- **Gaps:** {', '.join(gaps)}")
    lines.append("")

    scene_elements = build_scene_elements(frames, duration_seconds, transcript, visual_descriptions, audio_path)
    if scene_elements:
        lines.append("## Scene Element Table")
        lines.append("")
        lines.append("| Timecode | Text | Scene marker image | Movie segment | Sound |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in scene_elements:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md_cell(row["timecode"]),
                        _md_cell(row["text"]),
                        _md_cell(row["scene_marker_image"]),
                        _md_cell(row["movie_segment"]),
                        _md_cell(row["sound"]),
                    ]
                )
                + " |"
            )
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


def write_html_report(
    out_path: Path,
    source: str,
    title: str,
    duration_seconds: float,
    sampling_mode: str,
    frames: list[dict],
    transcript: dict | None = None,
    scenes: list[dict] | None = None,
    emotion_analysis: dict | None = None,
    captions: dict | None = None,
    focused_range: str | None = None,
    gaps: list[str] | None = None,
    visual_descriptions: list[dict] | None = None,
    audio_path: str | None = None,
    diff_intelligence: dict | None = None,
) -> Path:
    """Write a self-contained inspection page for scene evidence."""
    rows = build_scene_elements(frames, duration_seconds, transcript, visual_descriptions, audio_path, captions)
    css = """
body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:0;background:#f7f7f4;color:#1f2328}
main{max-width:1500px;margin:0 auto;padding:24px}
h1{font-size:24px;margin:0 0 12px}
.meta{display:flex;gap:14px;flex-wrap:wrap;margin:0 0 18px;color:#4b5563;font-size:14px}
.gaps{border:1px solid #c2410c;background:#fff7ed;color:#7c2d12;padding:10px 12px;margin:0 0 18px}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #d0d7de}
th,td{border:1px solid #d0d7de;padding:8px;vertical-align:top;font-size:13px}
th{background:#eef2f7;text-align:left;position:sticky;top:0}
img{width:180px;max-width:20vw;height:auto;display:block;border:1px solid #d0d7de;background:#eee}
video{width:220px;max-width:22vw;display:block}
audio{width:220px;max-width:22vw}
.path{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px;color:#57606a;overflow-wrap:anywhere;margin-top:4px}
.status{font-weight:600}
.missing{color:#9a3412}
.ok{color:#166534}
.evidence{border:1px solid #d0d7de;background:#fff;margin:0 0 18px;padding:10px 12px;font-size:13px}
.evidence div{margin:4px 0}
"""
    lines = [
        "<!doctype html>",
        "<meta charset=\"utf-8\">",
        f"<title>{escape(title)} Watch Report</title>",
        f"<style>{css}</style>",
        "<main>",
        f"<h1>{escape(title)}</h1>",
        "<div class=\"meta\">",
        f"<span>Source: <code>{escape(source)}</code></span>",
        f"<span>Duration: {_format_duration(duration_seconds)}</span>",
        f"<span>Sampling: {escape(sampling_mode)}</span>",
        f"<span>Frames: {len(frames)}</span>",
        f"<span>English SRT: {_source_summary(captions, 'missing')}</span>",
        f"<span>Open-Whisper: {_source_summary(transcript, 'missing')}</span>",
    ]
    if focused_range:
        lines.append(f"<span>Focus: {escape(focused_range)}</span>")
    lines.append("</div>")
    lines.append("<div class=\"evidence\">")
    lines.append(f"<div><strong>English SRT sample:</strong> {escape(_first_segment_text(captions))}</div>")
    lines.append(f"<div><strong>Open-Whisper sample:</strong> {escape(_first_segment_text(transcript))}</div>")
    lines.append("</div>")
    if gaps:
        lines.append(f"<div class=\"gaps\">Gaps: {escape(', '.join(gaps))}</div>")
    if diff_intelligence and diff_intelligence.get("overall_diff_percentage", 0) > 0:
        di = diff_intelligence
        cc = di.get("category_counts", {})
        lines.append("<div class=\"evidence\" style=\"border-left:3px solid #c2410c\">")
        lines.append("<div style=\"font-weight:700;margin-bottom:6px\">Forensic Insights — SRT vs Whisper Divergence</div>")
        lines.append(f"<div><strong>Overall diff:</strong> {di.get('overall_diff_percentage')}% of rows differ</div>")
        if cc.get("sanitized"):
            lines.append(f"<div>🔴 <strong>Sanitized:</strong> {cc['sanitized']} scene(s) — SRT may tone down raw language</div>")
        if cc.get("hidden_dialogue"):
            lines.append(f"<div>🟡 <strong>Hidden Dialogue:</strong> {cc['hidden_dialogue']} scene(s) — Whisper catches dialogue SRT omits</div>")
        if cc.get("acoustic_context"):
            lines.append(f"<div>🔵 <strong>Acoustic Context:</strong> {cc['acoustic_context']} scene(s) — SRT captures environmental cues Whisper missed</div>")
        if cc.get("unknown_diff"):
            lines.append(f"<div>⚪ <strong>Unclassified:</strong> {cc['unknown_diff']} scene(s) — may warrant manual review</div>")
        for takeaway in di.get("takeaways", []):
            lines.append(f"<div style=\"margin-top:4px;color:#4b5563;font-style:italic\">{escape(takeaway)}</div>")
        lines.append("</div>")
    lines.extend([
        "<table>",
        "<thead><tr><th>Timecode</th><th>English SRT / Captions</th><th>Open-Whisper Transcript</th><th>Scene Marker</th><th>Visual Evidence</th><th>Movie Segment</th><th>Sound</th></tr></thead>",
        "<tbody>",
    ])
    for row in rows:
        img_path = row.get("scene_marker_image_path", "")
        visual_status = row.get("visual_description_status", "not_analyzed")
        status_class = "ok" if visual_status == "described" else "missing"
        segment = row.get("movie_segment", "")
        start, end = _split_segment(segment)
        video_src = row.get("video_clip_path") or (f"{source}#t={start},{end}" if _is_local_media(source) else "")
        audio_src = row.get("audio_clip_path") or (f"{audio_path}#t={start},{end}" if audio_path else "")
        audio_wav_src = row.get("audio_wav_clip_path", "")
        lines.extend([
            "<tr>",
            f"<td>{escape(row.get('timecode', ''))}</td>",
            f"<td>{_caption_cell(captions, row.get('srt_text', ''))}</td>",
            f"<td>{_whisper_cell(transcript, row.get('text', ''))}</td>",
            "<td>",
            f"<img src=\"{escape(img_path)}\" alt=\"scene marker at {escape(row.get('timecode', ''))}\">" if img_path else "",
            f"<div class=\"path\">{escape(img_path)}</div>",
            "</td>",
            "<td>",
            f"<div class=\"status {status_class}\">{escape(visual_status)}</div>",
            f"<div>{escape(row.get('visual_description', ''))}</div>",
            f"<div class=\"path\">source: {escape(row.get('visual_description_source', 'none'))}</div>",
            "</td>",
            "<td>",
            f"<div>{escape(segment)}</div>",
            _video_player(video_src) if video_src else "<div class=\"missing\">video segment not playable from this source</div>",
            f"<div class=\"path\">{escape(video_src)}</div>" if video_src else "",
            "</td>",
            "<td>",
            _audio_player(audio_src, audio_wav_src) if (audio_src or audio_wav_src) else "<div class=\"missing\">audio clip not playable from this source</div>",
            f"<div>{escape(row.get('sound', ''))}</div>",
            f"<div class=\"path\">playable clip: <a href=\"{escape(audio_src)}\">{escape(audio_src)}</a></div>" if audio_src else "",
            f"<div class=\"path\">wav fallback: <a href=\"{escape(audio_wav_src)}\">{escape(audio_wav_src)}</a></div>" if audio_wav_src else "",
            f"<div class=\"path\">source extraction: {escape(row.get('audio_path', ''))}</div>" if row.get("audio_path") else "",
            "</td>",
            "</tr>",
        ])
    lines.extend(["</tbody></table>", "</main>"])
    out_path.write_text("\n".join(lines))
    return out_path


def _caption_cell(captions: dict | None, text: str) -> str:
    source = str((captions or {}).get("source", "")).lower()
    if "caption" in source or "srt" in source or "subtitle" in source:
        return (
            f"{escape(text)}<div class=\"path\">source: {escape((captions or {}).get('source', 'srt'))}"
            f"{_alignment_suffix(captions)}</div>"
        )
    return '<span class="missing">No English SRT/caption evidence for this row</span>'


def _whisper_cell(transcript: dict | None, text: str) -> str:
    source = str((transcript or {}).get("source", ""))
    if "whisper" in source.lower():
        return f"{escape(text)}<div class=\"path\">source: {escape(source)}</div>"
    return '<span class="missing">No Open-Whisper transcript for this row</span>'


def _video_player(src: str) -> str:
    media_type = _media_type(src, "video/mp4")
    safe_src = escape(src)
    return f'<video controls preload="metadata"><source src="{safe_src}" type="{media_type}"></video>'


def _audio_player(src: str, fallback_src: str = "") -> str:
    sources = []
    if src:
        sources.append(f'<source src="{escape(src)}" type="{_media_type(src, "audio/mpeg")}">')
    if fallback_src:
        sources.append(f'<source src="{escape(fallback_src)}" type="{_media_type(fallback_src, "audio/wav")}">')
    return f'<audio controls preload="metadata">{"".join(sources)}</audio>'


def _media_type(src: str, fallback: str) -> str:
    suffix = Path(src.split("#", 1)[0]).suffix.lower()
    if suffix == ".mp4":
        return "video/mp4"
    if suffix == ".m4a":
        return "audio/mp4"
    if suffix == ".mp3":
        return "audio/mpeg"
    if suffix == ".wav":
        return "audio/wav"
    if suffix == ".webm":
        return "video/webm"
    return fallback


def _source_summary(source_doc: dict | None, missing_label: str) -> str:
    if not source_doc or not source_doc.get("segments"):
        return f'<span class="missing">{escape(missing_label)}</span>'
    source = escape(str(source_doc.get("source", "unknown")))
    count = len(source_doc.get("segments", []))
    return f'<span class="ok">{source} ({count} segments){_alignment_suffix(source_doc)}</span>'


def _alignment_suffix(source_doc: dict | None) -> str:
    alignment = (source_doc or {}).get("alignment") or {}
    if alignment.get("status") != "shifted":
        return ""
    offset = alignment.get("offset_seconds")
    matches = alignment.get("match_count")
    return f" [time-shifted {escape(str(offset))}s vs {escape(str(alignment.get('reference_source', 'reference')))}, {escape(str(matches))} matches]"


def _first_segment_text(source_doc: dict | None) -> str:
    for segment in (source_doc or {}).get("segments", []):
        text = str(segment.get("text", "")).strip()
        if text:
            start = _format_ts(float(segment.get("start", 0.0)))
            return _truncate(f"[{start}] {text}", 180)
    return "missing"


def write_frames_manifest(frames: list[dict], out_path: Path, **extra) -> Path:
    manifest = dict(extra)
    manifest["frame_count"] = len(frames)
    manifest["frames"] = frames
    out_path.write_text(json.dumps(manifest, indent=2))
    return out_path


def _split_segment(segment: str) -> tuple[str, str]:
    if "-" not in segment:
        return "0", ""
    start, end = segment.split("-", 1)
    return str(_ts_to_seconds(start)), str(_ts_to_seconds(end))


def _ts_to_seconds(value: str) -> int:
    parts = [int(p) for p in value.strip().split(":") if p.isdigit()]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 1:
        return parts[0]
    return 0


def _is_local_media(source: str) -> bool:
    return bool(source) and not source.startswith(("http://", "https://"))


def build_scene_elements(
    frames: list[dict],
    duration_seconds: float,
    transcript: dict | None = None,
    visual_descriptions: list[dict] | None = None,
    audio_path: str | None = None,
    captions: dict | None = None,
) -> list[dict]:
    """Build scene-by-scene rows aligned to sampled frame timestamps."""
    if not frames:
        return []

    visual_by_index = _visual_by_index(visual_descriptions)
    timestamps = [float(f.get("timestamp_seconds", 0.0)) for f in frames]
    rows = []
    for index, frame in enumerate(frames):
        start = timestamps[index]
        next_start = timestamps[index + 1] if index + 1 < len(timestamps) else duration_seconds
        end = max(start, next_start)
        text = _text_for_segment(transcript, start, end)
        srt_text = _text_for_segment(captions, start, end)
        visual = visual_by_index.get(int(frame.get("index", index)))
        image_path = str(frame.get("path", ""))
        visual_description = str(visual.get("description", "")).strip() if visual else ""
        visual_status = "described" if visual_description else "not_analyzed"
        image_cell = image_path
        if visual_description:
            image_cell = f"{image_path} — {visual_description}"
        else:
            image_cell = f"{image_path} — visual description not analyzed"
        rows.append(
            {
                "index": int(frame.get("index", index)),
                "timecode": _format_ts(start),
                "text": text,
                "srt_text": srt_text,
                "scene_marker_image": image_cell,
                "scene_marker_image_path": image_path,
                "video_clip_path": str(frame.get("video_clip_path", "")),
                "audio_clip_path": str(frame.get("audio_clip_path", "")),
                "audio_wav_clip_path": str(frame.get("audio_wav_clip_path", "")),
                "visual_description": visual_description or "not_analyzed",
                "visual_description_source": visual.get("source", "none") if visual else "none",
                "visual_description_status": visual_status,
                "movie_segment": f"{_format_ts(start)}-{_format_ts(end)}",
                "sound": _sound_for_segment(transcript, start, end, audio_path),
                "audio_path": audio_path or "",
                "sound_description_source": "transcript" if transcript and transcript.get("segments") else "none",
            }
        )
    diff_info = get_row_diff  # ensure module is importable at runtime
    for row in rows:
        diff = get_row_diff(row)
        if diff:
            row["diff_info"] = diff
    return rows


def _visual_by_index(visual_descriptions: list[dict] | None) -> dict[int, dict]:
    by_index: dict[int, dict] = {}
    for item in visual_descriptions or []:
        try:
            by_index[int(item.get("index", -1))] = item
        except (TypeError, ValueError):
            continue
    return by_index


def _text_for_segment(transcript: dict | None, start: float, end: float) -> str:
    if not transcript or not transcript.get("segments"):
        return "No transcript available"
    texts = []
    for segment in transcript.get("segments", []):
        seg_start = float(segment.get("start", 0.0))
        seg_end = seg_start + float(segment.get("duration", 0.0))
        if seg_end >= start and seg_start <= end:
            text = str(segment.get("text", "")).strip()
            if text:
                texts.append(text)
    return _truncate(" ".join(texts), 220) if texts else "No transcript in this segment"


def _sound_for_segment(transcript: dict | None, start: float, end: float, audio_path: str | None = None) -> str:
    if not transcript or not transcript.get("segments"):
        return "Sound not transcribed; audio not analyzed"
    if _text_for_segment(transcript, start, end).startswith("No transcript"):
        return "No speech captured; soundtrack not analyzed"
    return f"Speech/dialogue from {transcript.get('source', 'transcript')}; soundtrack not analyzed"


def _truncate(value: str, limit: int) -> str:
    value = " ".join(value.split())
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "..."


def _md_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


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
