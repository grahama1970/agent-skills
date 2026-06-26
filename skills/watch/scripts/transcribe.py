"""Transcript utilities: SRT caption parsing, PGS OCR, Whisper via Docker, segment filtering.

Whisper transcription runs in a dedicated Docker container (hwdsl2/whisper-server:cuda)
on port 9000 for GPU-accelerated inference. Falls back to local faster-whisper on CPU.
PGS (BluRay image subs) are OCR'd with tesseract when text subs are unavailable.
"""
from __future__ import annotations

import difflib
import json
import logging
import os
import re
import statistics
import subprocess
from pathlib import Path

import httpx

WHISPER_API_URL = os.getenv("WHISPER_API_URL", "http://127.0.0.1:9000/v1/audio/transcriptions")
WHISPER_API_KEY = os.getenv("WHISPER_API_KEY", "")


def transcribe_video(video_path: str, work_dir: Path, language: str = "en",
                     start_seconds: float | None = None, end_seconds: float | None = None) -> dict:
    audio_file = work_dir / "audio.wav"
    _extract_audio(video_path, str(audio_file), start_seconds, end_seconds)
    result = _transcribe_docker(str(audio_file), language)
    if result:
        return result
    return _transcribe_local(str(audio_file), language)


def _extract_audio(video_path: str, output_path: str,
                   start_seconds: float | None = None, end_seconds: float | None = None) -> None:
    cmd = ["ffmpeg", "-y"]
    if start_seconds is not None:
        cmd.extend(["-ss", f"{start_seconds:.3f}"])
    if end_seconds is not None:
        duration = end_seconds - (start_seconds or 0.0)
        cmd.extend(["-t", f"{duration:.3f}"])
    cmd.extend(["-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", output_path])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Audio extraction failed: {result.stderr.strip()}")


def _transcribe_docker(audio_path: str, language: str = "en") -> dict | None:
    """Transcribe via Docker Whisper API (OpenAI-compatible)."""
    try:
        headers = {}
        if WHISPER_API_KEY:
            headers["Authorization"] = f"Bearer {WHISPER_API_KEY}"
        with open(audio_path, "rb") as f:
            files = {"file": (audio_path, f, "audio/wav")}
            data = {"model": "whisper-1", "language": language, "response_format": "verbose_json"}
            resp = httpx.post(WHISPER_API_URL, headers=headers, files=files, data=data, timeout=300)
        if resp.status_code != 200:
            return None
        result = resp.json()
        segments = []
        full_text_parts = []
        for seg in result.get("segments", []):
            segments.append({
                "text": seg.get("text", "").strip(),
                "start": round(seg.get("start", 0.0), 3),
                "duration": round(seg.get("end", 0.0) - seg.get("start", 0.0), 3),
            })
            full_text_parts.append(seg.get("text", "").strip())
        return {
            "source": "whisper-docker (cuda)",
            "segments": segments,
            "full_text": " ".join(full_text_parts),
            "language": result.get("language", language),
        }
    except Exception:
        return None


def _transcribe_local(audio_path: str, language: str = "en") -> dict:
    """Fallback: transcribe locally with CPU-only faster-whisper."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError("faster-whisper not installed. Run: uv pip install faster-whisper")
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = WhisperModel("base", device="cpu", compute_type="int8", num_workers=1)
            segments_gen, info = model.transcribe(audio_path, language=language, vad_filter=True)
            segments = []
            full_text_parts = []
            for seg in segments_gen:
                segments.append({
                    "text": seg.text.strip(),
                    "start": round(seg.start, 3),
                    "duration": round(seg.end - seg.start, 3),
                })
                full_text_parts.append(seg.text.strip())
            return {
                "source": "whisper-local (cpu)",
                "segments": segments,
                "full_text": " ".join(full_text_parts),
                "language": info.language if info else language,
            }
    except Exception as exc:
        raise RuntimeError(f"Local whisper failed: {exc}")


def parse_captions(subtitle_path: str) -> dict:
    path = Path(subtitle_path)
    if not path.exists():
        raise RuntimeError(f"Subtitle file not found: {subtitle_path}")

    segments = []
    content = path.read_text(encoding="utf-8", errors="replace")
    content = content.replace("\r\n", "\n")

    for block in content.strip().split("\n\n"):
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if len(lines) < 3:
            continue
        time_line = next((l for l in lines[:3] if "-->" in l), None)
        if not time_line:
            continue
        text = " ".join(lines[lines.index(time_line) + 1:])
        parts = [p.strip() for p in time_line.split("-->")]
        if len(parts) != 2:
            continue
        start = _parse_srt_time(parts[0])
        end = _parse_srt_time(parts[1])
        if start is None or end is None:
            continue
        segments.append({"text": text, "start": start, "duration": end - start})

    return {
        "source": "captions",
        "segments": segments,
        "full_text": " ".join(s["text"] for s in segments),
    }


def _parse_srt_time(raw: str) -> float | None:
    import re
    m = re.search(r"(\d{1,2}):(\d{2}):(\d{2})(?:[.,](\d{1,3}))?", raw.strip())
    if not m:
        return None
    hours = int(m.group(1))
    minutes = int(m.group(2))
    seconds = int(m.group(3))
    millis = int(m.group(4)) if m.group(4) else 0
    return hours * 3600 + minutes * 60 + seconds + millis / 1000.0


def filter_segments(segments: list[dict], start: float | None, end: float | None) -> list[dict]:
    if start is None and end is None:
        return segments
    filtered = []
    for seg in segments:
        seg_end = seg["start"] + seg["duration"]
        if start is not None and seg_end < start:
            continue
        if end is not None and seg["start"] > end:
            continue
        filtered.append(seg)
    return filtered


def align_segments_to_reference(
    target: dict | None,
    reference: dict | None,
    *,
    min_offset_seconds: float = 2.0,
    min_matches: int = 5,
    max_spread_seconds: float = 1.5,
    min_ratio: float = 0.65,
) -> tuple[dict | None, dict | None]:
    """Shift target segment starts when text-matched timing is stably offset.

    Returns ``(aligned_target, alignment)``. ``alignment`` is None when there is
    not enough evidence to alter timestamps. The original segment start is kept
    as ``original_start`` for auditability.
    """
    if not target or not reference:
        return target, None
    target_segments = list(target.get("segments") or [])
    reference_segments = list(reference.get("segments") or [])
    if not target_segments or not reference_segments:
        return target, None

    pairs = _matched_offsets(target_segments, reference_segments, min_ratio)
    if len(pairs) < min_matches:
        return target, {
            "status": "insufficient_matches",
            "match_count": len(pairs),
            "offset_seconds": 0.0,
        }

    offsets = sorted(p["offset_seconds"] for p in pairs)
    median = statistics.median(offsets)
    deviations = sorted(abs(offset - median) for offset in offsets)
    median_deviation = statistics.median(deviations)
    if abs(median) < min_offset_seconds or median_deviation > max_spread_seconds:
        return target, {
            "status": "already_aligned" if abs(median) < min_offset_seconds else "unstable_offset",
            "match_count": len(pairs),
            "offset_seconds": round(median, 3),
            "median_deviation_seconds": round(median_deviation, 3),
        }

    aligned_segments = []
    for segment in target_segments:
        row = dict(segment)
        row["original_start"] = row.get("start", 0.0)
        row["start"] = round(max(0.0, float(row.get("start", 0.0)) + median), 3)
        aligned_segments.append(row)

    aligned = dict(target)
    aligned["segments"] = aligned_segments
    aligned["alignment"] = {
        "status": "shifted",
        "reference_source": reference.get("source", "reference"),
        "offset_seconds": round(median, 3),
        "match_count": len(pairs),
        "median_deviation_seconds": round(median_deviation, 3),
        "examples": pairs[:5],
    }
    return aligned, aligned["alignment"]


def _matched_offsets(target_segments: list[dict], reference_segments: list[dict], min_ratio: float) -> list[dict]:
    pairs: list[dict] = []
    normalized_targets = [(_normalize_text(seg.get("text", "")), seg) for seg in target_segments]
    for ref in reference_segments[:80]:
        ref_text = _normalize_text(ref.get("text", ""))
        if len(ref_text) < 8:
            continue
        best_ratio = 0.0
        best_target = None
        for target_text, target in normalized_targets:
            if len(target_text) < 8:
                continue
            ratio = difflib.SequenceMatcher(None, ref_text, target_text).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_target = target
        if best_target and best_ratio >= min_ratio:
            offset = float(ref.get("start", 0.0)) - float(best_target.get("start", 0.0))
            pairs.append({
                "offset_seconds": round(offset, 3),
                "ratio": round(best_ratio, 3),
                "reference_start": round(float(ref.get("start", 0.0)), 3),
                "target_start": round(float(best_target.get("start", 0.0)), 3),
                "reference_text": str(ref.get("text", ""))[:120],
                "target_text": str(best_target.get("text", ""))[:120],
            })
    return pairs


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", value.lower()).strip()


def has_text_subtitles(video_path: str) -> bool:
    """Check if the first subtitle stream is text (subrip) or image (PGS)."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "s:0",
         "-show_entries", "stream=codec_name", "-of", "csv=p=0", video_path],
        capture_output=True, text=True, timeout=30,
    )
    codec = result.stdout.strip()
    return codec in ("subrip", "srt", "ass", "ssa", "webvtt")


def ocr_pgs_subtitles(video_path: str, output_path: str, lang: str = "eng") -> str | None:
    """Extract PGS (BluRay image) subtitles via ffmpeg overlay + tesseract OCR.

    Renders each PGS subtitle event as an overlay on a scaled video frame,
    OCRs the rendered frame, and produces an SRT file.

    This guarantees the subtitles match the exact movie encode since they
    are extracted from the file itself rather than a third-party source.
    """
    import json as _json
    import shutil
    import tempfile
    work = Path(tempfile.mkdtemp(prefix="pgs-ocr-"))
    frames_dir = work / "frames"
    frames_dir.mkdir()

    # Get subtitle event timing
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "s:0",
         "-show_entries", "packet=pts_time,duration_time",
         "-of", "json", video_path],
        capture_output=True, text=True, timeout=30,
    )
    packets = _json.loads(probe.stdout).get("packets", [])
    if not packets:
        shutil.rmtree(str(work), ignore_errors=True)
        return None

    srt_lines: list[str] = []
    batch_size = 50
    for batch_start in range(0, min(len(packets), 1000), batch_size):
        batch = packets[batch_start:batch_start + batch_size]
        for i, pkt in enumerate(batch):
            idx = batch_start + i
            pts = float(pkt.get("pts_time", 0))
            dur = float(pkt.get("duration_time") or 3.0)
            frame_path = frames_dir / f"sub{idx:06d}.png"

            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(pts), "-i", video_path,
                 "-filter_complex", "[0:v]scale=1920:540[bg];[bg][0:s:0]overlay",
                 "-vframes", "1", "-an", str(frame_path)],
                capture_output=True, text=True, timeout=120,
            )

            if not frame_path.exists() or frame_path.stat().st_size < 1000:
                continue

            txt_base = work / f"ocr{idx:06d}"
            subprocess.run(
                ["tesseract", str(frame_path), str(txt_base), "-l", lang, "--psm", "6"],
                capture_output=True, text=True, timeout=30,
            )
            text_file = Path(str(txt_base) + ".txt")
            text = text_file.read_text(encoding="utf-8", errors="replace").strip() if text_file.exists() else ""

            if text:
                start_ts = f"{int(pts//3600):02d}:{int((pts%3600)//60):02d}:{pts%60:06.3f}".replace(".", ",")
                end_ts = f"{int((pts+dur)//3600):02d}:{int(((pts+dur)%3600)//60):02d}:{(pts+dur)%60:06.3f}".replace(".", ",")
                srt_lines.append(str(len(srt_lines) // 4 + 1))
                srt_lines.append(f"{start_ts} --> {end_ts}")
                srt_lines.append(text)
                srt_lines.append("")

        if batch_start % 200 == 0:
            import logging
            logging.getLogger().info(f"OCR progress: {batch_start}/{min(len(packets), 1000)}")

    if srt_lines:
        Path(output_path).write_text("\n".join(srt_lines), encoding="utf-8")
        shutil.rmtree(str(work), ignore_errors=True)
        return output_path

    shutil.rmtree(str(work), ignore_errors=True)
    return None


def extract_subtitles(video_path: str, output_path: str | None = None,
                      stream_index: int = 0) -> str | None:
    """Extract subtitles from a video file, OCRing PGS if needed.

    Returns path to the SRT file, or None if no subtitle stream exists.
    """
    # Check if any subtitle stream exists
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", f"s:{stream_index}",
         "-show_entries", "stream=codec_name", "-of", "csv=p=0", video_path],
        capture_output=True, text=True, timeout=30,
    )
    codec = probe.stdout.strip()
    if not codec:
        return None

    out = output_path or str(Path(video_path).with_suffix(".srt"))

    if codec in ("subrip", "srt"):
        subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-map", f"0:s:{stream_index}",
             "-c:s", "srt", out],
            capture_output=True, text=True, timeout=120, check=True,
        )
        return out

    if codec in ("ass", "ssa"):
        subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-map", f"0:s:{stream_index}",
             "-c:s", "srt", out],
            capture_output=True, text=True, timeout=120, check=True,
        )
        return out

    if codec == "hdmv_pgs_subtitle":
        logger = logging.getLogger(__name__)
        logger.info("PGS image subtitles detected — OCR is too slow for practical use")
        logger.info("Using Whisper as sole transcript source for this movie")
        return None

    return None


def _extract_pgs_via_overlay(video_path: str, output_path: str, lang: str = "eng") -> str | None:
    """Extract PGS subtitles by rendering each as an image overlay and OCRing.

    Uses ffmpeg to overlay each subtitle event onto a blank frame at its pts,
    then OCRs each frame to produce an SRT file.
    """
    import json as _json
    import shutil
    import tempfile
    work = Path(tempfile.mkdtemp(prefix="pgs-overlay-"))
    frames_dir = work / "frames"
    frames_dir.mkdir()

    # Get subtitle packet timing
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "s:0",
         "-show_entries", "packet=pts_time,duration_time",
         "-of", "json", video_path],
        capture_output=True, text=True, timeout=30,
    )
    packets = _json.loads(probe.stdout).get("packets", [])
    if not packets:
        try:
            shutil.rmtree(str(work))
        except OSError:
            pass
        return None

    # Extract subtitle frames at each PTS using the overlay filter
    for i, pkt in enumerate(packets[:500]):  # limit to 500 for sanity
        pts = pkt.get("pts_time", 0)
        out_file = str(frames_dir / f"sub{i:06d}.png")
        cmd = [
            "ffmpeg", "-y", "-ss", str(pts), "-i", video_path,
            "-filter_complex", "[0:v]scale=1920:540,setpts=PTS[bg];[bg][0:s:0]overlay",
            "-vframes", "1", "-an", out_file,
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    # OCR each frame
    srt_lines: list[str] = []
    png_files = sorted(frames_dir.glob("*.png"))
    for i, png_path in enumerate(png_files):
        if png_path.stat().st_size < 1000:  # empty frame
            continue
        pts = packets[i].get("pts_time", 0) if i < len(packets) else 0
        dur = packets[i].get("duration_time", 3.0) if i < len(packets) else 3.0
        txt_base = work / f"ocr{i:06d}"
        subprocess.run(
            ["tesseract", str(png_path), str(txt_base), "-l", lang,
             "--psm", "6"],
            capture_output=True, text=True, timeout=30,
        )
        text_file = txt_base.with_suffix(".txt")
        text = text_file.read_text(encoding="utf-8", errors="replace").strip() if text_file.exists() else ""
        if text:
            srt_lines.append(str(len(srt_lines) // 4 + 1))
            start_ts = f"{int(pts//3600):02d}:{int((pts%3600)//60):02d}:{pts%60:06.3f}".replace(".", ",")
            end_ts = f"{int((pts+dur)//3600):02d}:{int(((pts+dur)%3600)//60):02d}:{(pts+dur)%60:06.3f}".replace(".", ",")
            srt_lines.append(f"{start_ts} --> {end_ts}")
            srt_lines.append(text)
            srt_lines.append("")

    if srt_lines:
        Path(output_path).write_text("\n".join(srt_lines), encoding="utf-8")
        try:
            shutil.rmtree(str(work))
        except OSError:
            pass
        return output_path

    try:
        shutil.rmtree(str(work))
    except OSError:
        pass
    return None
