"""Extract pitch/cadence curves and render a neutral humming guide."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from typing import Any

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import fftconvolve


@dataclass(frozen=True)
class DecomposeResult:
    audio_path: str
    out_dir: str
    melody_json: str
    cadence_json: str
    sound_json: str
    text_json: str
    neutral_hum_wav: str
    sample_rate: int
    duration_s: float
    frame_hz: float
    voiced_ratio: float
    onset_count: int

    def to_dict(self) -> dict:
        return asdict(self)


AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3", ".m4a", ".ogg", ".opus", ".aiff", ".aif"}
WORD_RE = re.compile(r"[A-Za-z0-9']+")


def _smooth(values: np.ndarray, width: int) -> np.ndarray:
    if width <= 1:
        return values
    kernel = np.hanning(width * 2 + 1).astype(np.float32)
    kernel /= kernel.sum()
    return fftconvolve(values.astype(np.float32), kernel, mode="same")


def _extract_f0(
    y: np.ndarray,
    sr: int,
    *,
    frame_length: int,
    hop_length: int,
    fmin: float,
    fmax: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    f0 = librosa.yin(
        y,
        fmin=fmin,
        fmax=fmax,
        sr=sr,
        frame_length=frame_length,
        hop_length=hop_length,
    ).astype(np.float32)
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    rms_threshold = max(float(np.percentile(rms, 35)) * 0.8, 1e-4)
    voiced = np.isfinite(f0) & (rms > rms_threshold)
    f0[~voiced] = 0.0
    times = librosa.frames_to_time(np.arange(len(f0)), sr=sr, hop_length=hop_length)
    return times.astype(np.float32), f0, rms.astype(np.float32)


def _extract_onsets(y: np.ndarray, sr: int, hop_length: int) -> tuple[np.ndarray, np.ndarray]:
    envelope = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
    frames = librosa.onset.onset_detect(
        onset_envelope=envelope,
        sr=sr,
        hop_length=hop_length,
        units="frames",
        backtrack=True,
    )
    times = librosa.frames_to_time(frames, sr=sr, hop_length=hop_length)
    return times.astype(np.float32), envelope.astype(np.float32)


def _midi_to_hz(midi: float) -> float:
    return 440.0 * (2.0 ** ((float(midi) - 69.0) / 12.0))


def _hz_to_midi(f0_hz: float) -> float:
    return 69.0 + 12.0 * math.log2(float(f0_hz) / 440.0)


def _pitch_controls(
    times: np.ndarray,
    f0: np.ndarray,
    *,
    min_gliss_duration_s: float = 0.12,
    min_gliss_delta_cents: float = 140.0,
    min_slope_cents_per_s: float = 70.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    controls: list[dict[str, Any]] = []
    voiced_indices = np.where(f0 > 0.0)[0]
    slope_by_index: dict[int, float] = {}
    if len(voiced_indices) >= 2:
        voiced_times = times[voiced_indices].astype(np.float32)
        voiced_cents = np.asarray([_hz_to_midi(float(f0[i])) * 100.0 for i in voiced_indices], dtype=np.float32)
        slopes = np.gradient(voiced_cents, voiced_times).astype(np.float32)
        slope_by_index = {int(i): float(s) for i, s in zip(voiced_indices, slopes)}

    for index, (t, freq) in enumerate(zip(times, f0)):
        if freq <= 0.0:
            controls.append(
                {
                    "t": round(float(t), 4),
                    "voiced": False,
                    "nearest_midi": None,
                    "bend_cents": None,
                    "f0_slope_cents_per_s": None,
                }
            )
            continue
        midi_float = _hz_to_midi(float(freq))
        nearest_midi = int(round(midi_float))
        bend_cents = 1200.0 * math.log2(float(freq) / _midi_to_hz(nearest_midi))
        controls.append(
            {
                "t": round(float(t), 4),
                "voiced": True,
                "nearest_midi": nearest_midi,
                "midi_float": round(float(midi_float), 4),
                "bend_cents": round(float(bend_cents), 3),
                "f0_slope_cents_per_s": round(float(slope_by_index.get(index, 0.0)), 3),
            }
        )

    events: list[dict[str, Any]] = []
    active: list[int] = []

    def flush() -> None:
        nonlocal active
        if len(active) < 2:
            active = []
            return
        start_i = active[0]
        end_i = active[-1]
        start_t = float(times[start_i])
        end_t = float(times[end_i])
        duration = end_t - start_t
        start_midi = _hz_to_midi(float(f0[start_i]))
        end_midi = _hz_to_midi(float(f0[end_i]))
        delta_cents = (end_midi - start_midi) * 100.0
        if duration >= min_gliss_duration_s and abs(delta_cents) >= min_gliss_delta_cents:
            direction = "slide_up" if delta_cents > 0 else "slide_down"
            events.append(
                {
                    "start_sec": round(start_t, 4),
                    "end_sec": round(end_t, 4),
                    "duration_sec": round(duration, 4),
                    "from_midi": round(float(start_midi), 4),
                    "to_midi": round(float(end_midi), 4),
                    "delta_cents": round(float(delta_cents), 3),
                    "direction": direction,
                    "articulation": "glissando",
                    "curve_source": "measured_f0",
                }
            )
        active = []

    previous_index: int | None = None
    for index in voiced_indices:
        slope = slope_by_index.get(int(index), 0.0)
        contiguous = previous_index is not None and int(index) == previous_index + 1
        if abs(slope) >= min_slope_cents_per_s:
            if not active or contiguous:
                active.append(int(index))
            else:
                flush()
                active.append(int(index))
        elif active:
            flush()
        previous_index = int(index)
    flush()
    return controls, events


def _write_melody_json(
    path: Path,
    *,
    times: np.ndarray,
    f0: np.ndarray,
    rms: np.ndarray,
    sr: int,
    hop_length: int,
) -> None:
    pitch_controls, glissando_events = _pitch_controls(times, f0)
    frames = [
        {
            "t": round(float(t), 4),
            "f0_hz": round(float(freq), 3),
            "rms": round(float(level), 6),
            "voiced": bool(freq > 0.0),
            "nearest_midi": control["nearest_midi"],
            "bend_cents": control["bend_cents"],
            "f0_slope_cents_per_s": control["f0_slope_cents_per_s"],
        }
        for t, freq, level, control in zip(times, f0, rms, pitch_controls)
    ]
    payload = {
        "schema": "hum.melody.v1",
        "sample_rate": sr,
        "hop_length": hop_length,
        "frame_hz": sr / hop_length,
        "pitch_control": {
            "representation": "frame_level_f0_plus_midi_bend",
            "bend_cents_reference": "nearest_midi_equal_temperament",
            "glissando_events": glissando_events,
            "note": "Glissando is represented by measured continuous F0, pitch-bend cents, and slide events; MIDI notes alone are not sufficient.",
        },
        "frames": frames,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_cadence_json(
    path: Path,
    *,
    onset_times: np.ndarray,
    onset_envelope: np.ndarray,
    sr: int,
    hop_length: int,
) -> None:
    payload = {
        "schema": "hum.cadence.v1",
        "sample_rate": sr,
        "hop_length": hop_length,
        "frame_hz": sr / hop_length,
        "onsets": [{"t": round(float(t), 4)} for t in onset_times],
        "onset_envelope": [
            {"t": round(float(t), 4), "strength": round(float(v), 6)}
            for t, v in zip(
                librosa.frames_to_time(np.arange(len(onset_envelope)), sr=sr, hop_length=hop_length),
                onset_envelope,
            )
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _classify_hum_frame(f0_hz: float, rms: float, centroid_hz: float, flatness: float) -> str:
    if rms < 1e-4:
        return "silence"
    if f0_hz <= 0.0:
        return "breath_or_unvoiced_noise"
    if centroid_hz < 1700.0 and flatness < 0.2:
        return "closed_mouth_m"
    if centroid_hz < 2600.0:
        return "nasal_ng_or_open_oo"
    return "bright_or_noisy_hum"


def _write_sound_json(
    path: Path,
    *,
    y: np.ndarray,
    f0: np.ndarray,
    rms: np.ndarray,
    sr: int,
    hop_length: int,
) -> None:
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop_length)[0].astype(np.float32)
    bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr, hop_length=hop_length)[0].astype(np.float32)
    rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, hop_length=hop_length, roll_percent=0.85)[0].astype(
        np.float32
    )
    flatness = librosa.feature.spectral_flatness(y=y, hop_length=hop_length)[0].astype(np.float32)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=hop_length).astype(np.float32)

    n = min(len(f0), len(rms), len(centroid), len(bandwidth), len(rolloff), len(flatness), mfcc.shape[1])
    times = librosa.frames_to_time(np.arange(n), sr=sr, hop_length=hop_length)
    labels = [
        _classify_hum_frame(float(f0[i]), float(rms[i]), float(centroid[i]), float(flatness[i]))
        for i in range(n)
    ]
    label_counts = {label: labels.count(label) for label in sorted(set(labels))}
    voiced = f0[:n] > 0.0

    payload = {
        "schema": "hum.sound.v1",
        "sample_rate": sr,
        "hop_length": hop_length,
        "frame_hz": sr / hop_length,
        "note": "hum_articulation is not literal speech phoneme recognition; humming has no lexical phonemes.",
        "summary": {
            "label_counts": label_counts,
            "mean_centroid_hz": round(float(np.mean(centroid[:n])), 3) if n else 0.0,
            "mean_bandwidth_hz": round(float(np.mean(bandwidth[:n])), 3) if n else 0.0,
            "mean_rolloff_hz": round(float(np.mean(rolloff[:n])), 3) if n else 0.0,
            "mean_flatness": round(float(np.mean(flatness[:n])), 6) if n else 0.0,
            "voiced_mean_centroid_hz": round(float(np.mean(centroid[:n][voiced])), 3)
            if np.any(voiced)
            else 0.0,
            "mfcc_mean": [round(float(v), 6) for v in np.mean(mfcc[:, :n], axis=1)] if n else [],
            "mfcc_std": [round(float(v), 6) for v in np.std(mfcc[:, :n], axis=1)] if n else [],
        },
        "frames": [
            {
                "t": round(float(times[i]), 4),
                "hum_articulation": labels[i],
                "centroid_hz": round(float(centroid[i]), 3),
                "bandwidth_hz": round(float(bandwidth[i]), 3),
                "rolloff_hz": round(float(rolloff[i]), 3),
                "flatness": round(float(flatness[i]), 6),
                "mfcc": [round(float(v), 6) for v in mfcc[:, i]],
            }
            for i in range(n)
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _round_float(value: float | None, digits: int = 4) -> float | None:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return None
    return round(float(value), digits)


def _normalize_whisper_segments(result: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    utterances: list[dict[str, Any]] = []
    words: list[dict[str, Any]] = []
    for segment_index, segment in enumerate(result.get("segments", [])):
        utterance_id = f"utt_{segment_index:04d}"
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", start))
        text = str(segment.get("text", "")).strip()
        utterances.append(
            {
                "utterance_id": utterance_id,
                "start_sec": _round_float(start),
                "end_sec": _round_float(end),
                "duration_sec": _round_float(end - start),
                "text": text,
            }
        )

        segment_words = segment.get("words") or []
        if segment_words:
            for word in segment_words:
                raw_word = str(word.get("word", "")).strip()
                clean_word = " ".join(WORD_RE.findall(raw_word))
                if not clean_word:
                    continue
                word_start = word.get("start")
                word_end = word.get("end")
                words.append(
                    {
                        "word_id": f"word_{len(words):05d}",
                        "utterance_id": utterance_id,
                        "word": clean_word,
                        "raw_word": raw_word,
                        "start_sec": _round_float(float(word_start)) if word_start is not None else None,
                        "end_sec": _round_float(float(word_end)) if word_end is not None else None,
                        "duration_sec": _round_float(float(word_end) - float(word_start))
                        if word_start is not None and word_end is not None
                        else None,
                        "probability": _round_float(float(word.get("probability")))
                        if word.get("probability") is not None
                        else None,
                        "timing_source": "whisper_word_timestamp",
                    }
                )
            continue

        tokens = WORD_RE.findall(text)
        if not tokens:
            continue
        step = max(end - start, 0.0) / len(tokens)
        for token_index, token in enumerate(tokens):
            word_start = start + token_index * step
            word_end = start + (token_index + 1) * step
            words.append(
                {
                    "word_id": f"word_{len(words):05d}",
                    "utterance_id": utterance_id,
                    "word": token,
                    "raw_word": token,
                    "start_sec": _round_float(word_start),
                    "end_sec": _round_float(word_end),
                    "duration_sec": _round_float(word_end - word_start),
                    "probability": None,
                    "timing_source": "estimated_evenly_from_utterance",
                }
            )
    return utterances, words


def _phonemize_words(words: list[dict[str, Any]], phoneme_language: str) -> tuple[list[dict[str, Any]], str | None]:
    try:
        from phonemizer import phonemize
        from phonemizer.separator import Separator
    except ImportError:
        return [], "phonemizer is not installed"

    phonemes: list[dict[str, Any]] = []
    separator = Separator(phone=" ", word="", syllable="")
    for word_row in words:
        word = str(word_row["word"]).lower().strip()
        if not word:
            continue
        try:
            phone_string = phonemize(
                [word],
                language=phoneme_language,
                backend="espeak",
                separator=separator,
                strip=True,
                preserve_punctuation=False,
                with_stress=False,
                njobs=1,
            )[0]
        except Exception as exc:
            return phonemes, f"phonemizer failed: {exc}"
        phones = [phone for phone in phone_string.split() if phone.strip()]
        if not phones:
            continue

        word_start = word_row.get("start_sec")
        word_end = word_row.get("end_sec")
        if word_start is None or word_end is None:
            for phone in phones:
                phonemes.append(
                    {
                        "phoneme_id": f"ph_{len(phonemes):06d}",
                        "word_id": word_row["word_id"],
                        "utterance_id": word_row["utterance_id"],
                        "word": word,
                        "phoneme": phone,
                        "start_sec": None,
                        "end_sec": None,
                        "duration_sec": None,
                        "timing_source": "untimed_g2p_only",
                    }
                )
            continue

        start = float(word_start)
        end = float(word_end)
        step = max(end - start, 0.0) / len(phones)
        for index, phone in enumerate(phones):
            phone_start = start + index * step
            phone_end = start + (index + 1) * step
            phonemes.append(
                {
                    "phoneme_id": f"ph_{len(phonemes):06d}",
                    "word_id": word_row["word_id"],
                    "utterance_id": word_row["utterance_id"],
                    "word": word,
                    "phoneme": phone,
                    "start_sec": _round_float(phone_start),
                    "end_sec": _round_float(phone_end),
                    "duration_sec": _round_float(phone_end - phone_start),
                    "timing_source": "approx_evenly_distributed_inside_whisper_word",
                }
            )
    return phonemes, None


def _build_text_payload(
    audio_path: Path,
    *,
    transcribe: bool,
    whisper_model: str,
    language: str | None,
    device: str | None,
    phoneme_language: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": "hum.text_alignment.v1",
        "mode": "skipped",
        "transcript": "",
        "utterances": [],
        "words": [],
        "phonemes_approx": [],
        "notes": [
            "For humming, hum_articulation in sound.json is usually more relevant than lexical phonemes.",
            "Whisper/phonemizer phonemes are approximate and not gold phone boundaries.",
            "For true phone-level boundaries, use Montreal Forced Aligner with transcript plus audio.",
        ],
    }
    if not transcribe:
        return payload

    try:
        import whisper
    except ImportError:
        payload.update({"mode": "unavailable", "error": "openai-whisper is not installed"})
        return payload

    try:
        model = whisper.load_model(whisper_model, device=device)
        kwargs: dict[str, Any] = {"verbose": False, "word_timestamps": True}
        if language:
            kwargs["language"] = language
        result = model.transcribe(str(audio_path), **kwargs)
    except TypeError:
        result = model.transcribe(str(audio_path), verbose=False, language=language)
    except Exception as exc:
        payload.update({"mode": "failed", "error": str(exc)})
        return payload

    utterances, words = _normalize_whisper_segments(result)
    phonemes, phoneme_error = _phonemize_words(words, phoneme_language)
    payload.update(
        {
            "mode": "transcribed",
            "whisper_model": whisper_model,
            "language": language,
            "phoneme_language": phoneme_language,
            "transcript": str(result.get("text", "")).strip(),
            "utterances": utterances,
            "words": words,
            "phonemes_approx": phonemes,
            "phoneme_error": phoneme_error,
        }
    )
    return payload


def _write_text_json(
    path: Path,
    audio_path: Path,
    *,
    transcribe: bool,
    whisper_model: str,
    language: str | None,
    device: str | None,
    phoneme_language: str,
) -> None:
    payload = _build_text_payload(
        audio_path,
        transcribe=transcribe,
        whisper_model=whisper_model,
        language=language,
        device=device,
        phoneme_language=phoneme_language,
    )
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render_neutral_hum(
    f0: np.ndarray,
    rms: np.ndarray,
    *,
    sr: int,
    hop_length: int,
    duration_samples: int,
) -> np.ndarray:
    sample_positions = np.arange(duration_samples, dtype=np.float32) / hop_length
    frame_positions = np.arange(len(f0), dtype=np.float32)
    f0_audio = np.interp(sample_positions, frame_positions, f0).astype(np.float32)
    rms_audio = np.interp(sample_positions, frame_positions, rms).astype(np.float32)

    voiced = f0_audio > 0.0
    env = _smooth(voiced.astype(np.float32), max(8, int(sr * 0.018)))
    if float(np.max(rms_audio)) > 0.0:
        env *= 0.35 + 0.65 * (rms_audio / float(np.max(rms_audio)))

    t = np.arange(duration_samples, dtype=np.float32) / sr
    f0_audio *= 1.0 + 0.0035 * np.sin(2.0 * np.pi * 5.0 * t)
    f0_audio[~voiced] = 0.0
    phase = np.cumsum(2.0 * np.pi * f0_audio / sr).astype(np.float32)

    y = np.zeros(duration_samples, dtype=np.float32)
    for harmonic in range(1, 9):
        partial = harmonic * f0_audio
        low_formant = np.exp(-0.5 * ((partial - 240.0) / 170.0) ** 2)
        nasal_formant = 0.32 * np.exp(-0.5 * ((partial - 1050.0) / 460.0) ** 2)
        amp = (low_formant + nasal_formant + 0.06) / harmonic
        y += amp.astype(np.float32) * np.sin(harmonic * phase)

    rng = np.random.default_rng(19)
    y += 0.0025 * rng.standard_normal(duration_samples).astype(np.float32) * env
    y *= env

    edge = min(int(sr * 0.025), max(0, duration_samples // 3))
    if edge:
        y[:edge] *= np.linspace(0.0, 1.0, edge, dtype=np.float32)
        y[-edge:] *= np.linspace(1.0, 0.0, edge, dtype=np.float32)

    peak = float(np.max(np.abs(y))) if len(y) else 0.0
    if peak > 0.0:
        y = 0.82 * y / peak
    return y.astype(np.float32)


def decompose_audio_to_hum(
    audio_path: Path,
    out_dir: Path,
    *,
    sr: int = 22050,
    frame_length: int = 2048,
    hop_length: int = 256,
    fmin: float = librosa.note_to_hz("C2"),
    fmax: float = librosa.note_to_hz("C6"),
    max_duration_s: float | None = None,
    transcribe: bool = False,
    whisper_model: str = "base",
    language: str | None = None,
    device: str | None = None,
    phoneme_language: str = "en-us",
) -> DecomposeResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    y, actual_sr = librosa.load(audio_path, sr=sr, mono=True, duration=max_duration_s)
    if not len(y):
        raise ValueError(f"Audio is empty: {audio_path}")

    times, f0, rms = _extract_f0(
        y,
        actual_sr,
        frame_length=frame_length,
        hop_length=hop_length,
        fmin=fmin,
        fmax=fmax,
    )
    onset_times, onset_envelope = _extract_onsets(y, actual_sr, hop_length)

    melody_json = out_dir / "melody.json"
    cadence_json = out_dir / "cadence.json"
    sound_json = out_dir / "sound.json"
    text_json = out_dir / "text.json"
    neutral_hum = out_dir / "neutral_hum.wav"

    _write_melody_json(
        melody_json,
        times=times,
        f0=f0,
        rms=rms,
        sr=actual_sr,
        hop_length=hop_length,
    )
    _write_cadence_json(
        cadence_json,
        onset_times=onset_times,
        onset_envelope=onset_envelope,
        sr=actual_sr,
        hop_length=hop_length,
    )
    _write_sound_json(
        sound_json,
        y=y,
        f0=f0,
        rms=rms,
        sr=actual_sr,
        hop_length=hop_length,
    )
    _write_text_json(
        text_json,
        audio_path,
        transcribe=transcribe,
        whisper_model=whisper_model,
        language=language,
        device=device,
        phoneme_language=phoneme_language,
    )
    hum = render_neutral_hum(
        f0,
        rms,
        sr=actual_sr,
        hop_length=hop_length,
        duration_samples=len(y),
    )
    sf.write(neutral_hum, hum, actual_sr)

    voiced_ratio = float(np.mean(f0 > 0.0)) if len(f0) else 0.0
    return DecomposeResult(
        audio_path=str(audio_path),
        out_dir=str(out_dir),
        melody_json=str(melody_json),
        cadence_json=str(cadence_json),
        sound_json=str(sound_json),
        text_json=str(text_json),
        neutral_hum_wav=str(neutral_hum),
        sample_rate=actual_sr,
        duration_s=round(len(y) / float(actual_sr), 3),
        frame_hz=round(actual_sr / float(hop_length), 3),
        voiced_ratio=round(voiced_ratio, 4),
        onset_count=int(len(onset_times)),
    )


def _safe_id(path: Path) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", path.stem).strip("._")
    return stem or "audio"


def iter_audio_files(root: Path, *, extensions: set[str] | None = None) -> list[Path]:
    suffixes = extensions or AUDIO_EXTENSIONS
    if root.is_file():
        return [root] if root.suffix.lower() in suffixes else []
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in suffixes)


def decompose_audio_dataset(
    input_path: Path,
    out_dir: Path,
    *,
    sr: int = 22050,
    limit: int | None = None,
    max_duration_s: float | None = None,
    transcribe: bool = False,
    whisper_model: str = "base",
    language: str | None = None,
    device: str | None = None,
    phoneme_language: str = "en-us",
) -> dict:
    audio_files = iter_audio_files(input_path)
    if limit is not None:
        audio_files = audio_files[:limit]
    out_dir.mkdir(parents=True, exist_ok=True)

    items = []
    errors = []
    seen: dict[str, int] = {}
    for audio_path in audio_files:
        clip_id = _safe_id(audio_path)
        seen[clip_id] = seen.get(clip_id, 0) + 1
        if seen[clip_id] > 1:
            clip_id = f"{clip_id}_{seen[clip_id]}"
        clip_dir = out_dir / "clips" / clip_id
        try:
            result = decompose_audio_to_hum(
                audio_path,
                clip_dir,
                sr=sr,
                max_duration_s=max_duration_s,
                transcribe=transcribe,
                whisper_model=whisper_model,
                language=language,
                device=device,
                phoneme_language=phoneme_language,
            )
            item = {"id": clip_id, **result.to_dict()}
            items.append(item)
        except Exception as exc:  # keep batch runs useful while surfacing failures
            errors.append({"id": clip_id, "audio_path": str(audio_path), "error": str(exc)})

    payload = {
        "schema": "hum.dataset_decomposition.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_path": str(input_path),
        "out_dir": str(out_dir),
        "sample_rate": sr,
        "max_duration_s": max_duration_s,
        "transcribe": transcribe,
        "whisper_model": whisper_model if transcribe else None,
        "language": language,
        "phoneme_language": phoneme_language if transcribe else None,
        "count": len(items),
        "error_count": len(errors),
        "items": items,
        "errors": errors,
    }
    index_path = out_dir / "index.json"
    index_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    payload["index_json"] = str(index_path)
    return payload
