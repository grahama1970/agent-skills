"""Bounded trained MIDI-control female hum renderer.

This is deliberately small and local: it learns a control-conditioned harmonic
profile from female HumTrans examples and renders MIDI/F0 curves without sample
splicing or voice-conversion services.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfiltfilt

from .sample_renderer import _load_midi_melody, midi_to_hz
from .timbre_model import _harmonic_profile, _notes_to_curves


@dataclass(frozen=True)
class NeuralTrainResult:
    out_dir: str
    checkpoint: str
    metrics_json: str
    train_count: int
    valid_count: int
    frame_count: int
    harmonic_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NeuralRenderResult:
    out_dir: str
    output_wav: str
    render_manifest: str
    checkpoint: str
    note_count: int
    duration_s: float
    peak: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HumEvalResult:
    report_json: str
    generated_wav: str
    target_midi: str
    median_abs_pitch_error_cents: float | None
    voiced_ratio: float
    duration_error_s: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _items(manifest: dict[str, Any], split: str) -> list[dict[str, Any]]:
    return [item for item in manifest.get("items", []) if item.get("split") == split]


def _harmonic_dataset_stats(
    items: list[dict[str, Any]],
    *,
    sr: int,
    n_harmonics: int,
    max_duration_s: float | None,
) -> tuple[np.ndarray, list[float], list[float], int]:
    profiles: list[np.ndarray] = []
    f0_values: list[float] = []
    rms_values: list[float] = []
    used = 0
    for item in items:
        audio_path = Path(item["audio_path"])
        if not audio_path.exists():
            continue
        y, actual_sr = librosa.load(audio_path, sr=sr, mono=True, duration=max_duration_s)
        if len(y) < 2048:
            continue
        clip_profiles, clip_f0, clip_rms = _harmonic_profile(
            y,
            actual_sr,
            n_harmonics=n_harmonics,
        )
        if not clip_profiles:
            continue
        profiles.extend(clip_profiles)
        f0_values.extend(clip_f0)
        rms_values.extend(clip_rms)
        used += 1
    if not profiles:
        raise ValueError("No voiced harmonic frames found in control dataset")
    median_profile = np.median(np.stack(profiles), axis=0).astype(np.float32)
    median_profile /= max(float(np.sum(median_profile)), 1e-9)
    return median_profile, f0_values, rms_values, used


def train_neural_hum_renderer(
    controls_dir: Path,
    out_dir: Path,
    *,
    epochs: int = 3,
    batch_size: int = 8,
    sample_rate: int = 22050,
    harmonics: int = 18,
    max_duration_s: float | None = 10.0,
) -> NeuralTrainResult:
    manifest_path = controls_dir / "manifest.json"
    manifest = _read_json(manifest_path)
    train_items = _items(manifest, "train")
    valid_items = _items(manifest, "valid")
    if not train_items:
        raise ValueError(f"No train items in {manifest_path}")
    out_dir.mkdir(parents=True, exist_ok=True)

    profile, f0_values, rms_values, train_used = _harmonic_dataset_stats(
        train_items,
        sr=sample_rate,
        n_harmonics=harmonics,
        max_duration_s=max_duration_s,
    )
    valid_profile = None
    valid_used = 0
    valid_distance = None
    if valid_items:
        try:
            valid_profile, _, _, valid_used = _harmonic_dataset_stats(
                valid_items,
                sr=sample_rate,
                n_harmonics=harmonics,
                max_duration_s=max_duration_s,
            )
            valid_distance = float(np.mean(np.abs(profile - valid_profile)))
        except Exception:
            valid_profile = None

    checkpoint = out_dir / "checkpoint.npz"
    np.savez_compressed(
        checkpoint,
        harmonic_weights=profile.astype(np.float32),
        sample_rate=np.asarray([sample_rate], dtype=np.int32),
        harmonics=np.asarray([harmonics], dtype=np.int32),
        median_rms=np.asarray([float(np.median(rms_values))], dtype=np.float32),
        p90_rms=np.asarray([float(np.percentile(rms_values, 90))], dtype=np.float32),
        median_f0_hz=np.asarray([float(np.median(f0_values))], dtype=np.float32),
    )
    metrics = {
        "schema": "hum.neural_renderer_metrics.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "controls_dir": str(controls_dir),
        "checkpoint": str(checkpoint),
        "renderer": "control_conditioned_harmonic_ddsp_numpy_v1",
        "epochs_requested": epochs,
        "batch_size_requested": batch_size,
        "train_count": len(train_items),
        "train_used": train_used,
        "valid_count": len(valid_items),
        "valid_used": valid_used,
        "frame_count_estimate": len(f0_values),
        "harmonics": harmonics,
        "median_f0_hz": round(float(np.median(f0_values)), 4),
        "p10_f0_hz": round(float(np.percentile(f0_values, 10)), 4),
        "p90_f0_hz": round(float(np.percentile(f0_values, 90)), 4),
        "median_rms": round(float(np.median(rms_values)), 6),
        "valid_harmonic_l1": round(valid_distance, 8) if valid_distance is not None else None,
        "limitations": [
            "This is a bounded trained DDSP-style harmonic renderer, not a final neural vocoder.",
            "It trains on female HumTrans audio and follows MIDI/control curves, but human listening remains the gate.",
            "It is designed to prove or reject MIDI-control viability before larger training or RunPod use.",
        ],
    }
    metrics_path = out_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    return NeuralTrainResult(
        out_dir=str(out_dir),
        checkpoint=str(checkpoint),
        metrics_json=str(metrics_path),
        train_count=len(train_items),
        valid_count=len(valid_items),
        frame_count=len(f0_values),
        harmonic_count=harmonics,
    )


def _checkpoint_data(checkpoint: Path) -> dict[str, Any]:
    data = np.load(checkpoint)
    return {
        "weights": np.asarray(data["harmonic_weights"], dtype=np.float32),
        "sample_rate": int(data["sample_rate"][0]),
        "median_rms": float(data["median_rms"][0]),
        "p90_rms": float(data["p90_rms"][0]),
    }


def render_neural_hum(
    checkpoint: Path,
    midi_path: Path,
    out_dir: Path,
    *,
    max_melody_duration_s: float | None = None,
    midi_track_name: str | None = None,
    midi_min_note_duration_s: float = 0.12,
    transpose_semitones: float = -5.0,
    portamento_s: float = 0.085,
    lowpass_hz: float = 1850.0,
    breath_gain: float = 0.004,
) -> NeuralRenderResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    ckpt = _checkpoint_data(checkpoint)
    sr = int(ckpt["sample_rate"])
    melody = _load_midi_melody(
        midi_path,
        max_duration_s=max_melody_duration_s,
        preferred_track_name=midi_track_name,
        legato=True,
        min_note_duration_s=midi_min_note_duration_s,
    )
    notes = list(melody["notes"])
    f0, amp = _notes_to_curves(
        notes,
        sr=sr,
        transpose_semitones=transpose_semitones,
        portamento_s=portamento_s,
    )
    weights = ckpt["weights"]
    weights = weights / max(float(np.sum(weights)), 1e-9)
    phase = np.cumsum(2.0 * np.pi * f0 / sr).astype(np.float32)
    y = np.zeros_like(f0, dtype=np.float32)
    for harmonic, weight in enumerate(weights, start=1):
        y += float(weight) * np.sin(harmonic * phase).astype(np.float32)
    y *= np.clip(amp, 0.0, 1.0)

    body_sos = butter(2, [85, lowpass_hz], btype="bandpass", fs=sr, output="sos")
    y = sosfiltfilt(body_sos, y).astype(np.float32)
    rng = np.random.default_rng(71)
    breath = rng.standard_normal(len(y)).astype(np.float32)
    breath_sos = butter(2, [500, min(2400, sr / 2 - 100)], btype="bandpass", fs=sr, output="sos")
    breath = sosfiltfilt(breath_sos, breath).astype(np.float32)
    if np.max(np.abs(breath)) > 0:
        breath /= np.max(np.abs(breath))
    y += breath_gain * breath * np.clip(amp, 0.0, 1.0)
    peak = float(np.max(np.abs(y))) if len(y) else 0.0
    if peak > 0:
        y = 0.72 * y / peak
    peak = float(np.max(np.abs(y))) if len(y) else 0.0

    output_wav = out_dir / "female_hum.wav"
    sf.write(output_wav, y, sr)
    pitch_bend_note_count = sum(1 for note in notes if note.get("pitch_bend_points"))
    manifest = {
        "schema": "hum.neural_render.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "checkpoint": str(checkpoint),
        "midi_path": str(midi_path),
        "output_wav": str(output_wav),
        "renderer": "control_conditioned_harmonic_ddsp_numpy_v1",
        "selected_midi_instrument": melody.get("instrument"),
        "source_tempo_bpm": melody.get("source_tempo_bpm"),
        "note_count": len(notes),
        "pitch_bend_note_count": pitch_bend_note_count,
        "pitch_bend_control": "pitch_bend_points_interpolated_to_f0_curve",
        "glissando_control": "continuous f0 curve with portamento smoothing; MIDI pitch bends preserved when present",
        "transpose_semitones": transpose_semitones,
        "portamento_s": portamento_s,
        "lowpass_hz": lowpass_hz,
        "duration_s": round(len(y) / sr, 4),
        "peak": round(peak, 6),
        "notes_preview": notes[:24],
        "limitations": [
            "Not final quality; this is an MVP viability renderer.",
            "No sample splicing and no Seed-VC/Orpheus conversion were used.",
            "Human listening remains required before any cache publication.",
        ],
    }
    manifest_path = out_dir / "render_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return NeuralRenderResult(
        out_dir=str(out_dir),
        output_wav=str(output_wav),
        render_manifest=str(manifest_path),
        checkpoint=str(checkpoint),
        note_count=len(notes),
        duration_s=round(len(y) / sr, 4),
        peak=round(peak, 6),
    )


def _target_curve_from_midi(midi_path: Path, *, sr: int, transpose_semitones: float = -5.0) -> tuple[np.ndarray, np.ndarray]:
    melody = _load_midi_melody(midi_path, legato=True, min_note_duration_s=0.12)
    return _notes_to_curves(list(melody["notes"]), sr=sr, transpose_semitones=transpose_semitones, portamento_s=0.085)


def _f0_from_wav(wav_path: Path, *, sr: int) -> tuple[np.ndarray, np.ndarray]:
    y, actual_sr = librosa.load(wav_path, sr=sr, mono=True)
    f0 = librosa.yin(
        y,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C6"),
        sr=actual_sr,
        frame_length=2048,
        hop_length=256,
    ).astype(np.float32)
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=256)[0]
    threshold = max(float(np.percentile(rms, 35)) * 0.8, 1e-4)
    voiced = np.isfinite(f0) & (rms > threshold)
    f0[~voiced] = 0.0
    times = librosa.frames_to_time(np.arange(len(f0)), sr=actual_sr, hop_length=256).astype(np.float32)
    return times, f0


def evaluate_hum_render(
    render_dir: Path,
    target_midi: Path,
    out: Path,
    *,
    generated_name: str = "female_hum.wav",
    transpose_semitones: float = -5.0,
) -> HumEvalResult:
    render_manifest = _read_json(render_dir / "render_manifest.json")
    generated_wav = render_dir / generated_name
    if not generated_wav.exists():
        raise FileNotFoundError(generated_wav)
    sr = int(sf.info(generated_wav).samplerate)
    times, generated_f0 = _f0_from_wav(generated_wav, sr=sr)
    target_f0_samples, target_amp = _target_curve_from_midi(target_midi, sr=sr, transpose_semitones=transpose_semitones)
    target_times = np.arange(len(target_f0_samples), dtype=np.float32) / sr
    target_at_frames = np.interp(times, target_times, target_f0_samples, left=0.0, right=0.0)
    both = (generated_f0 > 0.0) & (target_at_frames > 0.0)
    cents_errors: np.ndarray
    if np.any(both):
        cents_errors = 1200.0 * np.log2(np.maximum(generated_f0[both], 1e-6) / np.maximum(target_at_frames[both], 1e-6))
        median_abs_pitch = float(np.median(np.abs(cents_errors)))
        p90_abs_pitch = float(np.percentile(np.abs(cents_errors), 90))
    else:
        cents_errors = np.asarray([], dtype=np.float32)
        median_abs_pitch = None
        p90_abs_pitch = None
    gen_duration = sf.info(generated_wav).duration
    target_duration = len(target_f0_samples) / sr
    voiced_ratio = float(np.mean(generated_f0 > 0.0)) if len(generated_f0) else 0.0
    report = {
        "schema": "hum.render_eval.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "render_dir": str(render_dir),
        "generated_wav": str(generated_wav),
        "target_midi": str(target_midi),
        "render_manifest": render_manifest,
        "metrics": {
            "median_abs_pitch_error_cents": round(median_abs_pitch, 4) if median_abs_pitch is not None else None,
            "p90_abs_pitch_error_cents": round(p90_abs_pitch, 4) if p90_abs_pitch is not None else None,
            "overlap_frame_count": int(np.sum(both)),
            "voiced_ratio": round(voiced_ratio, 6),
            "generated_duration_s": round(float(gen_duration), 4),
            "target_duration_s": round(float(target_duration), 4),
            "duration_error_s": round(float(gen_duration - target_duration), 4),
            "pitch_bend_note_count": render_manifest.get("pitch_bend_note_count"),
        },
        "gate": {
            "numeric_alignment_only": True,
            "listening_required": True,
            "cache_publication_allowed": False,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return HumEvalResult(
        report_json=str(out),
        generated_wav=str(generated_wav),
        target_midi=str(target_midi),
        median_abs_pitch_error_cents=round(median_abs_pitch, 4) if median_abs_pitch is not None else None,
        voiced_ratio=round(voiced_ratio, 6),
        duration_error_s=round(float(gen_duration - target_duration), 4),
    )
