#!/usr/bin/env python3
"""Deterministic articulated humming renderer for a monophonic MIDI Melody track.

Required third-party packages:
    numpy, scipy, pretty_midi, librosa, soundfile

The renderer never synthesizes the supplied syllable text.  Syllables are used only
as deterministic control labels for non-lexical articulation choices.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import math
import os
import platform
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import librosa
import numpy as np
import pretty_midi
import scipy
import soundfile as sf
from scipy import signal


RENDERER_NAME = "hawaiian_war_chant_articulated_psola_v1"
OUTPUT_FILENAMES = {
    "inventory": "sample_inventory_v1.json",
    "alignment": "syllable_note_alignment_v1.json",
    "timeline": "articulation_timeline_v1.json",
    "midi": "humanized_melody_v1.mid",
    "audio": "articulated_psola_dry_v1.wav",
    "manifest": "render_manifest_v1.json",
    "qa": "qa_metrics_v1.json",
    "review": "review_ab_v1.wav",
}
REQUIRED_TOKENS = (
    "hm",
    "m_held",
    "m",
    "ng",
    "oo",
    "hm_to_m",
    "m_gliss_up",
    "m_gliss_down",
    "breathy_m",
    "m_chant",
    "sigh",
    "breath",
)
VOICED_TOKENS = {
    "hm",
    "m_held",
    "m",
    "ng",
    "oo",
    "hm_to_m",
    "m_gliss_up",
    "m_gliss_down",
    "breathy_m",
    "m_chant",
    "sigh",
}
UNPITCHED_TOKENS = {"breath"}
GLISS_TOKENS = {"m_gliss_up", "m_gliss_down"}

DEFAULT_PHRASES = [
    ["Au", "we", "ta", "hu", "a", "la"],
    ["Ta", "hu", "wa", "i", "la", "a", "ta", "hu", "wa", "i", "wa", "i", "la"],
    ["e", "hu", "he", "ne", "la", "a", "pi", "li", "ko", "o", "lu", "a", "la"],
    ["pu", "tu", "tu", "i", "lu", "a", "i", "te", "to", "e", "la"],
    ["ha", "nu", "li", "po", "i", "ta", "pa", "a", "lai"],
]

TOKEN_ALIASES = {
    "hm": ("hm", "hm_short"),
    "m_held": ("m_held",),
    "m": ("m", "m_pulsed"),
    "ng": ("ng", "ng_held"),
    "oo": ("oo", "oo_soft"),
    "hm_to_m": ("hm_to_m",),
    "m_gliss_up": ("m_gliss_up", "hum_slide_up", "gliss_up"),
    "m_gliss_down": ("m_gliss_down", "hum_slide_down", "gliss_down"),
    "breathy_m": ("breathy_m",),
    "m_chant": ("m_chant", "chant_hum_low"),
    "sigh": ("sigh",),
    "breath": ("breath",),
}


@dataclass(frozen=True)
class SampleAsset:
    token: str
    path: str
    sha256: str
    original_sample_rate: int
    sample_rate: int
    channels: int
    frames: int
    duration_sec: float
    peak_dbfs: float
    rms_dbfs: float
    active_start_sample: int
    active_end_sample: int
    sustain_start_sample: int
    sustain_end_sample: int
    median_f0_hz: float | None
    f0_p10_hz: float | None
    f0_p90_hz: float | None
    voiced_fraction: float


@dataclass(frozen=True)
class NoteState:
    note_index: int
    pitch: int
    velocity: int
    start: float
    end: float


class RenderError(RuntimeError):
    pass


def finite_float(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def dbfs(value: float, floor_db: float = -120.0) -> float:
    if not math.isfinite(value) or value <= 0.0:
        return floor_db
    return max(floor_db, 20.0 * math.log10(value))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return finite_float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, set):
        return sorted(value)
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    raise TypeError(f"Not JSON serializable: {type(value)!r}")


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=json_default) + "\n",
        encoding="utf-8",
    )


def normalize_stem(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def normalize_syllable(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"[^a-z]", "", ascii_text.lower()) or "a"


def mono_float32(path: Path, target_sr: int | None = None) -> tuple[np.ndarray, int, int, int]:
    y, sr = sf.read(path, dtype="float32", always_2d=True)
    channels = int(y.shape[1])
    y_mono = np.mean(y, axis=1, dtype=np.float64).astype(np.float32)
    if target_sr is not None and int(sr) != int(target_sr):
        y_mono = librosa.resample(
            y_mono,
            orig_sr=int(sr),
            target_sr=int(target_sr),
            res_type="scipy",
        ).astype(np.float32)
        return y_mono, int(target_sr), int(sr), channels
    return y_mono, int(sr), int(sr), channels


def load_phrases(path: Path | None) -> tuple[list[list[str]], dict[str, Any]]:
    if path is None:
        phrases = copy.deepcopy(DEFAULT_PHRASES)
        return phrases, {"source": "hardcoded_default", "sha256": sha256_json(phrases)}

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw_phrases = raw.get("phrases") if isinstance(raw, dict) else raw
    if not isinstance(raw_phrases, list) or not raw_phrases:
        raise RenderError("Phrase JSON must be a non-empty list or {'phrases': [...]}.")

    phrases: list[list[str]] = []
    for item in raw_phrases:
        if isinstance(item, str):
            syllables = [s for s in re.split(r"\s+", item.strip()) if s]
        elif isinstance(item, list):
            syllables = [str(s).strip() for s in item if str(s).strip()]
        elif isinstance(item, dict):
            value = item.get("syllables", item.get("text"))
            if isinstance(value, str):
                syllables = [s for s in re.split(r"\s+", value.strip()) if s]
            elif isinstance(value, list):
                syllables = [str(s).strip() for s in value if str(s).strip()]
            else:
                raise RenderError(f"Unsupported phrase object: {item!r}")
        else:
            raise RenderError(f"Unsupported phrase entry: {item!r}")
        if not syllables:
            raise RenderError("Every phrase must contain at least one syllable.")
        phrases.append(syllables)

    return phrases, {
        "source": str(path.resolve()),
        "sha256": sha256_file(path),
        "normalized_sha256": sha256_json(phrases),
    }


def discover_sample_paths(sample_dir: Path) -> dict[str, Path]:
    wavs = sorted(sample_dir.rglob("*.wav"))
    if not wavs:
        raise RenderError(f"No WAV files found under {sample_dir}")

    by_stem: dict[str, list[Path]] = {}
    for path in wavs:
        by_stem.setdefault(normalize_stem(path.stem), []).append(path)

    result: dict[str, Path] = {}
    missing: list[str] = []
    for token in REQUIRED_TOKENS:
        candidates: list[Path] = []
        for alias in TOKEN_ALIASES[token]:
            candidates.extend(by_stem.get(normalize_stem(alias), []))
        unique = sorted(set(candidates), key=lambda p: (len(str(p)), str(p)))
        if not unique:
            missing.append(token)
        else:
            result[token] = unique[0]
    if missing:
        raise RenderError(f"Missing required articulation tokens: {', '.join(missing)}")
    return result


def estimate_active_and_sustain(y: np.ndarray, sr: int) -> tuple[int, int, int, int]:
    if len(y) == 0:
        raise RenderError("Encountered an empty WAV sample.")
    win = max(8, int(round(0.010 * sr)))
    kernel = np.ones(win, dtype=np.float64) / win
    env = np.sqrt(signal.fftconvolve(np.asarray(y, dtype=np.float64) ** 2, kernel, mode="same") + 1e-12)
    peak = float(np.max(env))
    threshold = max(10.0 ** (-55.0 / 20.0), peak * 0.04)
    active = np.flatnonzero(env >= threshold)
    if active.size:
        active_start = int(active[0])
        active_end = int(active[-1] + 1)
    else:
        active_start, active_end = 0, len(y)

    active_len = max(1, active_end - active_start)
    active_env = env[active_start:active_end]
    high = max(float(np.percentile(active_env, 80)), peak * 0.55)
    above = np.flatnonzero(active_env >= high)
    if above.size:
        sustain_start = active_start + int(above[0])
        sustain_end = active_start + int(above[-1] + 1)
    else:
        sustain_start = active_start + int(round(0.25 * active_len))
        sustain_end = active_start + int(round(0.75 * active_len))

    sustain_start = max(sustain_start, active_start + min(int(0.025 * sr), active_len // 4))
    sustain_end = min(sustain_end, active_end - min(int(0.025 * sr), active_len // 4))
    minimum = int(round(0.080 * sr))
    if sustain_end - sustain_start < minimum:
        center = (active_start + active_end) // 2
        half = min(active_len // 2, max(minimum // 2, 1))
        sustain_start = max(active_start, center - half)
        sustain_end = min(active_end, center + half)
    if sustain_end <= sustain_start:
        sustain_start, sustain_end = active_start, active_end
    return active_start, active_end, sustain_start, sustain_end


def estimate_f0_summary(y: np.ndarray, sr: int, active_start: int, active_end: int) -> tuple[float | None, float | None, float | None, float]:
    segment = np.asarray(y[active_start:active_end], dtype=np.float32)
    if len(segment) < 256 or float(np.max(np.abs(segment))) < 1e-4:
        return None, None, None, 0.0
    frame_length = 2048
    if len(segment) < frame_length:
        segment = np.pad(segment, (0, frame_length - len(segment)))
    hop = 256
    try:
        f0 = librosa.yin(
            segment,
            fmin=float(librosa.note_to_hz("C2")),
            fmax=float(librosa.note_to_hz("C7")),
            sr=sr,
            frame_length=frame_length,
            hop_length=hop,
        )
        rms = librosa.feature.rms(
            y=segment, frame_length=frame_length, hop_length=hop, center=True
        )[0]
        flatness = librosa.feature.spectral_flatness(
            y=segment, n_fft=frame_length, hop_length=hop, center=True
        )[0]
    except Exception:
        return None, None, None, 0.0
    count = min(len(f0), len(rms), len(flatness))
    f0, rms, flatness = f0[:count], rms[:count], flatness[:count]
    energy_floor = max(10.0 ** (-50.0 / 20.0), float(np.max(rms)) * 0.08)
    valid = np.isfinite(f0) & (rms >= energy_floor) & (flatness <= 0.45)
    voiced_fraction = float(np.mean(valid)) if count else 0.0
    if np.count_nonzero(valid) < 2 or voiced_fraction < 0.08:
        return None, None, None, voiced_fraction
    values = f0[valid]
    return (
        finite_float(np.median(values)),
        finite_float(np.percentile(values, 10)),
        finite_float(np.percentile(values, 90)),
        voiced_fraction,
    )


def analyze_samples(sample_paths: dict[str, Path], target_sr: int) -> tuple[dict[str, SampleAsset], dict[str, np.ndarray]]:
    assets: dict[str, SampleAsset] = {}
    audio: dict[str, np.ndarray] = {}
    for token in REQUIRED_TOKENS:
        path = sample_paths[token]
        y, sr, original_sr, channels = mono_float32(path, target_sr)
        y = signal.detrend(y, type="constant").astype(np.float32)
        active_start, active_end, sustain_start, sustain_end = estimate_active_and_sustain(y, sr)
        median_f0, f0_p10, f0_p90, voiced_fraction = estimate_f0_summary(y, sr, active_start, active_end)
        peak = float(np.max(np.abs(y))) if len(y) else 0.0
        rms = float(np.sqrt(np.mean(np.asarray(y, dtype=np.float64) ** 2) + 1e-15))
        assets[token] = SampleAsset(
            token=token,
            path=str(path.resolve()),
            sha256=sha256_file(path),
            original_sample_rate=original_sr,
            sample_rate=sr,
            channels=channels,
            frames=len(y),
            duration_sec=len(y) / sr,
            peak_dbfs=dbfs(peak),
            rms_dbfs=dbfs(rms),
            active_start_sample=active_start,
            active_end_sample=active_end,
            sustain_start_sample=sustain_start,
            sustain_end_sample=sustain_end,
            median_f0_hz=median_f0,
            f0_p10_hz=f0_p10,
            f0_p90_hz=f0_p90,
            voiced_fraction=voiced_fraction,
        )
        audio[token] = y
    return assets, audio


def select_melody_track(pm: pretty_midi.PrettyMIDI, requested_name: str) -> int:
    exact = [i for i, inst in enumerate(pm.instruments) if inst.name.strip().lower() == requested_name.lower()]
    partial = [i for i, inst in enumerate(pm.instruments) if requested_name.lower() in inst.name.strip().lower()]
    candidates = exact or partial
    if not candidates:
        names = [inst.name or f"track_{i}" for i, inst in enumerate(pm.instruments)]
        raise RenderError(f"No instrument named like {requested_name!r}; available tracks: {names}")
    return max(candidates, key=lambda i: len(pm.instruments[i].notes))


def sorted_notes(instrument: pretty_midi.Instrument) -> list[pretty_midi.Note]:
    return sorted(instrument.notes, key=lambda n: (n.start, n.end, n.pitch, n.velocity))


def validate_melody(notes: Sequence[pretty_midi.Note]) -> None:
    if not notes:
        raise RenderError("The selected Melody track has no notes.")
    for i, note in enumerate(notes):
        if note.end <= note.start:
            raise RenderError(f"Non-positive note duration at note index {i}.")
        if i and note.start < notes[i - 1].end - 0.020:
            raise RenderError(
                "The reference renderer requires a monophonic Melody track; "
                f"notes {i - 1} and {i} overlap by more than 20 ms."
            )


def beat_intervals(pm: pretty_midi.PrettyMIDI, end_time: float) -> list[tuple[float, float]]:
    beats = np.asarray(pm.get_beats(), dtype=float)
    beats = beats[np.isfinite(beats)]
    if len(beats) < 2:
        tempo = float(pm.estimate_tempo()) if end_time > 0 else 120.0
        beat = 60.0 / max(tempo, 1.0)
        beats = np.arange(0.0, end_time + beat * 1.5, beat)
    else:
        step = float(np.median(np.diff(beats)))
        while beats[-1] < end_time + 1e-6:
            beats = np.append(beats, beats[-1] + step)
    return [(float(a), float(b)) for a, b in zip(beats[:-1], beats[1:]) if b > a]


def apply_deterministic_swing(
    pm: pretty_midi.PrettyMIDI,
    melody_track_index: int,
    ratio: float,
    tolerance_fraction: float,
) -> tuple[pretty_midi.PrettyMIDI, list[dict[str, Any]]]:
    if not 0.50 < ratio < 0.75:
        raise RenderError("Swing ratio must be between 0.50 and 0.75.")
    out = copy.deepcopy(pm)
    source_notes = sorted_notes(pm.instruments[melody_track_index])
    target_inst = out.instruments[melody_track_index]
    target_notes = sorted_notes(target_inst)
    if len(source_notes) != len(target_notes):
        raise RenderError("Internal note-copy mismatch.")

    note_index = {id(n): i for i, n in enumerate(target_notes)}
    pairs: list[dict[str, Any]] = []
    used: set[int] = set()
    intervals = beat_intervals(pm, max(n.end for n in source_notes))

    for beat_start, beat_end in intervals:
        beat_len = beat_end - beat_start
        mid = beat_start + 0.5 * beat_len
        tol = max(0.010, tolerance_fraction * beat_len)
        starts = [n for n in target_notes if beat_start - tol <= n.start < beat_end - tol]
        if len(starts) < 2:
            continue
        first = min(starts, key=lambda n: abs(n.start - beat_start))
        second_candidates = [n for n in starts if n is not first]
        second = min(second_candidates, key=lambda n: abs(n.start - mid))
        i1, i2 = note_index[id(first)], note_index[id(second)]
        if i1 in used or i2 in used or i2 != i1 + 1:
            continue
        if abs(first.start - beat_start) > tol:
            continue
        if abs(first.end - mid) > tol or abs(second.start - mid) > tol:
            continue
        if abs(second.end - beat_end) > tol:
            continue
        if abs(first.end - second.start) > tol:
            continue

        original = {
            "first_start": first.start,
            "boundary": 0.5 * (first.end + second.start),
            "second_end": second.end,
        }
        boundary = beat_start + ratio * beat_len
        first.end = boundary
        second.start = boundary
        first.velocity = min(127, first.velocity + 5)
        second.velocity = max(1, second.velocity - 2)
        used.update((i1, i2))
        pairs.append(
            {
                "first_note_index": i1,
                "second_note_index": i2,
                "beat_start_sec": beat_start,
                "beat_end_sec": beat_end,
                "original": original,
                "new_boundary_sec": boundary,
                "long_short_ratio": ratio,
            }
        )

    out.instruments = [out.instruments[melody_track_index]]
    out.instruments[0].name = "Melody_humanized"
    return out, pairs


def note_states(pm: pretty_midi.PrettyMIDI) -> list[NoteState]:
    notes = sorted_notes(pm.instruments[0])
    return [
        NoteState(i, int(n.pitch), int(n.velocity), float(n.start), float(n.end))
        for i, n in enumerate(notes)
    ]


def infer_cycles(note_count: int, phrases: Sequence[Sequence[str]], requested: int | None) -> int:
    syllables_per_cycle = sum(len(p) for p in phrases)
    if syllables_per_cycle <= 0:
        raise RenderError("No syllables supplied.")
    max_cycles = note_count // syllables_per_cycle
    if max_cycles < 1:
        raise RenderError(
            f"Melody has {note_count} notes but one phrase cycle needs at least {syllables_per_cycle}; "
            "provide a longer melody or a shorter phrase list."
        )
    if requested is not None:
        if requested < 1 or requested > max_cycles:
            raise RenderError(f"--cycles must be in [1, {max_cycles}] for this MIDI.")
        return requested
    estimate = int(round(note_count / (syllables_per_cycle * 1.15)))
    return min(max(1, estimate), max_cycles)


def phrase_partition_cost(
    notes: Sequence[NoteState],
    start: int,
    end: int,
    expected_notes: float,
    is_last: bool,
) -> float:
    length = end - start
    relative = (length - expected_notes) / max(expected_notes, 1.0)
    cost = 5.0 * relative * relative
    if not is_last and 0 < end < len(notes):
        gap = max(0.0, notes[end].start - notes[end - 1].end)
        local_duration = max(0.040, float(np.median([n.end - n.start for n in notes[max(0, end - 4):min(len(notes), end + 4)]])))
        cost -= min(gap / local_duration, 4.0) * 0.75
    return cost


def partition_notes_into_phrases(
    notes: Sequence[NoteState],
    phrases: Sequence[Sequence[str]],
    cycles: int,
) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for cycle in range(cycles):
        for phrase_index, syllables in enumerate(phrases):
            expanded.append({"cycle_index": cycle, "phrase_index": phrase_index, "syllables": list(syllables)})

    n = len(notes)
    k_total = len(expanded)
    minimums = [len(x["syllables"]) for x in expanded]
    if sum(minimums) > n:
        raise RenderError("Not enough notes to give every syllable one note in the inferred cycles.")
    total_syllables = sum(minimums)
    expected = [n * m / total_syllables for m in minimums]
    prefix_min = np.concatenate(([0], np.cumsum(minimums))).astype(int)

    dp = np.full((k_total + 1, n + 1), np.inf, dtype=float)
    previous = np.full((k_total + 1, n + 1), -1, dtype=int)
    dp[0, 0] = 0.0

    for k in range(1, k_total + 1):
        min_end = int(prefix_min[k])
        max_end = n - int(prefix_min[k_total] - prefix_min[k])
        min_segment = minimums[k - 1]
        for end in range(min_end, max_end + 1):
            start_min = int(prefix_min[k - 1])
            start_max = end - min_segment
            for start in range(start_min, start_max + 1):
                if not math.isfinite(dp[k - 1, start]):
                    continue
                cost = dp[k - 1, start] + phrase_partition_cost(
                    notes, start, end, expected[k - 1], k == k_total
                )
                if cost < dp[k, end]:
                    dp[k, end] = cost
                    previous[k, end] = start

    if not math.isfinite(dp[k_total, n]):
        raise RenderError("Could not partition Melody notes into phrase cycles.")

    boundaries = [n]
    end = n
    for k in range(k_total, 0, -1):
        start = int(previous[k, end])
        if start < 0:
            raise RenderError("Internal phrase partition traceback failed.")
        boundaries.append(start)
        end = start
    boundaries.reverse()

    result: list[dict[str, Any]] = []
    for i, spec in enumerate(expanded):
        start, end = boundaries[i], boundaries[i + 1]
        result.append({**spec, "note_start_index": start, "note_end_index_exclusive": end})
    return result


def base_gesture_candidates(syllable: str, phrase_position: int, phrase_length: int) -> list[str]:
    s = normalize_syllable(syllable)
    onset = s[0]
    if phrase_position == phrase_length - 1:
        return ["m_chant", "m_held"]
    if phrase_position == 0:
        return ["hm_to_m", "breathy_m", "hm"]
    if onset in "hwu":
        return ["breathy_m", "hm_to_m", "m_held"]
    if onset in "tpk":
        return ["m", "hm", "m"]
    if any(v in s for v in "ie"):
        return ["ng", "hm", "m"]
    if any(v in s for v in "ou"):
        return ["oo", "m_held", "breathy_m"]
    return ["m_held", "m", "oo"]


def syllable_sustain_weight(syllable: str, position: int, length: int) -> float:
    s = normalize_syllable(syllable)
    weight = 1.0
    if any(v in s for v in "aou"):
        weight += 0.55
    if position == length - 1:
        weight += 0.55
    if s.startswith(("h", "w")):
        weight += 0.20
    return weight


def allocate_note_counts(syllables: Sequence[str], note_count: int) -> list[int]:
    if note_count < len(syllables):
        raise RenderError("Phrase partition contains fewer notes than syllables.")
    counts = np.ones(len(syllables), dtype=int)
    extras = note_count - len(syllables)
    if extras == 0:
        return counts.tolist()
    weights = np.asarray(
        [syllable_sustain_weight(s, i, len(syllables)) for i, s in enumerate(syllables)],
        dtype=float,
    )
    ideal = extras * weights / float(np.sum(weights))
    floor = np.floor(ideal).astype(int)
    counts += floor
    remainder = extras - int(np.sum(floor))
    if remainder:
        order = sorted(range(len(syllables)), key=lambda i: (-(ideal[i] - floor[i]), i))
        for i in order[:remainder]:
            counts[i] += 1
    return counts.tolist()


def choose_attack_token(
    syllable: str,
    phrase_position: int,
    phrase_length: int,
    serial: int,
    recent: list[str],
) -> str:
    choices = base_gesture_candidates(syllable, phrase_position, phrase_length)
    ordered = choices[serial % len(choices):] + choices[: serial % len(choices)]
    for token in ordered:
        if len(recent) < 3 or not (recent[-1] == recent[-2] == recent[-3] == token):
            return token
    return ordered[0]


def continuation_token(attack_token: str) -> str:
    if attack_token == "ng":
        return "ng"
    if attack_token == "oo":
        return "oo"
    if attack_token == "m_chant":
        return "m_chant"
    return "m_held"


def build_alignment_and_timeline(
    notes: Sequence[NoteState],
    phrases: Sequence[Sequence[str]],
    phrase_partitions: Sequence[dict[str, Any]],
    swing_pairs: Sequence[dict[str, Any]],
    breath_gap_sec: float,
    gliss_max_semitones: int,
    gliss_gap_sec: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    alignment_phrases: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    recent_tokens: list[str] = []
    serial = 0

    for part_index, part in enumerate(phrase_partitions):
        syllables = list(part["syllables"])
        start = int(part["note_start_index"])
        end = int(part["note_end_index_exclusive"])
        phrase_notes = notes[start:end]
        counts = allocate_note_counts(syllables, len(phrase_notes))
        syllable_entries: list[dict[str, Any]] = []
        cursor = start
        for syllable_index, (syllable, count) in enumerate(zip(syllables, counts)):
            attack_token = choose_attack_token(
                syllable, syllable_index, len(syllables), serial, recent_tokens
            )
            recent_tokens.append(attack_token)
            serial += 1
            note_indices = list(range(cursor, cursor + count))
            syllable_entries.append(
                {
                    "syllable_index": syllable_index,
                    "source_syllable": syllable,
                    "note_indices": note_indices,
                    "attack_token": attack_token,
                }
            )
            for local_position, note_index in enumerate(note_indices):
                note = notes[note_index]
                is_attack = local_position == 0
                token = attack_token if is_attack else continuation_token(attack_token)
                next_note = notes[note_index + 1] if note_index + 1 < len(notes) else None
                transition: str | None = None
                transition_target: int | None = None
                if next_note is not None:
                    gap = next_note.start - note.end
                    interval = next_note.pitch - note.pitch
                    if (
                        abs(gap) <= gliss_gap_sec
                        and 1 <= abs(interval) <= gliss_max_semitones
                        and note.end - note.start >= 0.120
                    ):
                        transition = "m_gliss_up" if interval > 0 else "m_gliss_down"
                        transition_target = next_note.pitch
                events.append(
                    {
                        "event_id": f"note_{note_index:05d}",
                        "type": "voiced_note",
                        "note_index": note_index,
                        "start_sec": note.start,
                        "end_sec": note.end,
                        "duration_sec": note.end - note.start,
                        "pitch_midi": note.pitch,
                        "target_hz": float(pretty_midi.note_number_to_hz(note.pitch)),
                        "velocity": note.velocity,
                        "cycle_index": int(part["cycle_index"]),
                        "phrase_index": int(part["phrase_index"]),
                        "phrase_instance_index": part_index,
                        "syllable_index": syllable_index,
                        "source_syllable": syllable,
                        "role": "attack" if is_attack else "melisma_continuation",
                        "token": token,
                        "transition_out_token": transition,
                        "transition_target_midi": transition_target,
                    }
                )
            cursor += count

        alignment_phrases.append(
            {
                "phrase_instance_index": part_index,
                "cycle_index": int(part["cycle_index"]),
                "phrase_index": int(part["phrase_index"]),
                "note_start_index": start,
                "note_end_index_exclusive": end,
                "start_sec": notes[start].start,
                "end_sec": notes[end - 1].end,
                "syllables": syllable_entries,
            }
        )

        phrase_last = notes[end - 1]
        next_start = notes[end].start if end < len(notes) else None
        if next_start is not None:
            gap = next_start - phrase_last.end
            if gap >= breath_gap_sec:
                duration = min(0.45, max(0.10, gap - 0.040))
                events.append(
                    {
                        "event_id": f"breath_after_phrase_{part_index:03d}",
                        "type": "unpitched",
                        "start_sec": phrase_last.end + 0.020,
                        "end_sec": phrase_last.end + 0.020 + duration,
                        "duration_sec": duration,
                        "token": "breath",
                        "phrase_instance_index": part_index,
                    }
                )

    events.sort(key=lambda e: (e["start_sec"], 0 if e["type"] == "voiced_note" else 1, e["event_id"]))
    voiced_note_indices = sorted(e["note_index"] for e in events if e["type"] == "voiced_note")
    alignment = {
        "schema": "syllable_note_alignment_v1",
        "renderer": RENDERER_NAME,
        "note_count": len(notes),
        "coverage_ok": voiced_note_indices == list(range(len(notes))),
        "phrases": alignment_phrases,
    }
    token_counts: dict[str, int] = {}
    transition_counts: dict[str, int] = {}
    for event in events:
        token_counts[event["token"]] = token_counts.get(event["token"], 0) + 1
        transition = event.get("transition_out_token")
        if transition:
            transition_counts[transition] = transition_counts.get(transition, 0) + 1
    timeline = {
        "schema": "articulation_timeline_v1",
        "renderer": RENDERER_NAME,
        "events": events,
        "token_counts": token_counts,
        "transition_counts": transition_counts,
        "swing_pairs": list(swing_pairs),
        "non_lexical_policy": (
            "Source syllables control timing, accent, and resonance class only; "
            "the renderer emits only the supplied nonverbal tokens."
        ),
    }
    return alignment, timeline


def pitch_marks(y: np.ndarray, sr: int, f0_hz: float) -> np.ndarray:
    period = max(8.0, sr / max(f0_hz, 1.0))
    if len(y) < int(4 * period):
        return np.asarray([], dtype=int)
    search = max(2, int(round(0.28 * period)))
    first_window = y[: min(len(y), int(round(1.5 * period)))]
    first = int(np.argmax(np.abs(first_window)))
    polarity = 1.0 if y[first] >= 0 else -1.0
    marks = [first]
    while True:
        predicted = marks[-1] + period
        if predicted + search >= len(y):
            break
        lo = max(marks[-1] + 2, int(round(predicted - search)))
        hi = min(len(y), int(round(predicted + search + 1)))
        if hi <= lo:
            break
        local = polarity * y[lo:hi]
        mark = lo + int(np.argmax(local))
        if mark <= marks[-1]:
            break
        marks.append(mark)
    return np.asarray(marks, dtype=int)


def psola_sustain(
    y: np.ndarray,
    sr: int,
    source_f0_hz: float | None,
    target_f0_start_hz: float,
    output_length: int,
    target_f0_end_hz: float | None = None,
) -> np.ndarray:
    output_length = max(1, int(output_length))
    y = np.asarray(y, dtype=np.float64)
    if len(y) < 32 or source_f0_hz is None or not math.isfinite(source_f0_hz):
        return signal.resample(y if len(y) else np.zeros(1), output_length).astype(np.float32)

    marks = pitch_marks(y, sr, source_f0_hz)
    if len(marks) < 3:
        return signal.resample(y, output_length).astype(np.float32)

    end_hz = target_f0_end_hz or target_f0_start_hz
    target_marks: list[int] = []
    position = 0.0
    while position < output_length:
        progress = min(1.0, position / max(1.0, output_length - 1.0))
        f0 = target_f0_start_hz * ((end_hz / target_f0_start_hz) ** progress)
        period = sr / max(f0, 1.0)
        position += period
        if position < output_length:
            target_marks.append(int(round(position)))
    if not target_marks:
        return signal.resample(y, output_length).astype(np.float32)

    source_period = sr / source_f0_hz
    maximum_target_period = sr / min(target_f0_start_hz, end_hz)
    half = int(round(max(source_period, maximum_target_period) * 1.05))
    half = max(8, min(half, len(y) // 3))
    grain_length = 2 * half + 1
    window = signal.windows.hann(grain_length, sym=True)
    out = np.zeros(output_length + 2 * half + 2, dtype=np.float64)
    weight = np.zeros_like(out)

    usable = marks[(marks >= half) & (marks + half < len(y))]
    if len(usable) < 2:
        return signal.resample(y, output_length).astype(np.float32)
    for i, target_mark in enumerate(target_marks):
        source_mark = int(usable[i % len(usable)])
        grain = y[source_mark - half: source_mark + half + 1]
        start = target_mark
        stop = start + grain_length
        out[start:stop] += grain * window
        weight[start:stop] += window

    out = out[half:half + output_length]
    weight = weight[half:half + output_length]
    valid = weight > 1e-6
    out[valid] /= weight[valid]
    fade = min(int(0.008 * sr), output_length // 4)
    if fade > 1:
        ramp = np.linspace(0.0, 1.0, fade, endpoint=False)
        out[:fade] *= ramp
        out[-fade:] *= ramp[::-1]
    return out.astype(np.float32)


def pitch_shift_preserve_length(y: np.ndarray, sr: int, source_f0: float | None, target_f0: float) -> np.ndarray:
    if len(y) == 0 or source_f0 is None or source_f0 <= 0 or target_f0 <= 0:
        return np.asarray(y, dtype=np.float32).copy()
    original_length = len(y)
    work = np.asarray(y, dtype=np.float32)
    if original_length < 2048:
        pad = 2048 - original_length
        mode = "reflect" if original_length > 1 else "constant"
        work = np.pad(work, (0, pad), mode=mode)
    steps = 12.0 * math.log2(target_f0 / source_f0)
    shifted = librosa.effects.pitch_shift(
        work,
        sr=sr,
        n_steps=steps,
        bins_per_octave=12,
        res_type="scipy",
        scale=False,
    ).astype(np.float32)
    return shifted[:original_length]


def linear_fade(y: np.ndarray, fade_in: int, fade_out: int) -> np.ndarray:
    out = np.asarray(y, dtype=np.float32).copy()
    fade_in = min(max(0, fade_in), len(out))
    fade_out = min(max(0, fade_out), len(out))
    if fade_in > 1:
        out[:fade_in] *= np.linspace(0.0, 1.0, fade_in, endpoint=False, dtype=np.float32)
    if fade_out > 1:
        out[-fade_out:] *= np.linspace(1.0, 0.0, fade_out, endpoint=False, dtype=np.float32)
    return out


def overlay_part(
    output: np.ndarray,
    weight: np.ndarray,
    part: np.ndarray,
    start: int,
    fade_in: int,
    fade_out: int,
) -> None:
    if len(part) == 0:
        return
    start = max(0, int(start))
    stop = min(len(output), start + len(part))
    if stop <= start:
        return
    part = np.asarray(part[: stop - start], dtype=np.float64)
    envelope = np.ones(len(part), dtype=np.float64)
    fi = min(fade_in, len(part))
    fo = min(fade_out, len(part))
    if fi > 1:
        envelope[:fi] *= np.linspace(0.0, 1.0, fi, endpoint=False)
    if fo > 1:
        envelope[-fo:] *= np.linspace(1.0, 0.0, fo, endpoint=False)
    output[start:stop] += part * envelope
    weight[start:stop] += envelope


def render_voiced_gesture(
    token: str,
    target_midi: int,
    duration_sec: float,
    preserve_attack: bool,
    assets: dict[str, SampleAsset],
    audio: dict[str, np.ndarray],
    sr: int,
    crossfade_sec: float,
) -> np.ndarray:
    asset = assets[token]
    y = audio[token]
    total = max(1, int(round(duration_sec * sr)))
    target_hz = float(pretty_midi.note_number_to_hz(target_midi))
    active = y[asset.active_start_sample:asset.active_end_sample]
    sustain = y[asset.sustain_start_sample:asset.sustain_end_sample]
    if len(sustain) < 16:
        sustain = active

    attack = y[asset.active_start_sample:asset.sustain_start_sample] if preserve_attack else np.zeros(0, dtype=np.float32)
    release = y[asset.sustain_end_sample:asset.active_end_sample]
    attack = pitch_shift_preserve_length(attack, sr, asset.median_f0_hz, target_hz)
    release = pitch_shift_preserve_length(release, sr, asset.median_f0_hz, target_hz)

    max_attack = min(int(0.120 * sr), int(total * 0.32))
    max_release = min(int(0.090 * sr), int(total * 0.24))
    if len(attack) > max_attack:
        attack = attack[:max_attack]
    if len(release) > max_release:
        release = release[-max_release:]
    if not preserve_attack:
        attack = np.zeros(min(int(0.008 * sr), max(1, total // 10)), dtype=np.float32)

    xfade = int(round(np.clip(crossfade_sec, 0.025, 0.050) * sr))
    xfade = min(xfade, max(1, total // 4))
    attack_start = 0
    sustain_start = max(0, len(attack) - xfade)
    release_start = max(sustain_start + 1, total - len(release)) if len(release) else total
    sustain_stop = min(total, release_start + (xfade if len(release) else 0))
    sustain_length = max(1, sustain_stop - sustain_start)
    sustain_render = psola_sustain(
        sustain,
        sr,
        asset.median_f0_hz,
        target_hz,
        sustain_length,
    )

    out = np.zeros(total, dtype=np.float64)
    weight = np.zeros(total, dtype=np.float64)
    overlay_part(out, weight, attack, attack_start, min(int(0.005 * sr), len(attack)), xfade)
    overlay_part(out, weight, sustain_render, sustain_start, xfade, xfade if len(release) else int(0.012 * sr))
    if len(release):
        overlay_part(out, weight, release, release_start, xfade, min(int(0.020 * sr), len(release)))
    valid = weight > 1e-8
    out[valid] /= weight[valid]
    return out.astype(np.float32)


def render_gliss(
    token: str,
    start_midi: int,
    end_midi: int,
    duration_sec: float,
    assets: dict[str, SampleAsset],
    audio: dict[str, np.ndarray],
    sr: int,
) -> np.ndarray:
    asset = assets[token]
    source = audio[token][asset.active_start_sample:asset.active_end_sample]
    return psola_sustain(
        source,
        sr,
        asset.median_f0_hz,
        float(pretty_midi.note_number_to_hz(start_midi)),
        max(1, int(round(duration_sec * sr))),
        float(pretty_midi.note_number_to_hz(end_midi)),
    )


def concatenate_crossfade(a: np.ndarray, b: np.ndarray, crossfade: int, target_length: int) -> np.ndarray:
    crossfade = min(crossfade, len(a), len(b), max(0, target_length // 3))
    if crossfade <= 1:
        out = np.concatenate((a, b))
    else:
        fade_out = np.linspace(1.0, 0.0, crossfade, endpoint=False, dtype=np.float32)
        fade_in = 1.0 - fade_out
        overlap = a[-crossfade:] * fade_out + b[:crossfade] * fade_in
        out = np.concatenate((a[:-crossfade], overlap, b[crossfade:]))
    if len(out) < target_length:
        out = np.pad(out, (0, target_length - len(out)))
    elif len(out) > target_length:
        out = out[:target_length]
    return out.astype(np.float32)


def render_note_event(
    event: dict[str, Any],
    assets: dict[str, SampleAsset],
    audio: dict[str, np.ndarray],
    sr: int,
    crossfade_sec: float,
) -> np.ndarray:
    duration = float(event["duration_sec"])
    total = max(1, int(round(duration * sr)))
    transition = event.get("transition_out_token")
    preserve_attack = event["role"] == "attack"
    if transition and total >= int(0.130 * sr):
        gliss_sec = min(0.140, max(0.075, duration * 0.30))
        xfade = int(round(np.clip(crossfade_sec, 0.025, 0.050) * sr))
        body_len = max(1, total - int(round(gliss_sec * sr)) + xfade)
        body = render_voiced_gesture(
            event["token"],
            int(event["pitch_midi"]),
            body_len / sr,
            preserve_attack,
            assets,
            audio,
            sr,
            crossfade_sec,
        )
        gliss = render_gliss(
            transition,
            int(event["pitch_midi"]),
            int(event["transition_target_midi"]),
            gliss_sec,
            assets,
            audio,
            sr,
        )
        return concatenate_crossfade(body, gliss, xfade, total)
    return render_voiced_gesture(
        event["token"],
        int(event["pitch_midi"]),
        duration,
        preserve_attack,
        assets,
        audio,
        sr,
        crossfade_sec,
    )


def render_unpitched_event(
    event: dict[str, Any],
    assets: dict[str, SampleAsset],
    audio: dict[str, np.ndarray],
    sr: int,
) -> np.ndarray:
    token = event["token"]
    asset = assets[token]
    source = audio[token][asset.active_start_sample:asset.active_end_sample]
    length = max(1, int(round(float(event["duration_sec"]) * sr)))
    if len(source) != length:
        source = signal.resample(source if len(source) else np.zeros(1), length).astype(np.float32)
    return linear_fade(source, int(0.015 * sr), int(0.030 * sr))


def active_rms(y: np.ndarray, sr: int) -> float:
    frame = max(64, int(0.040 * sr))
    hop = max(32, frame // 2)
    rms = librosa.feature.rms(y=np.asarray(y, dtype=np.float32), frame_length=frame, hop_length=hop, center=True)[0]
    if not len(rms):
        return 0.0
    threshold = max(10.0 ** (-55.0 / 20.0), float(np.max(rms)) * 0.08)
    active = rms[rms >= threshold]
    return float(np.sqrt(np.mean(active ** 2))) if len(active) else float(np.sqrt(np.mean(rms ** 2)))


def render_timeline(
    timeline: dict[str, Any],
    assets: dict[str, SampleAsset],
    audio: dict[str, np.ndarray],
    sr: int,
    crossfade_sec: float,
    target_peak_dbfs: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    events = timeline["events"]
    last_end = max(float(e["end_sec"]) for e in events)
    out = np.zeros(int(math.ceil((last_end + 0.100) * sr)), dtype=np.float64)
    render_log: list[dict[str, Any]] = []

    for event in events:
        segment = (
            render_note_event(event, assets, audio, sr, crossfade_sec)
            if event["type"] == "voiced_note"
            else render_unpitched_event(event, assets, audio, sr)
        )
        token = event["token"]
        target_rms = 10.0 ** ((-24.0 if token != "breath" else -34.0) / 20.0)
        measured = active_rms(segment, sr)
        if measured > 1e-8:
            gain = float(np.clip(target_rms / measured, 10.0 ** (-12 / 20), 10.0 ** (12 / 20)))
            segment = segment * gain
        velocity_gain = 1.0
        if event["type"] == "voiced_note":
            velocity_gain = float(np.clip((int(event["velocity"]) / 96.0) ** 0.55, 0.70, 1.28))
            segment = segment * velocity_gain
        start = int(round(float(event["start_sec"]) * sr))
        stop = min(len(out), start + len(segment))
        if stop > start:
            out[start:stop] += segment[: stop - start]
        render_log.append(
            {
                "event_id": event["event_id"],
                "token": token,
                "start_sample": start,
                "rendered_frames": len(segment),
                "velocity_gain": velocity_gain,
            }
        )

    out = signal.detrend(out, type="constant")
    peak = float(np.max(np.abs(out))) if len(out) else 0.0
    target_peak = 10.0 ** (target_peak_dbfs / 20.0)
    normalization_gain = 1.0
    if peak > target_peak and peak > 0:
        normalization_gain = target_peak / peak
        out *= normalization_gain
    return out.astype(np.float32), {
        "normalization_gain": normalization_gain,
        "rendered_event_count": len(events),
        "event_log": render_log,
    }


def target_pitch_for_frames(
    frame_times: np.ndarray,
    voiced_events: Sequence[dict[str, Any]],
) -> tuple[np.ndarray, np.ndarray]:
    starts = np.asarray([e["start_sec"] for e in voiced_events], dtype=float)
    ends = np.asarray([e["end_sec"] for e in voiced_events], dtype=float)
    pitches = np.asarray([e["pitch_midi"] for e in voiced_events], dtype=float)
    indices = np.searchsorted(starts, frame_times, side="right") - 1
    valid_index = indices >= 0
    clipped = np.clip(indices, 0, len(starts) - 1)
    durations = ends[clipped] - starts[clipped]
    edge = np.minimum(0.050, np.maximum(0.010, durations * 0.18))
    valid = (
        valid_index
        & (frame_times >= starts[clipped] + edge)
        & (frame_times < ends[clipped] - edge)
    )
    target = np.full(len(frame_times), np.nan, dtype=float)
    target[valid] = pitches[clipped[valid]]
    return target, valid


def longest_run_seconds(mask: np.ndarray, hop_sec: float) -> float:
    longest = current = 0
    for value in np.asarray(mask, dtype=bool):
        current = current + 1 if value else 0
        longest = max(longest, current)
    return longest * hop_sec


def calculate_pitch_qa(y: np.ndarray, sr: int, voiced_events: Sequence[dict[str, Any]]) -> dict[str, Any]:
    hop = 256
    frame_length = 2048
    midi_values = [int(e["pitch_midi"]) for e in voiced_events]
    fmin = float(pretty_midi.note_number_to_hz(max(0, min(midi_values) - 12)))
    fmax = float(pretty_midi.note_number_to_hz(min(127, max(midi_values) + 12)))
    f0 = librosa.yin(
        y,
        fmin=fmin,
        fmax=fmax,
        sr=sr,
        frame_length=frame_length,
        hop_length=hop,
    )
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop, center=True)[0]
    flatness = librosa.feature.spectral_flatness(
        y=y, n_fft=frame_length, hop_length=hop, center=True
    )[0]
    count = min(len(f0), len(rms), len(flatness))
    f0, rms, flatness = f0[:count], rms[:count], flatness[:count]
    times = librosa.frames_to_time(np.arange(count), sr=sr, hop_length=hop)
    target_midi, expected = target_pitch_for_frames(times, voiced_events)
    energy_floor = max(10.0 ** (-55.0 / 20.0), float(np.max(rms)) * 0.025)
    voiced = np.isfinite(f0) & (rms >= energy_floor) & (flatness <= 0.65)
    valid = expected & voiced
    expected_count = int(np.count_nonzero(expected))
    voiced_coverage = float(np.count_nonzero(valid) / expected_count) if expected_count else 0.0
    if not np.any(valid):
        return {
            "voiced_coverage": voiced_coverage,
            "frame_count": 0,
            "median_abs_cents": None,
            "mean_abs_cents": None,
            "p90_abs_cents": None,
            "longest_octave_error_sec": None,
        }
    target_hz = librosa.midi_to_hz(target_midi[valid])
    cents = 1200.0 * np.log2(f0[valid] / target_hz)
    abs_cents = np.abs(cents)

    full_abs = np.full(count, np.nan, dtype=float)
    full_abs[valid] = abs_cents
    octave_mask = np.isfinite(full_abs) & (full_abs >= 600.0)
    return {
        "voiced_coverage": voiced_coverage,
        "frame_count": int(len(abs_cents)),
        "median_abs_cents": finite_float(np.median(abs_cents)),
        "mean_abs_cents": finite_float(np.mean(abs_cents)),
        "p90_abs_cents": finite_float(np.percentile(abs_cents, 90)),
        "longest_octave_error_sec": longest_run_seconds(octave_mask, hop / sr),
    }


def calculate_onset_qa(y: np.ndarray, sr: int, voiced_events: Sequence[dict[str, Any]]) -> dict[str, Any]:
    expected = np.asarray(
        [float(e["start_sec"]) for e in voiced_events if e["role"] == "attack"],
        dtype=float,
    )
    hop = 128
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    if len(onset_env):
        threshold = max(float(np.percentile(onset_env, 60)), float(np.max(onset_env)) * 0.08)
        peaks, _ = signal.find_peaks(
            onset_env,
            height=threshold,
            distance=max(1, int(round(0.035 * sr / hop))),
        )
        detected = librosa.frames_to_time(peaks, sr=sr, hop_length=hop)
    else:
        detected = np.asarray([], dtype=float)

    errors: list[float] = []
    matched = 0
    for onset in expected:
        if not len(detected):
            continue
        delta = detected - onset
        idx = int(np.argmin(np.abs(delta)))
        if abs(delta[idx]) <= 0.120:
            matched += 1
            errors.append(float(delta[idx]))
    abs_errors = np.abs(errors) if errors else np.asarray([], dtype=float)
    return {
        "expected_attack_count": int(len(expected)),
        "detected_onset_count": int(len(detected)),
        "matched_attack_count": int(matched),
        "attack_coverage": float(matched / len(expected)) if len(expected) else 1.0,
        "median_abs_error_ms": finite_float(np.median(abs_errors) * 1000.0) if len(abs_errors) else None,
        "p95_abs_error_ms": finite_float(np.percentile(abs_errors, 95) * 1000.0) if len(abs_errors) else None,
        "signed_errors_ms": [finite_float(x * 1000.0) for x in errors],
    }


def calculate_signal_qa(y: np.ndarray, sr: int, voiced_events: Sequence[dict[str, Any]]) -> dict[str, Any]:
    peak = float(np.max(np.abs(y))) if len(y) else 0.0
    oversampled = signal.resample_poly(np.asarray(y, dtype=np.float64), 4, 1)
    true_peak = float(np.max(np.abs(oversampled))) if len(oversampled) else peak
    rms = float(np.sqrt(np.mean(np.asarray(y, dtype=np.float64) ** 2) + 1e-15))

    hop = max(1, int(round(0.010 * sr)))
    frame = max(hop * 2, 64)
    frame_rms = librosa.feature.rms(y=y, frame_length=frame, hop_length=hop, center=True)[0]
    times = librosa.frames_to_time(np.arange(len(frame_rms)), sr=sr, hop_length=hop)
    _, expected = target_pitch_for_frames(times, voiced_events)
    dropout = expected & (frame_rms < 10.0 ** (-55.0 / 20.0))
    return {
        "frames": int(len(y)),
        "duration_sec": len(y) / sr,
        "sample_peak_dbfs": dbfs(peak),
        "true_peak_dbfs": dbfs(true_peak),
        "rms_dbfs": dbfs(rms),
        "dc_offset": finite_float(np.mean(y)),
        "clipped_sample_count": int(np.count_nonzero(np.abs(y) >= 0.9999)),
        "longest_expected_region_dropout_sec": longest_run_seconds(dropout, hop / sr),
    }


def max_consecutive(values: Iterable[str]) -> int:
    longest = current = 0
    previous: str | None = None
    for value in values:
        if value == previous:
            current += 1
        else:
            previous = value
            current = 1
        longest = max(longest, current)
    return longest


def calculate_token_qa(timeline: dict[str, Any], assets: dict[str, SampleAsset]) -> dict[str, Any]:
    events = timeline["events"]
    voiced = [e for e in events if e["type"] == "voiced_note"]
    used = [e["token"] for e in events]
    transitions = [e["transition_out_token"] for e in voiced if e.get("transition_out_token")]
    attack_tokens = [e["token"] for e in voiced if e["role"] == "attack"]
    used_voiced_classes = sorted((set(used) | set(transitions)) & VOICED_TOKENS - GLISS_TOKENS)
    missing = sorted(set(REQUIRED_TOKENS) - set(assets))
    note_indices = sorted(int(e["note_index"]) for e in voiced)
    return {
        "required_inventory_tokens": list(REQUIRED_TOKENS),
        "missing_inventory_tokens": missing,
        "used_token_counts": timeline["token_counts"],
        "used_transition_counts": timeline["transition_counts"],
        "used_voiced_gesture_classes": used_voiced_classes,
        "used_voiced_gesture_class_count": len(used_voiced_classes),
        "maximum_consecutive_identical_attack_token": max_consecutive(attack_tokens),
        "note_coverage_ok": note_indices == list(range(len(note_indices))),
    }


def calculate_swing_qa(swing_pairs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    ratios = [float(p["long_short_ratio"]) for p in swing_pairs]
    return {
        "pair_count": len(ratios),
        "median_long_short_ratio": finite_float(np.median(ratios)) if ratios else None,
        "minimum_ratio": finite_float(np.min(ratios)) if ratios else None,
        "maximum_ratio": finite_float(np.max(ratios)) if ratios else None,
    }


def passes_number(value: Any, predicate) -> bool:
    return value is not None and math.isfinite(float(value)) and bool(predicate(float(value)))


def calculate_qa(
    y: np.ndarray,
    sr: int,
    timeline: dict[str, Any],
    alignment: dict[str, Any],
    assets: dict[str, SampleAsset],
    require_swing_pair: bool,
) -> dict[str, Any]:
    voiced = [e for e in timeline["events"] if e["type"] == "voiced_note"]
    pitch = calculate_pitch_qa(y, sr, voiced)
    onset = calculate_onset_qa(y, sr, voiced)
    signal_qa = calculate_signal_qa(y, sr, voiced)
    token = calculate_token_qa(timeline, assets)
    swing = calculate_swing_qa(timeline["swing_pairs"])

    checks = {
        "alignment_complete": bool(alignment["coverage_ok"] and token["note_coverage_ok"]),
        "inventory_complete": not token["missing_inventory_tokens"],
        "token_diversity_at_least_five": token["used_voiced_gesture_class_count"] >= 5,
        "attack_repetition_at_most_three": token["maximum_consecutive_identical_attack_token"] <= 3,
        "swing_present_or_waived": swing["pair_count"] > 0 or not require_swing_pair,
        "swing_ratio_in_range": (
            (not require_swing_pair and swing["pair_count"] == 0)
            or passes_number(swing["median_long_short_ratio"], lambda x: 0.56 <= x <= 0.60)
        ),
        "pitch_median_at_most_45_cents": passes_number(pitch["median_abs_cents"], lambda x: x <= 45.0),
        "pitch_p90_at_most_150_cents": passes_number(pitch["p90_abs_cents"], lambda x: x <= 150.0),
        "voiced_coverage_at_least_0_65": pitch["voiced_coverage"] >= 0.65,
        "onset_median_at_most_50_ms": passes_number(onset["median_abs_error_ms"], lambda x: x <= 50.0),
        "onset_p95_at_most_120_ms": passes_number(onset["p95_abs_error_ms"], lambda x: x <= 120.0),
        "attack_coverage_at_least_0_50": onset["attack_coverage"] >= 0.50,
        "true_peak_at_most_minus_0_8_dbfs": signal_qa["true_peak_dbfs"] <= -0.8,
        "no_clipped_samples": signal_qa["clipped_sample_count"] == 0,
        "no_dropout_over_100_ms": signal_qa["longest_expected_region_dropout_sec"] <= 0.100,
    }
    return {
        "schema": "qa_metrics_v1",
        "renderer": RENDERER_NAME,
        "pitch": pitch,
        "onset": onset,
        "signal": signal_qa,
        "token_coverage": token,
        "swing": swing,
        "gate_checks": checks,
        "passes_local_gate": all(checks.values()),
        "scope_note": "Machine QA does not establish human-likeness; retain a blind listening gate.",
    }


def loudness_match(y: np.ndarray, sr: int, target_rms: float) -> np.ndarray:
    measured = active_rms(y, sr)
    out = np.asarray(y, dtype=np.float32).copy()
    if measured > 1e-8 and target_rms > 0:
        out *= float(np.clip(target_rms / measured, 0.1, 10.0))
    peak = float(np.max(np.abs(out))) if len(out) else 0.0
    if peak > 0.89:
        out *= 0.89 / peak
    return out


def create_review_ab(
    candidate: np.ndarray,
    sr: int,
    baseline_path: Path,
    output_path: Path,
    seed: int,
) -> dict[str, Any]:
    baseline, baseline_sr, _, _ = mono_float32(baseline_path, sr)
    target = min(active_rms(candidate, sr), active_rms(baseline, sr))
    if target <= 1e-8:
        target = 10.0 ** (-24.0 / 20.0)
    clips = {
        "candidate": loudness_match(candidate, sr, target),
        "baseline": loudness_match(baseline, sr, target),
    }
    rng = np.random.default_rng(seed)
    order = ["candidate", "baseline"]
    rng.shuffle(order)
    silence = np.zeros(int(round(1.0 * sr)), dtype=np.float32)
    review = np.concatenate((clips[order[0]], silence, clips[order[1]])).astype(np.float32)
    sf.write(output_path, review, sr, subtype="PCM_24")
    return {
        "order": order,
        "baseline_path": str(baseline_path.resolve()),
        "baseline_sha256": sha256_file(baseline_path),
        "baseline_original_sample_rate": baseline_sr,
        "separator_sec": 1.0,
        "active_rms_target": target,
    }


def multipart_body(fields: dict[str, str], file_field: str, file_path: Path) -> tuple[bytes, str]:
    boundary = f"----hum-renderer-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            (
                f'Content-Disposition: form-data; name="{file_field}"; '
                f'filename="{file_path.name}"\r\n'
            ).encode(),
            b"Content-Type: audio/wav\r\n\r\n",
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(chunks), boundary


def elevenlabs_voice_changer(
    input_wav: Path,
    output_path: Path,
    receipt_path: Path,
    voice_id: str,
    api_key: str,
    qa: dict[str, Any],
    model_id: str = "eleven_multilingual_sts_v2",
    output_format: str = "mp3_44100_128",
    seed: int = 20260620,
    enable_logging: bool = True,
    timeout_sec: float = 180.0,
) -> dict[str, Any]:
    """Explicit, post-QA-only ElevenLabs Voice Changer call using stdlib HTTP."""
    if not qa.get("passes_local_gate"):
        raise RenderError("ElevenLabs call refused: local QA did not pass.")
    if not api_key:
        raise RenderError("ElevenLabs call requires ELEVENLABS_API_KEY.")
    if not voice_id:
        raise RenderError("ElevenLabs call requires --elevenlabs-voice-id.")

    query = urllib.parse.urlencode(
        {
            "output_format": output_format,
            "enable_logging": "true" if enable_logging else "false",
        }
    )
    url = f"https://api.elevenlabs.io/v1/speech-to-speech/{urllib.parse.quote(voice_id)}?{query}"
    body, boundary = multipart_body(
        {"model_id": model_id, "seed": str(int(seed))},
        "audio",
        input_wav,
    )
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "xi-api-key": api_key,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "audio/mpeg, audio/wav, application/octet-stream",
            "User-Agent": f"{RENDERER_NAME}/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            payload = response.read()
            status = int(getattr(response, "status", 200))
            headers = dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", errors="replace")
        raise RenderError(f"ElevenLabs HTTP {exc.code}: {detail}") from exc
    if status < 200 or status >= 300 or not payload:
        raise RenderError(f"ElevenLabs returned status={status}, bytes={len(payload)}")
    output_path.write_bytes(payload)
    receipt = {
        "endpoint": "/v1/speech-to-speech/:voice_id",
        "status": status,
        "model_id": model_id,
        "output_format": output_format,
        "seed": int(seed),
        "enable_logging": bool(enable_logging),
        "input_sha256": sha256_file(input_wav),
        "output_sha256": sha256_file(output_path),
        "output_bytes": len(payload),
        "content_type": headers.get("Content-Type"),
        "request_id": headers.get("request-id") or headers.get("x-request-id"),
        "api_key_logged": False,
    }
    write_json(receipt_path, receipt)
    return receipt


def build_manifest(
    args: argparse.Namespace,
    midi_path: Path,
    phrase_source: dict[str, Any],
    assets: dict[str, SampleAsset],
    output_paths: dict[str, Path],
    review: dict[str, Any] | None,
    cloud_receipt: dict[str, Any] | None,
    render_info: dict[str, Any],
) -> dict[str, Any]:
    outputs: dict[str, Any] = {}
    for key, path in output_paths.items():
        if key == "manifest" or not path.exists():
            continue
        outputs[key] = {
            "path": str(path.resolve()),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
    safe_args = vars(args).copy()
    return {
        "schema": "render_manifest_v1",
        "renderer": RENDERER_NAME,
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
        "arguments": safe_args,
        "seed": int(args.seed),
        "inputs": {
            "midi": {"path": str(midi_path.resolve()), "sha256": sha256_file(midi_path)},
            "phrases": phrase_source,
            "samples": {token: asdict(asset) for token, asset in assets.items()},
        },
        "outputs": outputs,
        "review_ab": review,
        "elevenlabs": cloud_receipt,
        "render": render_info,
        "versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "pretty_midi": getattr(pretty_midi, "__version__", "unknown"),
            "librosa": librosa.__version__,
            "soundfile": sf.__version__,
        },
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--midi", required=True, type=Path, help="Input MIDI containing a Melody track.")
    parser.add_argument("--samples", required=True, type=Path, help="Directory containing articulation WAVs.")
    parser.add_argument("--phrases-json", type=Path, default=None, help="Optional phrase JSON; defaults to embedded phrases.")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--baseline-wav", type=Path, default=None)
    parser.add_argument("--melody-track-name", default="Melody")
    parser.add_argument("--sample-rate", type=int, default=44100)
    parser.add_argument("--cycles", type=int, default=None, help="Phrase cycles; default infers a feasible count.")
    parser.add_argument("--swing-ratio", type=float, default=0.58)
    parser.add_argument("--swing-tolerance", type=float, default=0.10, help="Fraction of one beat.")
    parser.add_argument("--crossfade-ms", type=float, default=35.0)
    parser.add_argument("--breath-gap-ms", type=float, default=250.0)
    parser.add_argument("--gliss-max-semitones", type=int, default=3)
    parser.add_argument("--gliss-gap-ms", type=float, default=40.0)
    parser.add_argument("--target-peak-dbfs", type=float, default=-1.2)
    parser.add_argument("--seed", type=int, default=20260620)
    parser.add_argument("--allow-no-swing-pairs", action="store_true")

    parser.add_argument("--run-elevenlabs", action="store_true", help="Explicit opt-in; never enabled by default.")
    parser.add_argument("--elevenlabs-voice-id", default=None)
    parser.add_argument("--elevenlabs-model-id", default="eleven_multilingual_sts_v2")
    parser.add_argument("--elevenlabs-output-format", default="mp3_44100_128")
    parser.add_argument("--elevenlabs-disable-logging", action="store_false", dest="elevenlabs_enable_logging")
    parser.set_defaults(elevenlabs_enable_logging=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.sample_rate < 16000:
        raise RenderError("--sample-rate must be at least 16000 Hz.")
    if not 25.0 <= args.crossfade_ms <= 50.0:
        raise RenderError("--crossfade-ms must be within 25..50 ms.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_paths = {key: args.output_dir / name for key, name in OUTPUT_FILENAMES.items()}

    phrases, phrase_source = load_phrases(args.phrases_json)
    sample_paths = discover_sample_paths(args.samples)
    assets, sample_audio = analyze_samples(sample_paths, args.sample_rate)
    write_json(
        output_paths["inventory"],
        {
            "schema": "sample_inventory_v1",
            "renderer": RENDERER_NAME,
            "sample_rate": args.sample_rate,
            "required_tokens": list(REQUIRED_TOKENS),
            "samples": {token: asdict(assets[token]) for token in REQUIRED_TOKENS},
        },
    )

    source_pm = pretty_midi.PrettyMIDI(str(args.midi))
    melody_index = select_melody_track(source_pm, args.melody_track_name)
    validate_melody(sorted_notes(source_pm.instruments[melody_index]))
    humanized_pm, swing_pairs = apply_deterministic_swing(
        source_pm,
        melody_index,
        args.swing_ratio,
        args.swing_tolerance,
    )
    humanized_pm.write(str(output_paths["midi"]))
    notes = note_states(humanized_pm)

    cycles = infer_cycles(len(notes), phrases, args.cycles)
    partitions = partition_notes_into_phrases(notes, phrases, cycles)
    alignment, timeline = build_alignment_and_timeline(
        notes,
        phrases,
        partitions,
        swing_pairs,
        args.breath_gap_ms / 1000.0,
        args.gliss_max_semitones,
        args.gliss_gap_ms / 1000.0,
    )
    alignment["phrase_source"] = phrase_source
    alignment["cycles"] = cycles
    write_json(output_paths["alignment"], alignment)
    write_json(output_paths["timeline"], timeline)

    audio, render_info = render_timeline(
        timeline,
        assets,
        sample_audio,
        args.sample_rate,
        args.crossfade_ms / 1000.0,
        args.target_peak_dbfs,
    )
    sf.write(output_paths["audio"], audio, args.sample_rate, subtype="PCM_24")

    qa = calculate_qa(
        audio,
        args.sample_rate,
        timeline,
        alignment,
        assets,
        require_swing_pair=not args.allow_no_swing_pairs,
    )
    write_json(output_paths["qa"], qa)

    review: dict[str, Any] | None = None
    if args.baseline_wav is not None:
        review = create_review_ab(
            audio,
            args.sample_rate,
            args.baseline_wav,
            output_paths["review"],
            args.seed,
        )

    cloud_receipt: dict[str, Any] | None = None
    if args.run_elevenlabs:
        api_key = os.environ.get("ELEVENLABS_API_KEY", "")
        cloud_output = args.output_dir / "elevenlabs_voice_changer_v1.mp3"
        receipt_path = args.output_dir / "elevenlabs_request_receipt_v1.json"
        cloud_receipt = elevenlabs_voice_changer(
            output_paths["audio"],
            cloud_output,
            receipt_path,
            args.elevenlabs_voice_id or "",
            api_key,
            qa,
            model_id=args.elevenlabs_model_id,
            output_format=args.elevenlabs_output_format,
            seed=args.seed,
            enable_logging=args.elevenlabs_enable_logging,
        )
        output_paths["elevenlabs_audio"] = cloud_output
        output_paths["elevenlabs_receipt"] = receipt_path

    manifest = build_manifest(
        args,
        args.midi,
        phrase_source,
        assets,
        output_paths,
        review,
        cloud_receipt,
        render_info,
    )
    write_json(output_paths["manifest"], manifest)

    print(json.dumps({
        "renderer": RENDERER_NAME,
        "output_dir": str(args.output_dir.resolve()),
        "passes_local_gate": qa["passes_local_gate"],
        "swing_pairs": len(swing_pairs),
        "cycles": cycles,
    }, indent=2))
    return 0 if qa["passes_local_gate"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RenderError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
