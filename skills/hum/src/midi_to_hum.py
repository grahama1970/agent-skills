"""Synthesize a neutral 'mmm' guide track from MIDI melody notes."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pretty_midi
import soundfile as sf
from scipy.signal import fftconvolve


def midi_to_hz(note_number: int) -> float:
    return 440.0 * (2.0 ** ((note_number - 69) / 12.0))


def build_f0_from_midi(midi_path: str, sr: int, min_note_seconds: float = 0.06) -> tuple[np.ndarray, np.ndarray]:
    pm = pretty_midi.PrettyMIDI(midi_path)
    duration = pm.get_end_time()
    n = int(np.ceil(duration * sr)) + 1

    f0 = np.zeros(n, dtype=np.float32)
    velocity = np.zeros(n, dtype=np.float32)

    notes = []
    for inst in pm.instruments:
        if inst.is_drum:
            continue
        notes.extend(inst.notes)

    if not notes:
        raise ValueError(f"No pitched MIDI notes found in {midi_path}")

    for note in notes:
        if note.end - note.start < min_note_seconds:
            continue

        start = max(0, int(note.start * sr))
        end = min(n, int(note.end * sr))
        hz = midi_to_hz(note.pitch)
        vel = note.velocity / 127.0

        if start < end:
            replace = hz > f0[start:end]
            f0[start:end][replace] = hz
            velocity[start:end][replace] = vel

    return f0, velocity


def smooth_voicing(active: np.ndarray, sr: int, fade_ms: float = 12.0) -> np.ndarray:
    fade = max(8, int(sr * fade_ms / 1000.0))
    kernel = np.hanning(fade * 2 + 1)
    kernel /= kernel.sum()
    env = fftconvolve(active.astype(np.float32), kernel, mode="same")
    return np.clip(env, 0.0, 1.0)


def synthesize_hum(
    midi_path: str | Path,
    out_wav: str | Path,
    sr: int = 44100,
    vibrato_hz: float = 5.2,
    vibrato_depth: float = 0.004,
) -> Path:
    f0, velocity = build_f0_from_midi(str(midi_path), sr)
    n = len(f0)
    t = np.arange(n, dtype=np.float32) / sr

    voiced = f0 > 1.0
    env = smooth_voicing(voiced, sr)

    f0_vib = f0 * (1.0 + vibrato_depth * np.sin(2.0 * np.pi * vibrato_hz * t))
    f0_vib[~voiced] = 0.0

    phase = np.cumsum(2.0 * np.pi * f0_vib / sr).astype(np.float32)

    y = np.zeros(n, dtype=np.float32)
    for h in range(1, 9):
        partial_freq = h * f0_vib
        nasal_low = np.exp(-0.5 * ((partial_freq - 250.0) / 180.0) ** 2)
        nasal_mid = 0.35 * np.exp(-0.5 * ((partial_freq - 1100.0) / 500.0) ** 2)
        amp = (nasal_low + nasal_mid + 0.08) / h
        y += amp.astype(np.float32) * np.sin(h * phase)

    intensity = 0.55 + 0.45 * np.clip(velocity, 0.0, 1.0)
    y *= env * intensity

    rng = np.random.default_rng(7)
    y += 0.003 * rng.standard_normal(n).astype(np.float32) * env

    edge = int(0.025 * sr)
    if n > 2 * edge:
        fade_in = np.linspace(0.0, 1.0, edge, dtype=np.float32)
        fade_out = np.linspace(1.0, 0.0, edge, dtype=np.float32)
        y[:edge] *= fade_in
        y[-edge:] *= fade_out

    peak = float(np.max(np.abs(y)) + 1e-9)
    y = 0.85 * y / peak

    out_path = Path(out_wav)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out_path, y, sr)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--midi", required=True)
    parser.add_argument("--out", default="work/source_hum.wav")
    parser.add_argument("--sr", type=int, default=44100)
    args = parser.parse_args()
    path = synthesize_hum(args.midi, args.out, args.sr)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
