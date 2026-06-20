"""Closed-mouth hum guide from vocal stem + MIDI melody (local path-B renderer)."""

from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np
import pretty_midi
import soundfile as sf
from scipy.signal import butter, fftconvolve, sosfiltfilt

from .midi_to_hum import build_f0_from_midi, midi_to_hz, smooth_voicing, synthesize_hum


def filter_midi_notes(midi_path: Path, min_pitch: int = 48) -> Path:
    pm = pretty_midi.PrettyMIDI(str(midi_path))
    for inst in pm.instruments:
        inst.notes = [n for n in inst.notes if n.pitch >= min_pitch]
    out = midi_path.with_name(midi_path.stem + "_filtered.mid")
    pm.write(str(out))
    return out



def _bandpass(y: np.ndarray, sr: int, lo: float, hi: float) -> np.ndarray:
    sos = butter(4, [lo, hi], btype="band", fs=sr, output="sos")
    return sosfiltfilt(sos, y).astype(np.float32)


def _extract_vocal_f0(y: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    hop = 512
    f0_frames, voiced_flag, _ = librosa.pyin(
        y,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C6"),
        sr=sr,
        hop_length=hop,
    )
    times = librosa.times_like(f0_frames, sr=sr, hop_length=hop)
    sample_t = np.arange(len(y), dtype=np.float64) / sr
    f0 = np.interp(sample_t, times, np.nan_to_num(f0_frames, nan=0.0)).astype(np.float32)
    voiced_f = np.interp(sample_t, times, voiced_flag.astype(np.float64)).astype(np.float32)
    voiced = (voiced_f > 0.5) & (f0 > 1.0)
    return f0, voiced


def _merge_f0(
    midi_f0: np.ndarray,
    vocal_f0: np.ndarray,
    vocal_voiced: np.ndarray,
    *,
    vocal_weight: float = 0.35,
) -> np.ndarray:
    out = midi_f0.copy()
    midi_active = midi_f0 > 1.0
    use_vocal = vocal_voiced & (vocal_f0 > 1.0)
    blend = use_vocal & midi_active
    out[blend] = (1.0 - vocal_weight) * midi_f0[blend] + vocal_weight * vocal_f0[blend]
    solo_vocal = use_vocal & ~midi_active
    out[solo_vocal] = vocal_f0[solo_vocal]
    return out


def _rms_envelope(y: np.ndarray, sr: int, win_ms: float = 40.0) -> np.ndarray:
    win = max(1, int(sr * win_ms / 1000.0))
    sq = y.astype(np.float64) ** 2
    kernel = np.ones(win, dtype=np.float64) / win
    env = np.sqrt(np.maximum(fftconvolve(sq, kernel, mode="same"), 0.0))
    peak = float(env.max() + 1e-9)
    return (env / peak).astype(np.float32)


def _synthesize_from_f0(
    f0: np.ndarray,
    envelope: np.ndarray,
    sr: int,
    *,
    vibrato_hz: float = 5.0,
    vibrato_depth: float = 0.003,
) -> np.ndarray:
    n = len(f0)
    t = np.arange(n, dtype=np.float32) / sr
    voiced = f0 > 1.0
    env = smooth_voicing(voiced, sr) * np.clip(envelope, 0.05, 1.0)

    f0_vib = f0 * (1.0 + vibrato_depth * np.sin(2.0 * np.pi * vibrato_hz * t))
    f0_vib[~voiced] = 0.0
    phase = np.cumsum(2.0 * np.pi * f0_vib / sr).astype(np.float32)

    y = np.zeros(n, dtype=np.float32)
    for h in range(1, 7):
        partial = h * f0_vib
        nasal = np.exp(-0.5 * ((partial - 280.0) / 200.0) ** 2)
        chest = 0.25 * np.exp(-0.5 * ((partial - 900.0) / 450.0) ** 2)
        amp = (nasal + chest + 0.06) / h
        y += amp.astype(np.float32) * np.sin(h * phase)

    rng = np.random.default_rng(11)
    breath = 0.012 * rng.standard_normal(n).astype(np.float32)
    y = (y + breath) * env

    edge = int(0.02 * sr)
    if n > 2 * edge:
        fade = np.linspace(0.0, 1.0, edge, dtype=np.float32)
        y[:edge] *= fade
        y[-edge:] *= fade

    peak = float(np.max(np.abs(y)) + 1e-9)
    return (0.88 * y / peak).astype(np.float32)


def render_neural_hum(
    vocals_path: Path,
    midi_path: Path,
    out_wav: Path,
    *,
    sr: int = 44100,
    vocal_blend: float = 0.22,
) -> Path:
    """Build a closed-mouth hum guide: MIDI melody + vocal timing/envelope."""
    y, file_sr = sf.read(vocals_path, always_2d=False)
    if y.ndim > 1:
        y = y.mean(axis=1)
    if file_sr != sr:
        y = librosa.resample(y.astype(np.float32), orig_sr=file_sr, target_sr=sr)

    y = y.astype(np.float32)
    y_hum_band = _bandpass(y, sr, 180.0, 2800.0)

    filtered_midi = filter_midi_notes(Path(midi_path))
    midi_f0, _ = build_f0_from_midi(str(filtered_midi), sr)
    n = len(y)
    if len(midi_f0) < n:
        midi_f0 = np.pad(midi_f0, (0, n - len(midi_f0)))
    else:
        midi_f0 = midi_f0[:n]

    vocal_f0, vocal_voiced = _extract_vocal_f0(y, sr)
    merged_f0 = _merge_f0(midi_f0, vocal_f0, vocal_voiced)

    envelope = _rms_envelope(y_hum_band, sr)
    synth = _synthesize_from_f0(merged_f0, envelope, sr)

    # Keep a little band-limited vocal texture for breath/naturalness.
    vocal_hum = y_hum_band * envelope
    vocal_peak = float(np.max(np.abs(vocal_hum)) + 1e-9)
    vocal_hum = 0.35 * vocal_hum / vocal_peak

    mix = (1.0 - vocal_blend) * synth + vocal_blend * vocal_hum
    peak = float(np.max(np.abs(mix)) + 1e-9)
    mix = (0.9 * mix / peak).astype(np.float32)

    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out_wav, mix, sr)
    return out_wav


def prepare_ace_bundle(
    midi_path: Path,
    out_dir: Path,
    *,
    syllable: str = "mmm",
) -> dict:
    """Write ACE Studio import hints: melody MIDI + closed-mouth lyric map."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pm = pretty_midi.PrettyMIDI(str(midi_path))
    ace_midi = out_dir / "melody.mid"
    pm.write(str(ace_midi))

    lines: list[str] = []
    notes = sorted(
        (n for inst in pm.instruments if not inst.is_drum for n in inst.notes),
        key=lambda n: n.start,
    )
    for note in notes:
        dur = max(0.08, note.end - note.start)
        lines.append(f"{syllable}\t{note.start:.3f}\t{dur:.3f}\t{note.pitch}")

    lyrics_path = out_dir / "ace_lyrics.tsv"
    lyrics_path.write_text("syllable\tstart_s\tdur_s\tmidi\n" + "\n".join(lines) + "\n")

    readme = out_dir / "ACE_EXPORT.md"
    readme.write_text(
        """# ACE Studio export (path B)

1. Import `melody.mid` into ACE Studio.
2. Set lyrics to closed-mouth syllables (`mmm`, `hm`, `ng`) using `ace_lyrics.tsv` timing.
3. Use a neutral stock voice or your cloned ACE voice.
4. Export **dry vocal only** as `source_hum.wav` (no reverb, no backing).
5. Run:

```bash
./run.sh add --song <segment.wav> --source-hum ./source_hum.wav \\
  --source-hum-renderer ace --start ... --duration ...
```
"""
    )
    return {
        "midi": str(ace_midi),
        "lyrics": str(lyrics_path),
        "readme": str(readme),
        "note_count": len(notes),
    }
