"""Fail-closed quality gates for guide hum before Seed-VC."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pretty_midi
import soundfile as sf

IMPORT_RENDERERS = {"ace", "suno_manual", "elevenlabs_manual", "real_hum"}
AUTO_RENDERERS = {"old_synth", "neural_hum", "acestep_api", "pixazo"}
DIAG_RENDERERS = {"vocal_stem_diag"}


@dataclass
class MidiMelodyMetrics:
    note_count: int
    pitch_min: int
    pitch_max: int
    pitch_span: int
    score: int

    def to_dict(self) -> dict:
        return asdict(self)


def _filter_pm_notes(pm: pretty_midi.PrettyMIDI, min_pitch: int) -> None:
    for inst in pm.instruments:
        inst.notes = [n for n in inst.notes if n.pitch >= min_pitch]


def analyze_midi(midi_path: Path, *, min_pitch: int = 0) -> MidiMelodyMetrics:
    pm = pretty_midi.PrettyMIDI(str(midi_path))
    if min_pitch:
        _filter_pm_notes(pm, min_pitch)

    notes = [
        n
        for inst in pm.instruments
        if not inst.is_drum
        for n in inst.notes
        if n.end - n.start >= 0.06
    ]
    if not notes:
        return MidiMelodyMetrics(0, 0, 0, 0, -999)
    lo = min(n.pitch for n in notes)
    hi = max(n.pitch for n in notes)
    span = hi - lo
    score = len(notes) + span
    if lo < 48:
        score -= 20
    return MidiMelodyMetrics(len(notes), lo, hi, span, score)


def validate_midi_for_hum(metrics: MidiMelodyMetrics, duration_s: float) -> list[str]:
    errors: list[str] = []
    min_notes = max(8, int(duration_s * 0.8))
    if metrics.note_count < min_notes:
        errors.append(
            f"MIDI too sparse: {metrics.note_count} notes for {duration_s:.1f}s (need >= {min_notes})"
        )
    if metrics.pitch_min and metrics.pitch_min < 48:
        errors.append(f"MIDI pitch floor too low: {metrics.pitch_min} (likely harmonic garbage)")
    if metrics.pitch_span < 5:
        errors.append(f"MIDI pitch span too narrow: {metrics.pitch_span} semitones")
    return errors


def validate_source_hum_wav(path: Path, *, min_duration_s: float = 3.0) -> tuple[list[str], dict]:
    y, sr = sf.read(path, always_2d=False)
    if y.ndim > 1:
        y = y.mean(axis=1)
    duration_s = len(y) / float(sr)
    peak = float(np.max(np.abs(y))) if len(y) else 0.0
    rms = float(np.sqrt(np.mean(np.square(y)))) if len(y) else 0.0

    metrics = {
        "duration_s": round(duration_s, 2),
        "sample_rate": sr,
        "peak": round(peak, 4),
        "rms": round(rms, 4),
    }
    errors: list[str] = []
    if duration_s < min_duration_s:
        errors.append(f"Guide hum too short: {duration_s:.1f}s")
    if peak < 0.01:
        errors.append("Guide hum is near-silent")
    if rms < 0.005:
        errors.append("Guide hum RMS too low to be a usable vocal performance")
    return errors, metrics


def normalize_renderer(name: str) -> str:
    aliases = {
        "midi_hum": "old_synth",
        "synth": "old_synth",
        "elevenlabs": "elevenlabs_manual",
        "eleven_labs": "elevenlabs_manual",
        "pixazo": "acestep_api",
        "ace_step": "acestep_api",
    }
    return aliases.get(name, name)


def renderer_requires_import(renderer: str) -> bool:
    return normalize_renderer(renderer) in IMPORT_RENDERERS
