"""Sample-based female humming renderer for fast viability checks."""

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


@dataclass(frozen=True)
class RenderResult:
    out_dir: str
    output_wav: str
    render_manifest: str
    dataset_index: str
    sample_count: int
    note_count: int
    duration_s: float
    peak: float

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_MELODY = {
    "schema": "hum.render_melody.v1",
    "notes": [
        {"start": 0.00, "midi": 69, "duration": 0.55},
        {"start": 0.62, "midi": 72, "duration": 0.38},
        {"start": 1.06, "midi": 71, "duration": 0.46},
        {"start": 1.60, "midi": 67, "duration": 0.58},
        {"start": 2.28, "midi": 69, "duration": 0.80},
    ],
    "style": ["female_hum", "soft", "sample_based_mvp"],
}


def midi_to_hz(midi: float) -> float:
    return 440.0 * (2.0 ** ((float(midi) - 69.0) / 12.0))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_summary(active: list[dict[str, Any]], frame_step: float) -> tuple[float, float, float, float] | None:
    start = float(active[0].get("t", 0.0))
    end = float(active[-1].get("t", start)) + frame_step
    f0_values = np.asarray([float(v["f0_hz"]) for v in active], dtype=np.float32)
    median_f0 = float(np.median(f0_values))
    cents = 1200.0 * np.log2(np.maximum(f0_values, 1e-6) / median_f0)
    return start, end, median_f0, float(np.std(cents))


def _extract_voiced_runs(frames: list[dict[str, Any]], min_duration_s: float) -> list[tuple[float, float, float, float]]:
    runs: list[tuple[float, float, float, float]] = []
    active: list[dict[str, Any]] = []
    previous_t: float | None = None
    frame_step = 0.012
    for frame in frames:
        t = float(frame.get("t", 0.0))
        f0 = float(frame.get("f0_hz", 0.0) or 0.0)
        if previous_t is not None:
            frame_step = max(0.001, t - previous_t)
        previous_t = t

        if f0 > 0.0:
            active.append(frame)
            continue

        if active:
            summary = _run_summary(active, frame_step)
            if summary and summary[1] - summary[0] >= min_duration_s:
                runs.append(summary)
            active = []

    if active:
        summary = _run_summary(active, frame_step)
        if summary and summary[1] - summary[0] >= min_duration_s:
            runs.append(summary)
    return runs


def _load_sample_library(
    dataset_index: Path,
    *,
    sr: int,
    carrier: str,
    min_sample_duration_s: float,
    max_samples: int,
) -> list[dict[str, Any]]:
    index = _read_json(dataset_index)
    samples: list[dict[str, Any]] = []
    for item in index.get("items", []):
        wav_path = Path(item.get("audio_path", "")) if carrier == "original" else Path(item.get("neutral_hum_wav", ""))
        melody_path = Path(item.get("melody_json", ""))
        if not wav_path.exists() or not melody_path.exists():
            continue

        melody = _read_json(melody_path)
        runs = _extract_voiced_runs(melody.get("frames", []), min_sample_duration_s)
        if not runs:
            continue

        y, actual_sr = librosa.load(wav_path, sr=sr, mono=True)
        for run_index, (start_s, end_s, median_f0, f0_std_cents) in enumerate(runs):
            start_i = max(0, int(round(start_s * actual_sr)))
            end_i = min(len(y), int(round(end_s * actual_sr)))
            segment = y[start_i:end_i].astype(np.float32)
            if len(segment) < int(min_sample_duration_s * actual_sr):
                continue
            peak = float(np.max(np.abs(segment))) if len(segment) else 0.0
            if peak < 0.02 or median_f0 <= 0.0:
                continue
            samples.append(
                {
                    "source_id": item.get("id", wav_path.stem),
                    "source_wav": str(wav_path),
                    "carrier": carrier,
                    "run_index": run_index,
                    "start_s": round(start_s, 4),
                    "end_s": round(end_s, 4),
                    "duration_s": round((end_i - start_i) / actual_sr, 4),
                    "median_f0_hz": round(median_f0, 4),
                    "f0_std_cents": round(f0_std_cents, 4),
                    "audio": segment,
                    "peak": peak,
                }
            )
            if len(samples) >= max_samples:
                return samples
    return samples


def _load_melody(melody_json: Path | None) -> dict[str, Any]:
    if melody_json is None:
        return DEFAULT_MELODY
    payload = _read_json(melody_json)
    if "notes" not in payload:
        raise ValueError(f"Melody JSON must contain a notes list: {melody_json}")
    return payload


def _select_midi_instrument(candidate_instruments: list[Any], preferred_name: str | None) -> Any:
    if preferred_name:
        preferred = preferred_name.lower()
        for instrument in candidate_instruments:
            if preferred in (instrument.name or "").lower():
                return instrument
    for token in ("melody", "lead", "vocal", "voice"):
        for instrument in candidate_instruments:
            if token in (instrument.name or "").lower():
                return instrument
    return max(candidate_instruments, key=lambda inst: len(inst.notes))


def _load_midi_melody(
    midi_path: Path,
    *,
    max_duration_s: float | None = None,
    preferred_track_name: str | None = None,
    legato: bool = True,
    min_note_duration_s: float = 0.18,
    target_tempo_bpm: float | None = None,
    swing_ratio: float = 0.0,
    pitch_bend_range_semitones: float = 2.0,
) -> dict[str, Any]:
    try:
        import pretty_midi
    except ImportError as exc:
        raise RuntimeError("pretty-midi is required for MIDI melody input") from exc

    midi = pretty_midi.PrettyMIDI(str(midi_path))
    tempo_times, tempos = midi.get_tempo_changes()
    source_tempo_bpm = float(tempos[0]) if len(tempos) else None
    candidate_instruments = [inst for inst in midi.instruments if not inst.is_drum and inst.notes]
    if not candidate_instruments:
        raise ValueError(f"MIDI contains no non-drum notes: {midi_path}")

    instrument = _select_midi_instrument(candidate_instruments, preferred_track_name)
    notes = []
    first_start = min(note.start for note in instrument.notes)
    sorted_notes = sorted(instrument.notes, key=lambda n: (n.start, -n.pitch))
    bend_events = sorted(getattr(instrument, "pitch_bends", []), key=lambda b: b.time)
    for index, note in enumerate(sorted_notes):
        start = float(note.start - first_start)
        end = float(note.end - first_start)
        if legato and index + 1 < len(sorted_notes):
            next_start = float(sorted_notes[index + 1].start - first_start)
            if next_start > start:
                end = max(end, next_start - 0.012)
        duration = end - start
        if duration <= 0.045:
            continue
        if max_duration_s is not None and start >= max_duration_s:
            break
        if max_duration_s is not None and start + duration > max_duration_s:
            duration = max(0.03, max_duration_s - start)
        pitch_bend_points = []
        for bend in bend_events:
            bend_time = float(bend.time - first_start)
            if start <= bend_time <= start + duration:
                bend_semitones = (float(bend.pitch) / 8192.0) * float(pitch_bend_range_semitones)
                pitch_bend_points.append(
                    {
                        "t": round(bend_time - start, 4),
                        "bend_cents": round(bend_semitones * 100.0, 4),
                        "pitchwheel": int(bend.pitch),
                    }
                )
        notes.append(
            {
                "start": round(start, 4),
                "midi": int(note.pitch),
                "duration": round(duration, 4),
                "velocity": int(note.velocity),
                "pitch_bend_points": pitch_bend_points,
            }
        )
    if not notes:
        raise ValueError(f"MIDI melody extraction produced no notes: {midi_path}")
    if target_tempo_bpm and source_tempo_bpm:
        scale = source_tempo_bpm / float(target_tempo_bpm)
        for note in notes:
            note["start"] = round(float(note["start"]) * scale, 4)
            note["duration"] = round(float(note["duration"]) * scale, 4)
    if swing_ratio > 0.0:
        notes = _apply_swing(notes, tempo_bpm=target_tempo_bpm or source_tempo_bpm or 192.0, swing_ratio=swing_ratio)
    if min_note_duration_s > 0:
        notes = _simplify_short_midi_notes(notes, min_note_duration_s)
    return {
        "schema": "hum.render_melody.v1",
        "source_midi": str(midi_path),
        "instrument": instrument.name or f"program_{instrument.program}",
        "source_tempo_bpm": round(source_tempo_bpm, 4) if source_tempo_bpm else None,
        "target_tempo_bpm": target_tempo_bpm,
        "swing_ratio": swing_ratio,
        "legato": legato,
        "min_note_duration_s": min_note_duration_s,
        "pitch_bend_range_semitones": pitch_bend_range_semitones,
        "notes": notes,
    }


def _apply_swing(notes: list[dict[str, Any]], *, tempo_bpm: float, swing_ratio: float) -> list[dict[str, Any]]:
    quarter_s = 60.0 / float(tempo_bpm)
    eighth_s = quarter_s / 2.0
    ratio = max(0.5, min(0.75, float(swing_ratio)))
    swung: list[dict[str, Any]] = []
    for note in notes:
        start = float(note["start"])
        duration = float(note["duration"])
        grid = round(start / eighth_s)
        quantized = grid * eighth_s
        if abs(start - quantized) <= eighth_s * 0.32:
            beat = grid // 2
            is_offbeat = grid % 2 == 1
            new_start = beat * quarter_s + (ratio * quarter_s if is_offbeat else 0.0)
            next_grid = round((start + duration) / eighth_s)
            next_beat = next_grid // 2
            next_is_offbeat = next_grid % 2 == 1
            new_end = (
                next_beat * quarter_s + (ratio * quarter_s if next_is_offbeat else 0.0)
                if next_grid > grid
                else new_start + duration
            )
            duration = max(0.045, new_end - new_start)
            start = new_start
        out = dict(note)
        out["start"] = round(start, 4)
        out["duration"] = round(duration, 4)
        swung.append(out)
    return sorted(swung, key=lambda n: (float(n["start"]), float(n["midi"])))


def _simplify_short_midi_notes(notes: list[dict[str, Any]], min_note_duration_s: float) -> list[dict[str, Any]]:
    simplified: list[dict[str, Any]] = []
    group: list[dict[str, Any]] = []
    group_start: float | None = None
    group_end = 0.0

    def flush() -> None:
        nonlocal group, group_start, group_end
        if not group or group_start is None:
            return
        # Use the duration-weighted pitch. This smooths fast ornamental runs into
        # a hummable contour instead of emitting a machine-gun series of splices.
        weights = np.asarray([float(n["duration"]) for n in group], dtype=np.float32)
        pitches = np.asarray([float(n["midi"]) for n in group], dtype=np.float32)
        midi = int(round(float(np.average(pitches, weights=np.maximum(weights, 1e-4)))))
        simplified.append(
            {
                "start": round(group_start, 4),
                "midi": midi,
                "duration": round(max(group_end - group_start, min_note_duration_s), 4),
                "source_note_count": len(group),
                "pitch_bend_points": [
                    {
                        **point,
                        "t": round(float(note["start"]) + float(point["t"]) - group_start, 4),
                    }
                    for note in group
                    for point in note.get("pitch_bend_points", [])
                    if group_start <= float(note["start"]) + float(point["t"]) <= group_end
                ],
            }
        )
        group = []
        group_start = None
        group_end = 0.0

    for note in notes:
        start = float(note["start"])
        end = start + float(note["duration"])
        if group_start is None:
            group_start = start
        group.append(note)
        group_end = max(group_end, end)
        if group_end - group_start >= min_note_duration_s:
            flush()
    flush()
    return simplified


def _normalize_notes(notes: list[dict[str, Any]], *, rest_s: float) -> list[dict[str, float]]:
    normalized: list[dict[str, float]] = []
    cursor = 0.0
    for note in notes:
        duration = float(note.get("duration", note.get("duration_s", 0.0)) or 0.0)
        if duration <= 0.0:
            continue
        midi = float(note.get("midi", note.get("note", 69)))
        start = float(note["start"]) if "start" in note else cursor
        normalized.append({"start": start, "midi": midi, "duration": duration})
        if "pitch_bend_points" in note:
            normalized[-1]["pitch_bend_points"] = note["pitch_bend_points"]
        cursor = max(cursor, start + duration + rest_s)
    if not normalized:
        raise ValueError("Melody contains no positive-duration notes")
    return normalized


def _fit_audio_to_duration(audio: np.ndarray, target_samples: int) -> np.ndarray:
    if target_samples <= 0:
        return np.zeros(0, dtype=np.float32)
    if len(audio) < 256:
        repeats = int(math.ceil(256 / max(len(audio), 1)))
        audio = np.tile(audio, repeats)
    if len(audio) < target_samples * 0.5:
        repeats = int(math.ceil((target_samples * 0.8) / max(len(audio), 1)))
        audio = np.tile(audio, max(1, repeats))

    rate = max(0.125, min(8.0, len(audio) / float(target_samples)))
    stretched = librosa.effects.time_stretch(audio.astype(np.float32), rate=rate)
    if len(stretched) < target_samples:
        stretched = np.pad(stretched, (0, target_samples - len(stretched)))
    return stretched[:target_samples].astype(np.float32)


def _fade(audio: np.ndarray, sr: int, fade_s: float = 0.045) -> np.ndarray:
    out = audio.astype(np.float32, copy=True)
    edge = min(int(sr * fade_s), len(out) // 2)
    if edge > 0:
        fade_in = np.sin(np.linspace(0.0, np.pi / 2.0, edge, dtype=np.float32)) ** 2
        fade_out = np.cos(np.linspace(0.0, np.pi / 2.0, edge, dtype=np.float32)) ** 2
        out[:edge] *= fade_in
        out[-edge:] *= fade_out
    return out


def _mix_note(output: np.ndarray, note_audio: np.ndarray, start_i: int) -> None:
    end_i = min(len(output), start_i + len(note_audio))
    if end_i <= start_i:
        return
    existing = output[start_i:end_i]
    incoming = note_audio[: end_i - start_i]
    output[start_i:end_i] = existing + incoming


def _apply_tone(audio: np.ndarray, sr: int, tone: str) -> np.ndarray:
    if tone == "neutral":
        return audio.astype(np.float32)
    if tone not in {"dark", "low_breathy"}:
        raise ValueError("tone must be 'neutral', 'dark', or 'low_breathy'")

    # Darken the sample-spliced render: keep the low vocal body and suppress
    # bright artifacts that make the output read as synthetic.
    sos = butter(2, 2800, btype="lowpass", fs=sr, output="sos")
    darker = sosfiltfilt(sos, audio).astype(np.float32)
    body_sos = butter(2, [140, 620], btype="bandpass", fs=sr, output="sos")
    body = sosfiltfilt(body_sos, audio).astype(np.float32)
    shaped = 0.86 * darker + 0.22 * body
    if tone == "low_breathy":
        rng = np.random.default_rng(31)
        breath = rng.standard_normal(len(audio)).astype(np.float32)
        breath_sos = butter(2, [900, 2600], btype="bandpass", fs=sr, output="sos")
        breath = sosfiltfilt(breath_sos, breath).astype(np.float32)
        if np.max(np.abs(breath)) > 0:
            breath /= np.max(np.abs(breath))
        env = np.clip(np.abs(audio) * 4.0, 0.0, 1.0)
        shaped = shaped + 0.004 * breath * env
    return shaped.astype(np.float32)


def render_female_hum(
    dataset_index: Path,
    out_dir: Path,
    *,
    melody_json: Path | None = None,
    midi_path: Path | None = None,
    max_melody_duration_s: float | None = None,
    midi_track_name: str | None = None,
    midi_legato: bool = True,
    midi_min_note_duration_s: float = 0.18,
    midi_tempo_bpm: float | None = None,
    midi_swing_ratio: float = 0.0,
    sr: int = 22050,
    carrier: str = "original",
    transpose_semitones: float = 0.0,
    tone: str = "neutral",
    rest_s: float = 0.06,
    min_sample_duration_s: float = 0.25,
    max_samples: int = 512,
    min_stretch_ratio: float = 0.65,
    max_stretch_ratio: float = 1.55,
) -> RenderResult:
    if carrier not in {"original", "neutral"}:
        raise ValueError("carrier must be 'original' or 'neutral'")
    out_dir.mkdir(parents=True, exist_ok=True)
    samples = _load_sample_library(
        dataset_index,
        sr=sr,
        carrier=carrier,
        min_sample_duration_s=min_sample_duration_s,
        max_samples=max_samples,
    )
    if not samples:
        raise ValueError(f"No usable voiced samples found in dataset index: {dataset_index}")

    if melody_json is not None and midi_path is not None:
        raise ValueError("Use either melody_json or midi_path, not both")
    melody = (
        _load_midi_melody(
            midi_path,
            max_duration_s=max_melody_duration_s,
            preferred_track_name=midi_track_name,
            legato=midi_legato,
            min_note_duration_s=midi_min_note_duration_s,
            target_tempo_bpm=midi_tempo_bpm,
            swing_ratio=midi_swing_ratio,
        )
        if midi_path
        else _load_melody(melody_json)
    )
    notes = _normalize_notes(list(melody.get("notes", [])), rest_s=rest_s)

    duration_s = max(note["start"] + note["duration"] for note in notes) + 0.08
    output = np.zeros(int(math.ceil(duration_s * sr)), dtype=np.float32)
    rendered_notes: list[dict[str, Any]] = []

    reuse_counts: dict[str, int] = {}
    for note_index, note in enumerate(notes):
        rendered_midi = note["midi"] + transpose_semitones
        target_hz = midi_to_hz(rendered_midi)
        sample = min(
            samples,
            key=lambda s: (
                abs(12.0 * math.log2(float(s["median_f0_hz"]) / target_hz))
                + (min(float(s.get("f0_std_cents", 0.0)), 600.0) / 90.0) ** 1.35
                + abs(math.log(max(float(s["duration_s"]), 1e-3) / max(float(note["duration"]), 1e-3))) * 1.4
                + (
                    4.0
                    if not (
                        min_stretch_ratio
                        <= float(s["duration_s"]) / max(float(note["duration"]), 1e-3)
                        <= max_stretch_ratio
                    )
                    else 0.0
                )
                + 0.2 * reuse_counts.get(str(s["source_id"]), 0)
            ),
        )
        reuse_counts[str(sample["source_id"])] = reuse_counts.get(str(sample["source_id"]), 0) + 1
        n_steps = 12.0 * math.log2(target_hz / float(sample["median_f0_hz"]))
        shifted = librosa.effects.pitch_shift(sample["audio"], sr=sr, n_steps=n_steps)
        target_samples = int(round(note["duration"] * sr))
        fitted = _fade(_fit_audio_to_duration(shifted, target_samples), sr)
        note_rms = float(np.sqrt(np.mean(np.square(fitted)))) if len(fitted) else 0.0
        if note_rms > 0.0:
            fitted = fitted * min(1.0, 0.18 / note_rms)

        start_i = int(round(note["start"] * sr))
        _mix_note(output, fitted, start_i)
        rendered_notes.append(
            {
                "note_index": note_index,
                "start_s": round(note["start"], 4),
                "duration_s": round(note["duration"], 4),
                "input_midi": round(note["midi"], 4),
                "midi": round(rendered_midi, 4),
                "target_f0_hz": round(target_hz, 4),
                "source_id": sample["source_id"],
                "source_wav": sample["source_wav"],
                "carrier": sample["carrier"],
                "source_run_index": sample["run_index"],
                "source_start_s": sample["start_s"],
                "source_end_s": sample["end_s"],
                "source_duration_s": sample["duration_s"],
                "source_median_f0_hz": sample["median_f0_hz"],
                "source_f0_std_cents": sample["f0_std_cents"],
                "pitch_shift_semitones": round(n_steps, 4),
                "time_stretch_ratio": round(float(sample["duration_s"]) / float(note["duration"]), 4),
            }
        )

    peak = float(np.max(np.abs(output))) if len(output) else 0.0
    if peak > 0.0:
        output = 0.72 * output / peak
    output = _apply_tone(output, sr, tone)
    peak = float(np.max(np.abs(output))) if len(output) else 0.0
    if peak > 0.0:
        output = 0.72 * output / peak
    peak = float(np.max(np.abs(output))) if len(output) else 0.0

    output_wav = out_dir / "female_hum.wav"
    manifest_path = out_dir / "render_manifest.json"
    sf.write(output_wav, output, sr)

    if midi_path:
        melody_source = str(midi_path)
    elif melody_json:
        melody_source = str(melody_json)
    else:
        melody_source = "default"

    manifest = {
        "schema": "hum.sample_render.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_index": str(dataset_index),
        "melody_json": str(melody_json) if melody_json else None,
        "midi_path": str(midi_path) if midi_path else None,
        "midi_track_name": midi_track_name,
        "midi_legato": midi_legato,
        "midi_min_note_duration_s": midi_min_note_duration_s,
        "midi_tempo_bpm": midi_tempo_bpm,
        "midi_swing_ratio": midi_swing_ratio,
        "selected_midi_instrument": melody.get("instrument"),
        "melody_source": melody_source,
        "renderer": "sample_based_mvp",
        "carrier": carrier,
        "transpose_semitones": round(float(transpose_semitones), 4),
        "tone": tone,
        "sample_rate": sr,
        "sample_count": len(samples),
        "note_count": len(notes),
        "duration_s": round(len(output) / float(sr), 4),
        "peak": round(peak, 6),
        "notes": rendered_notes,
        "limitations": [
            "This is a viability baseline, not proof of Embry-like dynamic humming.",
            "Output quality requires human listening review before any cache publication.",
            "Samples are pitch-shifted/time-stretched carriers, so transitions may be stitched.",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return RenderResult(
        out_dir=str(out_dir),
        output_wav=str(output_wav),
        render_manifest=str(manifest_path),
        dataset_index=str(dataset_index),
        sample_count=len(samples),
        note_count=len(notes),
        duration_s=round(len(output) / float(sr), 4),
        peak=round(peak, 6),
    )
