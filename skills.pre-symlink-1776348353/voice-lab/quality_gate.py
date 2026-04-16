"""Per-segment quality gate combining voice-lab and hum-lab metrics.

Wraps quality.py (TTS metrics) and evaluate.py (RVC metrics) into
a unified pass/fail gate for voice lesson segments.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf
from loguru import logger
from rich.console import Console
from rich.table import Table

console = Console()

# Quality thresholds
THRESHOLDS = {
    "noise_floor_db": -40.0,  # Below this = too quiet
    "peak_db": -0.5,          # Above this = clipping risk
    "min_duration_s": 2.0,     # Below = too short for Qwen3-TTS training
    "max_duration_s": 12.0,    # Above = too long for Qwen3-TTS (Horus filters 2-12s)
    "similarity_min": 0.5,     # Minimum acceptable similarity
    "rms_min_db": -35.0,       # Minimum RMS for usable audio
}


@dataclass
class GateResult:
    """Result of quality gate for a single segment."""

    segment_index: int
    passed: bool
    score: float
    checks: dict
    failures: list[str]

    def to_dict(self) -> dict:
        return {
            "segment_index": self.segment_index,
            "passed": self.passed,
            "score": round(self.score, 3),
            "checks": self.checks,
            "failures": self.failures,
        }


@dataclass
class GateReport:
    """Aggregate gate report for a session."""

    total_segments: int
    passed_segments: int
    failed_segments: int
    overall_score: float
    results: list[GateResult]

    def to_dict(self) -> dict:
        return {
            "total_segments": self.total_segments,
            "passed_segments": self.passed_segments,
            "failed_segments": self.failed_segments,
            "overall_score": round(self.overall_score, 3),
            "training_ready": self.passed_segments >= self.total_segments * 0.7,
            "results": [r.to_dict() for r in self.results],
        }


def check_segment(
    audio_path: Path,
    reference_path: Optional[Path] = None,
    segment_index: int = 0,
) -> GateResult:
    """Run quality gate on a single audio segment."""
    failures = []
    checks = {}
    score = 0.0

    try:
        audio, sr = sf.read(str(audio_path), dtype="float32")
    except Exception as exc:
        return GateResult(
            segment_index=segment_index,
            passed=False,
            score=0.0,
            checks={"error": str(exc)},
            failures=["file_unreadable"],
        )

    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    duration_s = len(audio) / sr
    rms = float(np.sqrt(np.mean(audio**2)))
    peak = float(np.max(np.abs(audio)))
    rms_db = 20 * np.log10(rms + 1e-10)
    peak_db = 20 * np.log10(peak + 1e-10)

    checks["duration_s"] = round(duration_s, 2)
    checks["rms_db"] = round(rms_db, 1)
    checks["peak_db"] = round(peak_db, 1)

    # Duration check
    if duration_s < THRESHOLDS["min_duration_s"]:
        failures.append(f"too_short ({duration_s:.1f}s < {THRESHOLDS['min_duration_s']}s)")
    elif duration_s > THRESHOLDS["max_duration_s"]:
        failures.append(f"too_long ({duration_s:.1f}s > {THRESHOLDS['max_duration_s']}s)")

    # Noise check
    if rms_db < THRESHOLDS["rms_min_db"]:
        failures.append(f"too_quiet (RMS {rms_db:.1f}dB < {THRESHOLDS['rms_min_db']}dB)")

    # Clipping check
    if peak_db > THRESHOLDS["peak_db"]:
        failures.append(f"clipping (peak {peak_db:.1f}dB)")
        checks["clipping"] = True
    else:
        checks["clipping"] = False

    # Silence ratio — check how much of the segment is silent
    frame_len = int(0.02 * sr)  # 20ms frames
    n_frames = len(audio) // frame_len
    if n_frames > 0:
        silent_frames = 0
        for i in range(n_frames):
            frame = audio[i * frame_len : (i + 1) * frame_len]
            frame_rms = np.sqrt(np.mean(frame**2))
            if 20 * np.log10(frame_rms + 1e-10) < -50:
                silent_frames += 1
        silence_ratio = silent_frames / n_frames
        checks["silence_ratio"] = round(silence_ratio, 3)
        if silence_ratio > 0.5:
            failures.append(f"mostly_silent ({silence_ratio:.0%})")

    # Similarity check (if reference provided)
    if reference_path and reference_path.exists():
        try:
            from alignment import _compute_similarity

            ref_audio, ref_sr = sf.read(str(reference_path), dtype="float32")
            if ref_audio.ndim > 1:
                ref_audio = ref_audio.mean(axis=1)

            sim = _compute_similarity(audio, ref_audio, sr)
            checks["similarity"] = round(sim, 3)

            if sim < THRESHOLDS["similarity_min"]:
                failures.append(
                    f"low_similarity ({sim:.2f} < {THRESHOLDS['similarity_min']})"
                )
        except Exception as exc:
            logger.warning(f"Similarity check failed: {exc}")
            checks["similarity_error"] = str(exc)

    # Compute overall score (0-1)
    duration_score = 1.0 if THRESHOLDS["min_duration_s"] <= duration_s <= THRESHOLDS["max_duration_s"] else 0.5
    noise_score = min(1.0, max(0.0, (rms_db - THRESHOLDS["rms_min_db"]) / 20))
    clip_score = 0.0 if checks.get("clipping") else 1.0
    silence_score = 1.0 - checks.get("silence_ratio", 0.0)

    score = 0.25 * duration_score + 0.30 * noise_score + 0.25 * clip_score + 0.20 * silence_score

    return GateResult(
        segment_index=segment_index,
        passed=len(failures) == 0,
        score=score,
        checks=checks,
        failures=failures,
    )


def check_session(
    segments_dir: Path,
    reference_dir: Optional[Path] = None,
) -> GateReport:
    """Run quality gate on all segments in a directory."""
    segment_files = sorted(segments_dir.glob("*.wav"))
    if not segment_files:
        return GateReport(
            total_segments=0,
            passed_segments=0,
            failed_segments=0,
            overall_score=0.0,
            results=[],
        )

    results = []
    for i, seg_path in enumerate(segment_files):
        ref_path = None
        if reference_dir:
            # Try to find matching reference
            ref_name = seg_path.name.replace("graham_", "original_")
            ref_path = reference_dir / ref_name
            if not ref_path.exists():
                ref_path = None

        result = check_segment(seg_path, ref_path, segment_index=i)
        results.append(result)

    passed = sum(1 for r in results if r.passed)
    scores = [r.score for r in results]
    avg_score = sum(scores) / len(scores) if scores else 0.0

    return GateReport(
        total_segments=len(results),
        passed_segments=passed,
        failed_segments=len(results) - passed,
        overall_score=avg_score,
        results=results,
    )


def print_gate_report(report: GateReport) -> None:
    """Display gate report in a table."""
    table = Table(title="Quality Gate Report")
    table.add_column("#", justify="right", width=4)
    table.add_column("Duration", justify="right")
    table.add_column("RMS dB", justify="right")
    table.add_column("Peak dB", justify="right")
    table.add_column("Score", justify="right")
    table.add_column("Status", justify="center")
    table.add_column("Issues")

    for r in report.results:
        dur = r.checks.get("duration_s", 0)
        rms = r.checks.get("rms_db", 0)
        peak = r.checks.get("peak_db", 0)

        status = "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]"
        score_color = "green" if r.score >= 0.7 else "yellow" if r.score >= 0.5 else "red"
        issues = ", ".join(r.failures) if r.failures else ""

        table.add_row(
            str(r.segment_index),
            f"{dur:.1f}s",
            f"{rms:.1f}",
            f"{peak:.1f}",
            f"[{score_color}]{r.score:.2f}[/{score_color}]",
            status,
            issues,
        )

    console.print(table)

    # Summary
    console.print(f"\nTotal: {report.total_segments} segments")
    console.print(f"Passed: [green]{report.passed_segments}[/green]")
    console.print(f"Failed: [red]{report.failed_segments}[/red]")
    console.print(f"Overall score: {report.overall_score:.3f}")

    training_ready = report.passed_segments >= report.total_segments * 0.7
    if training_ready:
        console.print("[green]Training ready: YES[/green]")
    else:
        console.print("[red]Training ready: NO (need 70% pass rate)[/red]")
