"""Train and render a lightweight harmonic hum timbre model."""

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

from .sample_renderer import _load_melody, _load_midi_melody, midi_to_hz


@dataclass(frozen=True)
class TimbreTrainResult:
    model_json: str
    dataset_index: str
    clip_count: int
    frame_count: int
    harmonic_count: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TimbreRenderResult:
    output_wav: str
    render_manifest: str
    model_json: str
    note_count: int
    duration_s: float
    peak: float

    def to_dict(self) -> dict:
        return asdict(self)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _harmonic_profile(
    y: np.ndarray,
    sr: int,
    *,
    n_harmonics: int,
    frame_length: int = 2048,
    hop_length: int = 256,
) -> tuple[list[np.ndarray], list[float], list[float]]:
    f0 = librosa.yin(
        y,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C6"),
        sr=sr,
        frame_length=frame_length,
        hop_length=hop_length,
    )
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    S = np.abs(librosa.stft(y, n_fft=frame_length, hop_length=hop_length))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=frame_length)
    voiced_threshold = max(float(np.percentile(rms, 45)) * 0.8, 1e-4)

    profiles: list[np.ndarray] = []
    voiced_f0: list[float] = []
    voiced_rms: list[float] = []
    frame_count = min(len(f0), len(rms), S.shape[1])
    for frame_index in range(frame_count):
        base = float(f0[frame_index])
        level = float(rms[frame_index])
        if not np.isfinite(base) or base <= 0.0 or level <= voiced_threshold:
            continue
        mags = []
        for harmonic in range(1, n_harmonics + 1):
            target = base * harmonic
            if target >= sr / 2:
                mags.append(0.0)
                continue
            bin_index = int(np.argmin(np.abs(freqs - target)))
            lo = max(0, bin_index - 1)
            hi = min(len(freqs), bin_index + 2)
            mags.append(float(np.max(S[lo:hi, frame_index])))
        arr = np.asarray(mags, dtype=np.float32)
        total = float(np.sum(arr))
        if total <= 0.0:
            continue
        profiles.append(arr / total)
        voiced_f0.append(base)
        voiced_rms.append(level)
    return profiles, voiced_f0, voiced_rms


def train_hum_timbre_model(
    dataset_index: Path,
    out_dir: Path,
    *,
    sr: int = 22050,
    n_harmonics: int = 16,
    max_duration_s: float | None = 60.0,
) -> TimbreTrainResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    index = _read_json(dataset_index)
    all_profiles: list[np.ndarray] = []
    all_f0: list[float] = []
    all_rms: list[float] = []
    clip_count = 0
    for item in index.get("items", []):
        audio_path = Path(item.get("audio_path", ""))
        if not audio_path.exists():
            continue
        y, actual_sr = librosa.load(audio_path, sr=sr, mono=True, duration=max_duration_s)
        if not len(y):
            continue
        profiles, f0_values, rms_values = _harmonic_profile(y, actual_sr, n_harmonics=n_harmonics)
        if not profiles:
            continue
        all_profiles.extend(profiles)
        all_f0.extend(f0_values)
        all_rms.extend(rms_values)
        clip_count += 1

    if not all_profiles:
        raise ValueError(f"No voiced harmonic frames found in {dataset_index}")

    profile = np.median(np.stack(all_profiles), axis=0)
    profile = profile / np.sum(profile)
    rms_values = np.asarray(all_rms, dtype=np.float32)
    f0_values = np.asarray(all_f0, dtype=np.float32)
    model = {
        "schema": "hum.timbre_model.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_index": str(dataset_index),
        "sample_rate": sr,
        "n_harmonics": n_harmonics,
        "clip_count": clip_count,
        "frame_count": len(all_profiles),
        "harmonic_weights": [round(float(v), 8) for v in profile],
        "median_f0_hz": round(float(np.median(f0_values)), 4),
        "p10_f0_hz": round(float(np.percentile(f0_values, 10)), 4),
        "p90_f0_hz": round(float(np.percentile(f0_values, 90)), 4),
        "median_rms": round(float(np.median(rms_values)), 6),
        "p90_rms": round(float(np.percentile(rms_values, 90)), 6),
        "renderer": "continuous_harmonic_timbre_v1",
        "limitations": [
            "This is a lightweight trained timbre model, not DDSP/neural vocoding.",
            "It renders continuous MIDI-controlled humming and avoids per-note sample splicing.",
            "Human listening remains the quality gate.",
        ],
    }
    model_json = out_dir / "hum_timbre_model.json"
    model_json.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
    return TimbreTrainResult(
        model_json=str(model_json),
        dataset_index=str(dataset_index),
        clip_count=clip_count,
        frame_count=len(all_profiles),
        harmonic_count=n_harmonics,
    )


def _notes_to_curves(
    notes: list[dict[str, Any]],
    *,
    sr: int,
    transpose_semitones: float,
    portamento_s: float,
) -> tuple[np.ndarray, np.ndarray]:
    duration_s = max(float(n["start"]) + float(n["duration"]) for n in notes) + 0.12
    n_samples = int(math.ceil(duration_s * sr))
    f0 = np.zeros(n_samples, dtype=np.float32)
    amp = np.zeros(n_samples, dtype=np.float32)
    for note in notes:
        start = int(round(float(note["start"]) * sr))
        end = min(n_samples, int(round((float(note["start"]) + float(note["duration"])) * sr)))
        if end <= start:
            continue
        base_midi = float(note["midi"]) + transpose_semitones
        pitch_bend_points = list(note.get("pitch_bend_points", []) or [])
        if pitch_bend_points:
            point_times = [0.0]
            point_cents = [0.0]
            for point in pitch_bend_points:
                t = max(0.0, min(float(note["duration"]), float(point.get("t", 0.0))))
                point_times.append(t)
                point_cents.append(float(point.get("bend_cents", 0.0)))
            point_times.append(float(note["duration"]))
            point_cents.append(point_cents[-1])
            order = np.argsort(np.asarray(point_times, dtype=np.float32))
            point_times = [point_times[int(i)] for i in order]
            point_cents = [point_cents[int(i)] for i in order]
            local_t = np.arange(end - start, dtype=np.float32) / sr
            bend_cents = np.interp(local_t, point_times, point_cents).astype(np.float32)
            midi_curve = base_midi + (bend_cents / 100.0)
            f0[start:end] = np.asarray([midi_to_hz(v) for v in midi_curve], dtype=np.float32)
        else:
            hz = midi_to_hz(base_midi)
            f0[start:end] = hz
        amp[start:end] = 1.0

    glide = max(1, int(portamento_s * sr))
    if glide > 1:
        kernel = np.hanning(glide * 2 + 1).astype(np.float32)
        kernel /= np.sum(kernel)
        voiced = amp > 0
        filled = f0.copy()
        nonzero = np.where(filled > 0)[0]
        if len(nonzero):
            filled[: nonzero[0]] = filled[nonzero[0]]
            filled[nonzero[-1] + 1 :] = filled[nonzero[-1]]
            missing = filled <= 0
            filled[missing] = np.interp(np.where(missing)[0], nonzero, filled[nonzero])
            smoothed = np.convolve(filled, kernel, mode="same")
            f0[voiced] = smoothed[voiced]
        amp = np.convolve(amp, kernel, mode="same")
        amp = np.clip(amp, 0.0, 1.0)
    return f0, amp


def render_trained_hum(
    model_json: Path,
    out_dir: Path,
    *,
    melody_json: Path | None = None,
    midi_path: Path | None = None,
    max_melody_duration_s: float | None = None,
    midi_track_name: str | None = None,
    midi_min_note_duration_s: float = 0.28,
    transpose_semitones: float = 0.0,
    portamento_s: float = 0.055,
) -> TimbreRenderResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    model = _read_json(model_json)
    sr = int(model["sample_rate"])
    if midi_path and melody_json:
        raise ValueError("Use either midi_path or melody_json, not both")
    melody = (
        _load_midi_melody(
            midi_path,
            max_duration_s=max_melody_duration_s,
            preferred_track_name=midi_track_name,
            legato=True,
            min_note_duration_s=midi_min_note_duration_s,
        )
        if midi_path
        else _load_melody(melody_json)
    )
    notes = list(melody["notes"])
    pitch_bend_note_count = sum(1 for note in notes if note.get("pitch_bend_points"))
    f0, amp = _notes_to_curves(
        notes,
        sr=sr,
        transpose_semitones=transpose_semitones,
        portamento_s=portamento_s,
    )

    weights = np.asarray(model["harmonic_weights"], dtype=np.float32)
    weights = weights / np.sum(weights)
    phase = np.cumsum(2.0 * np.pi * f0 / sr).astype(np.float32)
    y = np.zeros_like(f0, dtype=np.float32)
    for harmonic, weight in enumerate(weights, start=1):
        # Closed-mouth hum: strong fundamental/body, gently reduced bright partials.
        y += float(weight) * np.sin(harmonic * phase).astype(np.float32)
    y *= amp

    body_sos = butter(2, [90, 2600], btype="bandpass", fs=sr, output="sos")
    y = sosfiltfilt(body_sos, y).astype(np.float32)
    rng = np.random.default_rng(43)
    breath = rng.standard_normal(len(y)).astype(np.float32)
    breath_sos = butter(2, [650, 2200], btype="bandpass", fs=sr, output="sos")
    breath = sosfiltfilt(breath_sos, breath).astype(np.float32)
    if np.max(np.abs(breath)) > 0:
        breath /= np.max(np.abs(breath))
    y += 0.003 * breath * amp

    peak = float(np.max(np.abs(y))) if len(y) else 0.0
    if peak > 0:
        y = 0.7 * y / peak
    peak = float(np.max(np.abs(y))) if len(y) else 0.0
    output_wav = out_dir / "trained_hum.wav"
    sf.write(output_wav, y, sr)

    manifest_path = out_dir / "render_manifest.json"
    manifest = {
        "schema": "hum.trained_render.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_json": str(model_json),
        "midi_path": str(midi_path) if midi_path else None,
        "melody_json": str(melody_json) if melody_json else None,
        "selected_midi_instrument": melody.get("instrument"),
        "midi_min_note_duration_s": midi_min_note_duration_s,
        "transpose_semitones": transpose_semitones,
        "portamento_s": portamento_s,
        "pitch_bend_note_count": pitch_bend_note_count,
        "pitch_bend_control": "pitch_bend_points_interpolated_to_f0_curve",
        "note_count": len(notes),
        "duration_s": round(len(y) / sr, 4),
        "peak": round(peak, 6),
        "renderer": model.get("renderer"),
        "limitations": model.get("limitations", []),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return TimbreRenderResult(
        output_wav=str(output_wav),
        render_manifest=str(manifest_path),
        model_json=str(model_json),
        note_count=len(notes),
        duration_s=round(len(y) / sr, 4),
        peak=round(peak, 6),
    )
