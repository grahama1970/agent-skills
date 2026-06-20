from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import soundfile as sf


@dataclass(frozen=True)
class PitchCorrectionResult:
    input_wav: Path
    output_wav: Path | None
    analysis_json: Path
    manifest_json: Path
    correction_cents: float
    voiced_ratio: float
    median_abs_cents_before: float | None
    median_abs_cents_after_estimate: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_wav": str(self.input_wav),
            "output_wav": str(self.output_wav) if self.output_wav else None,
            "analysis_json": str(self.analysis_json),
            "manifest_json": str(self.manifest_json),
            "correction_cents": self.correction_cents,
            "voiced_ratio": self.voiced_ratio,
            "median_abs_cents_before": self.median_abs_cents_before,
            "median_abs_cents_after_estimate": self.median_abs_cents_after_estimate,
        }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_float(value: float | np.floating | None) -> float | None:
    if value is None:
        return None
    value = float(value)
    if np.isnan(value) or np.isinf(value):
        return None
    return value


def _nearest_note_cents(f0: np.ndarray) -> np.ndarray:
    midi = librosa.hz_to_midi(f0)
    nearest = np.rint(midi)
    return (midi - nearest) * 100.0


def analyze_pitch(
    audio_path: Path,
    *,
    sample_rate: int = 44100,
    fmin_hz: float = 80.0,
    fmax_hz: float = 880.0,
) -> dict[str, Any]:
    y, sr = librosa.load(audio_path, sr=sample_rate, mono=True)
    duration_seconds = float(len(y) / sr) if sr else 0.0
    if len(y) == 0:
        voiced = np.array([], dtype=float)
        cents = np.array([], dtype=float)
    else:
        f0, _, _ = librosa.pyin(
            y,
            fmin=fmin_hz,
            fmax=fmax_hz,
            sr=sr,
            frame_length=2048,
            hop_length=256,
        )
        voiced = f0[np.isfinite(f0)]
        cents = _nearest_note_cents(voiced) if voiced.size else np.array([], dtype=float)

    total_frames = int(np.ceil(len(y) / 256)) if len(y) else 0
    voiced_ratio = float(voiced.size / total_frames) if total_frames else 0.0
    median_cents = _safe_float(np.median(cents)) if cents.size else None
    return {
        "schema": "hum.pitch_analysis.v1",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "audio_path": str(audio_path),
        "audio_sha256": _sha256(audio_path),
        "sample_rate": sr,
        "duration_seconds": round(duration_seconds, 6),
        "fmin_hz": fmin_hz,
        "fmax_hz": fmax_hz,
        "voiced_frame_count": int(voiced.size),
        "total_frame_estimate": total_frames,
        "voiced_ratio": round(voiced_ratio, 6),
        "median_f0_hz": _safe_float(np.median(voiced)) if voiced.size else None,
        "median_detune_cents": median_cents,
        "mean_detune_cents": _safe_float(np.mean(cents)) if cents.size else None,
        "median_abs_detune_cents": _safe_float(np.median(np.abs(cents))) if cents.size else None,
        "p90_abs_detune_cents": _safe_float(np.percentile(np.abs(cents), 90)) if cents.size else None,
        "p95_abs_detune_cents": _safe_float(np.percentile(np.abs(cents), 95)) if cents.size else None,
        "note": (
            "This is a diagnostic pitch-centering estimate. It does not prove musical usability; "
            "human listening remains the gate."
        ),
    }


def pitch_correct_guide(
    audio_path: Path,
    out_dir: Path,
    *,
    sample_rate: int = 44100,
    max_correction_cents: float = 35.0,
    min_voiced_ratio: float = 0.08,
    target_peak_dbfs: float = -1.0,
    dry_run: bool = False,
) -> PitchCorrectionResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    analysis_before = analyze_pitch(audio_path, sample_rate=sample_rate)
    median_detune = analysis_before.get("median_detune_cents")
    voiced_ratio = float(analysis_before.get("voiced_ratio") or 0.0)
    if median_detune is None or voiced_ratio < min_voiced_ratio:
        correction_cents = 0.0
        reason = "insufficient_voiced_pitch"
    else:
        correction_cents = float(np.clip(-float(median_detune), -max_correction_cents, max_correction_cents))
        reason = "median_detune_to_nearest_equal_temperament"

    output_wav: Path | None = None
    analysis_after: dict[str, Any] | None = None
    if not dry_run:
        y, sr = librosa.load(audio_path, sr=sample_rate, mono=True)
        if abs(correction_cents) > 0.01 and len(y):
            y = librosa.effects.pitch_shift(y, sr=sr, n_steps=correction_cents / 100.0)
        peak = float(np.max(np.abs(y))) if len(y) else 0.0
        target_peak = float(10 ** (target_peak_dbfs / 20.0))
        if peak > 0:
            y = y * min(1.0, target_peak / peak)
        output_wav = out_dir / f"{audio_path.stem}__pitch_global_{correction_cents:+.1f}c.wav"
        sf.write(output_wav, y.astype(np.float32), sr)
        analysis_after = analyze_pitch(output_wav, sample_rate=sample_rate)

    analysis_path = out_dir / f"{audio_path.stem}__pitch_analysis.json"
    manifest_path = out_dir / f"{audio_path.stem}__pitch_correction_manifest.json"
    analysis_payload = {
        "schema": "hum.pitch_correction_analysis_bundle.v1",
        "before": analysis_before,
        "after": analysis_after,
    }
    analysis_path.write_text(json.dumps(analysis_payload, indent=2) + "\n")

    manifest = {
        "schema": "hum.pitch_corrected_guide.v1",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "input_wav": str(audio_path),
        "input_sha256": _sha256(audio_path),
        "output_wav": str(output_wav) if output_wav else None,
        "output_sha256": _sha256(output_wav) if output_wav else None,
        "method": "global_median_detune_correction",
        "reason": reason,
        "sample_rate": sample_rate,
        "max_correction_cents": max_correction_cents,
        "applied_correction_cents": correction_cents,
        "min_voiced_ratio": min_voiced_ratio,
        "analysis_json": str(analysis_path),
        "bakeoff_role": "pre_elevenlabs_guide_variant",
        "release_gate": "human_listening_required",
        "warning": (
            "This is intentionally light preprocessing before STS. It is not hard autotune, "
            "and it should be compared against the raw guide in the bakeoff."
        ),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    return PitchCorrectionResult(
        input_wav=audio_path,
        output_wav=output_wav,
        analysis_json=analysis_path,
        manifest_json=manifest_path,
        correction_cents=correction_cents,
        voiced_ratio=voiced_ratio,
        median_abs_cents_before=analysis_before.get("median_abs_detune_cents"),
        median_abs_cents_after_estimate=(
            analysis_after.get("median_abs_detune_cents") if analysis_after is not None else None
        ),
    )
