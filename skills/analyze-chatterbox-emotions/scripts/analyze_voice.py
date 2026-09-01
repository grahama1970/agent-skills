#!/usr/bin/env python3
"""Chatterbox voice-quality evaluator.

This script treats emotion as an artifact-quality target. It does not infer a
speaker's real emotional state.
"""
from __future__ import annotations

import argparse
import difflib
import json
import math
import os
import statistics
import subprocess
import tempfile
import wave
from array import array
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "analyze_chatterbox_emotions.voice_eval.v1"
TARGET_PROFILES: dict[str, dict[str, float]] = {
    "neutral": {"arousal": 0.35, "valence": 0.0},
    "warm": {"arousal": 0.35, "valence": 0.45},
    "friendly": {"arousal": 0.45, "valence": 0.55},
    "happy": {"arousal": 0.65, "valence": 0.75},
    "sad": {"arousal": 0.25, "valence": -0.65},
    "angry": {"arousal": 0.85, "valence": -0.65},
    "fearful": {"arousal": 0.75, "valence": -0.55},
    "serious": {"arousal": 0.45, "valence": -0.1},
    "reassuring": {"arousal": 0.32, "valence": 0.45},
    "excited": {"arousal": 0.85, "valence": 0.65},
    "tender": {"arousal": 0.28, "valence": 0.25},
    "guarded": {"arousal": 0.42, "valence": -0.15},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_cmd(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def ffprobe(path: Path) -> dict[str, Any]:
    if not shutil_which("ffprobe"):
        return {"available": False}
    p = run_cmd([
        "ffprobe", "-hide_banner", "-v", "error",
        "-show_entries", "format=duration,size",
        "-show_entries", "stream=codec_name,sample_rate,channels",
        "-of", "json", str(path),
    ])
    try:
        parsed = json.loads(p.stdout or "{}")
    except json.JSONDecodeError:
        parsed = {}
    parsed["available"] = True
    parsed["returncode"] = p.returncode
    if p.stderr:
        parsed["stderr"] = p.stderr[-1000:]
    return parsed


def shutil_which(name: str) -> str | None:
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(directory) / name
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def convert_to_wav(path: Path, work_dir: Path) -> Path:
    if path.suffix.lower() == ".wav":
        return path
    if not shutil_which("ffmpeg"):
        raise RuntimeError("ffmpeg_required_for_non_wav_input")
    out = work_dir / "converted.wav"
    p = run_cmd(["ffmpeg", "-y", "-i", str(path), "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(out)])
    if p.returncode != 0 or not out.is_file():
        raise RuntimeError(f"ffmpeg_convert_failed:{p.stderr[-500:]}")
    return out


@dataclass
class AudioData:
    samples: list[float]
    sample_rate: int
    channels: int
    sample_width: int


def read_wav(path: Path) -> AudioData:
    with wave.open(str(path), "rb") as fh:
        channels = fh.getnchannels()
        sample_width = fh.getsampwidth()
        sample_rate = fh.getframerate()
        frames = fh.readframes(fh.getnframes())
    if sample_width != 2:
        raise RuntimeError(f"unsupported_sample_width:{sample_width}")
    pcm = array("h")
    pcm.frombytes(frames)
    if channels > 1:
        mono = []
        for i in range(0, len(pcm), channels):
            mono.append(sum(pcm[i:i + channels]) / channels)
        values = mono
    else:
        values = list(pcm)
    samples = [max(-1.0, min(1.0, float(v) / 32768.0)) for v in values]
    return AudioData(samples=samples, sample_rate=sample_rate, channels=channels, sample_width=sample_width)


def window_rms(samples: list[float], sample_rate: int, window_ms: int = 25, hop_ms: int = 10) -> tuple[list[float], list[float]]:
    win = max(1, int(sample_rate * window_ms / 1000))
    hop = max(1, int(sample_rate * hop_ms / 1000))
    times: list[float] = []
    rms: list[float] = []
    for start in range(0, max(1, len(samples) - win + 1), hop):
        chunk = samples[start:start + win]
        if not chunk:
            continue
        val = math.sqrt(sum(x * x for x in chunk) / len(chunk))
        times.append((start + win / 2) / sample_rate)
        rms.append(val)
    return times, rms


def dbfs(value: float) -> float:
    return 20.0 * math.log10(max(value, 1e-9))


def detect_pauses(samples: list[float], sample_rate: int, *, threshold_dbfs: float = -42.0,
                  min_pause_ms: int = 180) -> dict[str, Any]:
    times, rms = window_rms(samples, sample_rate)
    silent = [dbfs(v) < threshold_dbfs for v in rms]
    spans: list[dict[str, float]] = []
    start: float | None = None
    hop = 0.01
    for idx, is_silent in enumerate(silent):
        if is_silent and start is None:
            start = times[idx]
        if (not is_silent or idx == len(silent) - 1) and start is not None:
            end = times[idx] if not is_silent else times[idx] + hop
            dur = end - start
            if dur * 1000 >= min_pause_ms:
                spans.append({"start_sec": round(start, 3), "end_sec": round(end, 3), "duration_ms": round(dur * 1000, 1)})
            start = None
    duration = len(samples) / sample_rate if sample_rate else 0.0
    silence_time = sum(span["duration_ms"] for span in spans) / 1000.0
    return {
        "threshold_dbfs": threshold_dbfs,
        "min_pause_ms": min_pause_ms,
        "pause_count": len(spans),
        "pause_spans": spans,
        "silence_ratio": round(silence_time / duration, 4) if duration else 0.0,
    }


def estimate_f0(samples: list[float], sample_rate: int) -> dict[str, Any]:
    # Lightweight autocorrelation over voiced-ish 40 ms frames. Good enough for
    # regression/prosody trend checks, not a musicological pitch tracker.
    frame = int(sample_rate * 0.04)
    hop = int(sample_rate * 0.02)
    min_lag = max(1, int(sample_rate / 450.0))
    max_lag = max(min_lag + 1, int(sample_rate / 70.0))
    f0s: list[float] = []
    for start in range(0, max(0, len(samples) - frame), hop):
        chunk = samples[start:start + frame]
        energy = math.sqrt(sum(x * x for x in chunk) / len(chunk)) if chunk else 0.0
        if energy < 0.01:
            continue
        mean = sum(chunk) / len(chunk)
        centered = [x - mean for x in chunk]
        best_lag = None
        best_corr = 0.0
        denom = sum(x * x for x in centered) or 1e-9
        for lag in range(min_lag, min(max_lag, len(centered) - 1)):
            corr = sum(centered[i] * centered[i + lag] for i in range(0, len(centered) - lag)) / denom
            if corr > best_corr:
                best_corr = corr
                best_lag = lag
        if best_lag and best_corr > 0.25:
            f0s.append(sample_rate / best_lag)
    if not f0s:
        return {"available": False, "f0_median_hz": None, "f0_range_semitones": None, "f0_std_hz": None, "voiced_frame_count": 0}
    lo = max(min(f0s), 1e-6)
    hi = max(f0s)
    return {
        "available": True,
        "f0_median_hz": round(statistics.median(f0s), 2),
        "f0_std_hz": round(statistics.pstdev(f0s), 2) if len(f0s) > 1 else 0.0,
        "f0_range_semitones": round(12.0 * math.log2(hi / lo), 2) if hi > lo else 0.0,
        "voiced_frame_count": len(f0s),
    }


def load_planned_pauses(path: Path | None) -> list[int]:
    if not path:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        chunks = payload
    elif isinstance(payload, dict):
        chunks = (payload.get("chatterbox_pause_plan") or payload.get("chunks") or
                  (payload.get("render_plan") or {}).get("chunks") or [])
        if not chunks and payload.get("turn_pairs"):
            chunks = []
            for pair in payload.get("turn_pairs") or []:
                chunks.extend(((pair.get("embry") or {}).get("chatterbox_pause_plan") or []))
    else:
        chunks = []
    pauses = []
    for chunk in chunks:
        try:
            pause = int(chunk.get("pause_after_ms") or 0)
        except AttributeError:
            continue
        if pause > 0:
            pauses.append(pause)
    return pauses


def target_values(label: str | None, arousal: float | None, valence: float | None) -> dict[str, Any]:
    profile = TARGET_PROFILES.get((label or "").lower(), TARGET_PROFILES["neutral"])
    return {
        "label": label or "neutral",
        "arousal": float(profile["arousal"] if arousal is None else arousal),
        "valence": float(profile["valence"] if valence is None else valence),
        "profile_source": "explicit" if arousal is not None or valence is not None else "label_profile",
    }


def score_against_target(target: dict[str, Any], estimated_arousal: float, estimated_valence: float,
                         text_similarity: float | None, quality_score: float, prosody_score: float) -> tuple[float, float]:
    arousal_match = max(0.0, 1.0 - abs(target["arousal"] - estimated_arousal))
    valence_match = max(0.0, 1.0 - abs(target["valence"] - estimated_valence) / 2.0)
    affect_match = 0.55 * arousal_match + 0.45 * valence_match
    intelligibility = text_similarity if text_similarity is not None else 0.55
    overall = 100.0 * (0.35 * affect_match + 0.25 * intelligibility + 0.20 * prosody_score + 0.20 * quality_score)
    return affect_match, overall


def analyze(audio_path: Path, *, expected_text: str | None, transcript: str | None,
            target_label: str | None, target_arousal: float | None, target_valence: float | None,
            render_plan: Path | None) -> dict[str, Any]:
    if not audio_path.is_file():
        return {
            "schema": SCHEMA, "created_at": utc_now(), "status": "FAIL_MISSING_AUDIO",
            "verdict": "fail", "overall_score": 0, "audio_path": str(audio_path),
            "failed_gates": ["audio_file_exists"], "mocked": False, "live": False,
        }
    with tempfile.TemporaryDirectory(prefix="analyze-chatterbox-") as td:
        wav_path = convert_to_wav(audio_path, Path(td))
        data = read_wav(wav_path)
    samples = data.samples
    sr = data.sample_rate
    duration = len(samples) / sr if sr else 0.0
    abs_samples = [abs(x) for x in samples]
    peak = max(abs_samples) if abs_samples else 0.0
    clipping_fraction = sum(1 for x in abs_samples if x >= 0.999) / len(abs_samples) if abs_samples else 0.0
    _, rms_vals = window_rms(samples, sr)
    rms_db = [dbfs(v) for v in rms_vals]
    rms_median = statistics.median(rms_db) if rms_db else -120.0
    rms_std = statistics.pstdev(rms_db) if len(rms_db) > 1 else 0.0
    pauses = detect_pauses(samples, sr)
    f0 = estimate_f0(samples, sr)
    speech_sec = max(0.001, duration * (1.0 - pauses["silence_ratio"]))
    expected_words = len((expected_text or "").split())
    speech_rate_wpm = (expected_words / speech_sec * 60.0) if expected_words else None
    transcript_similarity = None
    if expected_text and transcript:
        transcript_similarity = difflib.SequenceMatcher(None, " ".join(expected_text.lower().split()), " ".join(transcript.lower().split())).ratio()
    planned = load_planned_pauses(render_plan)
    measured_long = [span["duration_ms"] for span in pauses["pause_spans"] if span["duration_ms"] >= 250]
    estimated_arousal = max(0.0, min(1.0, 0.45 + (rms_median + 28.0) / 38.0 * 0.25 + min(rms_std, 12.0) / 12.0 * 0.20))
    estimated_valence = max(-1.0, min(1.0, 0.0))
    target = target_values(target_label, target_arousal, target_valence)
    artifact_flags: list[str] = []
    if peak < 0.02:
        artifact_flags.append("very_low_signal")
    if clipping_fraction > 0.001:
        artifact_flags.append("clipping_detected")
    if pauses["silence_ratio"] > 0.45:
        artifact_flags.append("excessive_silence_ratio")
    if planned and not measured_long:
        artifact_flags.append("planned_pause_not_detected")
    if any(span["duration_ms"] > 3000 for span in pauses["pause_spans"]):
        artifact_flags.append("long_unexplained_silence")
    quality_score = max(0.0, 1.0 - min(1.0, clipping_fraction * 50.0) - (0.25 if peak < 0.02 else 0.0))
    prosody_score = 0.7
    if speech_rate_wpm is not None:
        prosody_score = 1.0 if 90 <= speech_rate_wpm <= 190 else 0.65
    if pauses["pause_count"] and planned:
        prosody_score = min(1.0, prosody_score + 0.1)
    affect_match, overall = score_against_target(target, estimated_arousal, estimated_valence, transcript_similarity, quality_score, prosody_score)
    failed_gates = []
    if artifact_flags:
        failed_gates.extend(artifact_flags)
    status = "PASS_VOICE_EVAL" if overall >= 75 and not failed_gates else "REVIEW_VOICE_EVAL"
    verdict = "pass" if status.startswith("PASS") else "review"
    if overall < 50 or "clipping_detected" in failed_gates or "very_low_signal" in failed_gates:
        status = "FAIL_VOICE_EVAL"
        verdict = "fail"
    return {
        "schema": SCHEMA,
        "created_at": utc_now(),
        "status": status,
        "verdict": verdict,
        "overall_score": round(overall, 2),
        "mocked": False,
        "live": True,
        "audio_path": str(audio_path),
        "ffprobe": ffprobe(audio_path),
        "target_affect": target,
        "affect": {
            "predicted_label": "not_available",
            "probabilities": {},
            "emotion_classifier": {"available": False, "reason": "optional_speechbrain_not_loaded"},
            "target_match_score": round(affect_match, 4),
            "estimated_arousal": round(estimated_arousal, 4),
            "estimated_valence": round(estimated_valence, 4),
            "warning": "Acoustic affect proxies are evaluation signals, not ground-truth emotion.",
        },
        "prosody": {
            "duration_sec": round(duration, 3),
            "speech_rate_wpm": round(speech_rate_wpm, 2) if speech_rate_wpm is not None else None,
            "rms_db_median": round(rms_median, 2),
            "rms_db_std": round(rms_std, 2),
            **f0,
        },
        "pauses": {
            **pauses,
            "planned_pause_after_ms": planned,
            "measured_long_pause_ms": measured_long,
            "planned_pause_count": len(planned),
            "measured_long_pause_count": len(measured_long),
        },
        "intelligibility": {
            "expected_text_present": bool(expected_text),
            "expected_word_count": expected_words,
            "transcript": transcript,
            "text_similarity": round(transcript_similarity, 4) if transcript_similarity is not None else None,
            "asr_claim": "caller_supplied_transcript_only" if transcript else "not_measured",
        },
        "quality": {
            "peak_amplitude": round(peak, 6),
            "clipping_fraction": round(clipping_fraction, 8),
            "artifact_flags": artifact_flags,
            "quality_score": round(quality_score, 4),
        },
        "recommendations": recommendations(planned, measured_long, artifact_flags, speech_rate_wpm),
        "claims": {
            "proves": ["audio file was decoded and measured", "pause and quality metrics were computed from waveform samples"],
            "does_not_prove": ["real speaker emotion", "human preference", "ASR fidelity unless transcript is supplied"],
        },
        "failed_gates": failed_gates,
    }


def recommendations(planned: list[int], measured: list[float], flags: list[str], speech_rate: float | None) -> list[str]:
    out: list[str] = []
    if planned and len(measured) < len(planned):
        out.append("Increase render_chunks pause_after_ms or split affect beats into separate chunks; fewer measured pauses than planned pauses were detected.")
    if not planned:
        out.append("Provide a Chatterbox render plan or conversation turn to compare requested pauses with measured waveform pauses.")
    if speech_rate and speech_rate > 190:
        out.append("Speech rate is high; add chunk pauses or reduce pace for collect-herself/tender lines.")
    if "clipping_detected" in flags:
        out.append("Reduce gain or rerender; waveform clipping was detected.")
    if not out:
        out.append("No hard technical issue detected; use human listening or ASR for perceptual acceptance.")
    return out


def write_markdown(result: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Chatterbox voice-quality evaluation",
        "",
        f"Status: `{result['status']}`",
        f"Verdict: `{result['verdict']}`",
        f"Overall score: `{result['overall_score']}`",
        "",
        "## Affect boundary",
        result["affect"]["warning"],
        "",
        "## Pause evidence",
        f"Planned pauses: `{result['pauses']['planned_pause_after_ms']}`",
        f"Measured long pauses: `{result['pauses']['measured_long_pause_ms']}`",
        f"Silence ratio: `{result['pauses']['silence_ratio']}`",
        "",
        "## Quality",
        f"Peak amplitude: `{result['quality']['peak_amplitude']}`",
        f"Clipping fraction: `{result['quality']['clipping_fraction']}`",
        f"Artifact flags: `{result['quality']['artifact_flags']}`",
        "",
        "## Recommendations",
    ]
    lines.extend(f"- {item}" for item in result.get("recommendations") or [])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--audio", required=True, type=Path)
    ap.add_argument("--expected-text")
    ap.add_argument("--transcript")
    ap.add_argument("--target-label", default="neutral")
    ap.add_argument("--target-arousal", type=float)
    ap.add_argument("--target-valence", type=float)
    ap.add_argument("--render-plan", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--report", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        result = analyze(args.audio, expected_text=args.expected_text, transcript=args.transcript,
                         target_label=args.target_label, target_arousal=args.target_arousal,
                         target_valence=args.target_valence, render_plan=args.render_plan)
    except Exception as exc:
        result = {"schema": SCHEMA, "created_at": utc_now(), "status": "FAIL_ANALYZER_ERROR", "verdict": "fail", "overall_score": 0, "mocked": False, "live": False, "audio_path": str(args.audio), "failed_gates": [str(exc)]}
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.report:
        write_markdown(result, args.report)
    if args.json or not args.out:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['status']} score={result['overall_score']} verdict={result['verdict']} out={args.out}")
    return 0 if result.get("status") != "FAIL_ANALYZER_ERROR" and result.get("status") != "FAIL_MISSING_AUDIO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
