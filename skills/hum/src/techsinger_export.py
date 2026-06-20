"""Export bounded hum control data into a TechSinger-compatible smoke schema."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import soundfile as sf

from .sample_renderer import _load_midi_melody


TECH_KEYS = [
    "mix_tech",
    "falsetto_tech",
    "breathy_tech",
    "bubble_tech",
    "strong_tech",
    "weak_tech",
    "pharyngeal_tech",
    "vibrato_tech",
    "glissando_tech",
]


@dataclass(frozen=True)
class TechSingerExportResult:
    out_dir: str
    metadata_json: str
    validation_json: str
    item_count: int
    error_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TechSingerValidationResult:
    out_dir: str
    validation_json: str
    item_count: int
    error_count: int
    warning_count: int
    has_glissando: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _copy_audio(src: Path, dst: Path, sample_rate: int) -> tuple[float, int]:
    y, sr = librosa.load(src, sr=sample_rate, mono=True)
    dst.parent.mkdir(parents=True, exist_ok=True)
    sf.write(dst, y.astype(np.float32), sample_rate)
    return float(len(y) / sample_rate), sample_rate


def _extract_f0(wav_path: Path, out_path: Path, *, sample_rate: int, hop_length: int) -> dict[str, Any]:
    y, sr = librosa.load(wav_path, sr=sample_rate, mono=True)
    if len(y) < 512:
        f0 = np.zeros(0, dtype=np.float32)
    else:
        frame_length = 2048 if len(y) >= 2048 else 512
        f0 = librosa.yin(
            y,
            fmin=librosa.note_to_hz("C2"),
            fmax=librosa.note_to_hz("C7"),
            sr=sr,
            frame_length=frame_length,
            hop_length=hop_length,
        ).astype(np.float32)
        rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
        threshold = max(float(np.percentile(rms, 35)) * 0.8, 1e-4)
        voiced = np.isfinite(f0) & (rms > threshold)
        f0[~voiced] = 0.0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(out_path, f0)
    voiced_f0 = f0[f0 > 0]
    return {
        "path": str(out_path),
        "frame_count": int(len(f0)),
        "voiced_frame_count": int(len(voiced_f0)),
        "voiced_ratio": round(float(len(voiced_f0) / max(len(f0), 1)), 6) if len(f0) else 0.0,
        "median_f0_hz": round(float(np.median(voiced_f0)), 4) if len(voiced_f0) else None,
    }


def _events_from_notes(
    notes: list[dict[str, Any]],
    *,
    duration_s: float,
    min_event_s: float,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    cursor = 0.0
    for note in sorted(notes, key=lambda n: (float(n.get("start", 0.0)), -float(n.get("duration", 0.0)))):
        start = max(0.0, float(note.get("start", 0.0)))
        dur = max(0.0, float(note.get("duration", 0.0)))
        end = min(duration_s, start + dur)
        if end <= cursor:
            continue
        if start > cursor + min_event_s:
            events.append(
                {
                    "ph": "<SP>",
                    "duration": start - cursor,
                    "pitch": 0,
                    "note_type": 1,
                    "glissando": 0,
                }
            )
        event_duration = end - max(start, cursor)
        if event_duration >= min_event_s:
            events.append(
                {
                    "ph": "m",
                    "duration": event_duration,
                    "pitch": int(note.get("midi", 0)),
                    "note_type": 2,
                    "glissando": 1 if note.get("pitch_bend_points") else 0,
                }
            )
        cursor = max(cursor, end)
        if cursor >= duration_s:
            break
    if cursor < duration_s - min_event_s:
        events.append(
            {
                "ph": "<SP>",
                "duration": duration_s - cursor,
                "pitch": 0,
                "note_type": 1,
                "glissando": 0,
            }
        )
    if not events:
        events.append(
            {
                "ph": "m",
                "duration": duration_s,
                "pitch": int(notes[0].get("midi", 60)) if notes else 60,
                "note_type": 2,
                "glissando": 0,
            }
        )
    total = sum(float(event["duration"]) for event in events)
    if total > 0:
        scale = duration_s / total
        for event in events:
            event["duration"] = float(event["duration"]) * scale
    return events


def _tech_arrays(events: list[dict[str, Any]]) -> dict[str, list[int]]:
    neutral = [2] * len(events)
    arrays = {key: list(neutral) for key in TECH_KEYS}
    arrays["glissando_tech"] = [1 if int(event["glissando"]) else 2 for event in events]
    return arrays


def _manifest_items(controls_manifest: Path, *, limit: int | None) -> list[dict[str, Any]]:
    payload = _read_json(controls_manifest)
    items = list(payload.get("items", []))
    if limit is not None:
        items = items[:limit]
    return items


def export_techsinger_smoke(
    controls_manifest: Path,
    out_dir: Path,
    *,
    limit: int | None = None,
    sample_rate: int = 22050,
    hop_length: int = 256,
    min_event_s: float = 0.035,
) -> TechSingerExportResult:
    """Create a TechSinger-compatible processed-data smoke directory."""
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_dir = out_dir / "wavs"
    feature_dir = out_dir / "features"
    metadata: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    phones = {"m", "<SP>"}
    speakers: dict[str, int] = {}
    feature_dir.mkdir(parents=True, exist_ok=True)

    for source_index, item in enumerate(_manifest_items(controls_manifest, limit=limit)):
        item_id = str(item.get("id") or f"item_{source_index:05d}")
        try:
            audio_path = Path(str(item["audio_path"]))
            midi_path = Path(str(item["midi_path"]))
            if not audio_path.exists():
                raise FileNotFoundError(audio_path)
            if not midi_path.exists():
                raise FileNotFoundError(midi_path)

            wav_path = wav_dir / f"{item_id}.wav"
            duration_s, _ = _copy_audio(audio_path, wav_path, sample_rate)
            f0_summary = _extract_f0(
                wav_path,
                wav_path.with_name(f"{wav_path.stem}_f0.npy"),
                sample_rate=sample_rate,
                hop_length=hop_length,
            )
            melody = _load_midi_melody(
                midi_path,
                max_duration_s=duration_s,
                min_note_duration_s=0.0,
                legato=False,
            )
            events = _events_from_notes(melody["notes"], duration_s=duration_s, min_event_s=min_event_s)
            speaker = str(item.get("speaker_id") or "female_hum_00")
            if speaker not in speakers:
                speakers[speaker] = len(speakers)
            ph = [str(event["ph"]) for event in events]
            phones.update(ph)
            row = {
                "item_name": item_id,
                "ph": ph,
                "txt": ph,
                "word": ph,
                "ph_durs": [round(float(event["duration"]), 6) for event in events],
                "wav_fn": str(wav_path),
                "singer": speaker,
                "ep_pitches": [int(event["pitch"]) for event in events],
                "ep_notedurs": [round(float(event["duration"]), 6) for event in events],
                "ep_types": [int(event["note_type"]) for event in events],
                **_tech_arrays(events),
                "source_manifest_item": item,
                "hum_export": {
                    "schema": "hum.techsinger_smoke.item.v1",
                    "source_midi": str(midi_path),
                    "f0_summary": f0_summary,
                    "duration_s": round(duration_s, 6),
                    "glissando_event_count": sum(1 for event in events if int(event["glissando"])),
                    "note_event_count": sum(1 for event in events if int(event["pitch"]) > 0),
                    "rest_event_count": sum(1 for event in events if int(event["pitch"]) == 0),
                },
            }
            (feature_dir / f"{item_id}.json").write_text(json.dumps(row["hum_export"], indent=2) + "\n", encoding="utf-8")
            metadata.append(row)
        except Exception as exc:
            errors.append({"id": item_id, "error": f"{type(exc).__name__}: {exc}"})

    metadata_path = out_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    (out_dir / "phone_set.json").write_text(json.dumps(sorted(phones), indent=2) + "\n", encoding="utf-8")
    (out_dir / "spker_set.json").write_text(json.dumps(speakers, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "spk_map.json").write_text(json.dumps(speakers, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    validation = validate_techsinger_smoke(out_dir)
    validation_payload = _read_json(Path(validation.validation_json))
    validation_payload["export_errors"] = errors
    validation_payload["export_error_count"] = len(errors)
    Path(validation.validation_json).write_text(json.dumps(validation_payload, indent=2) + "\n", encoding="utf-8")

    return TechSingerExportResult(
        out_dir=str(out_dir),
        metadata_json=str(metadata_path),
        validation_json=validation.validation_json,
        item_count=len(metadata),
        error_count=len(errors) + validation.error_count,
    )


def _validate_item(row: dict[str, Any]) -> tuple[list[str], list[str], bool]:
    errors: list[str] = []
    warnings: list[str] = []
    required = ["item_name", "ph", "ph_durs", "wav_fn", "singer", "ep_pitches", "ep_notedurs", "ep_types"]
    for key in required:
        if key not in row:
            errors.append(f"missing:{key}")

    ph = row.get("ph") or []
    lengths = {
        "ph": len(ph),
        "ph_durs": len(row.get("ph_durs") or []),
        "ep_pitches": len(row.get("ep_pitches") or []),
        "ep_notedurs": len(row.get("ep_notedurs") or []),
        "ep_types": len(row.get("ep_types") or []),
    }
    for key in TECH_KEYS:
        lengths[key] = len(row.get(key) or [])
    if len(set(lengths.values())) != 1:
        errors.append(f"length_mismatch:{lengths}")

    wav_path = Path(str(row.get("wav_fn", "")))
    if not wav_path.exists():
        errors.append(f"missing_wav:{wav_path}")
        duration_s = None
    else:
        info = sf.info(wav_path)
        duration_s = float(info.frames / info.samplerate)
        ph_duration = sum(float(v) for v in row.get("ph_durs") or [])
        if abs(ph_duration - duration_s) > 0.05:
            errors.append(f"duration_mismatch:ph={ph_duration:.4f}:wav={duration_s:.4f}")

    f0_path = wav_path.with_name(f"{wav_path.stem}_f0.npy")
    if not f0_path.exists():
        errors.append(f"missing_f0:{f0_path}")
    else:
        f0 = np.load(f0_path)
        if int(np.sum(f0 > 0)) == 0:
            errors.append(f"empty_voiced_f0:{f0_path}")

    if not any(int(v) > 0 for v in row.get("ep_pitches") or []):
        errors.append("no_note_pitch")

    has_glissando = any(int(v) == 1 for v in row.get("glissando_tech") or [])
    if not has_glissando:
        warnings.append("no_glissando_mask")
    return errors, warnings, has_glissando


def validate_techsinger_smoke(out_dir: Path) -> TechSingerValidationResult:
    metadata_path = out_dir / "metadata.json"
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    has_glissando = False
    if not metadata_path.exists():
        errors.append({"scope": "dataset", "error": f"missing_metadata:{metadata_path}"})
        metadata: list[dict[str, Any]] = []
    else:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    for filename in ["phone_set.json", "spker_set.json"]:
        if not (out_dir / filename).exists():
            errors.append({"scope": "dataset", "error": f"missing:{filename}"})

    for row in metadata:
        row_errors, row_warnings, row_has_glissando = _validate_item(row)
        has_glissando = has_glissando or row_has_glissando
        for error in row_errors:
            errors.append({"item_name": row.get("item_name"), "error": error})
        for warning in row_warnings:
            warnings.append({"item_name": row.get("item_name"), "warning": warning})

    if metadata and not has_glissando:
        warnings.append({"scope": "dataset", "warning": "no_items_with_glissando_mask"})

    payload = {
        "schema": "hum.techsinger_smoke.validation.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "out_dir": str(out_dir),
        "metadata_json": str(metadata_path),
        "item_count": len(metadata),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "has_glissando": has_glissando,
        "errors": errors,
        "warnings": warnings,
        "acceptance_checks": {
            "metadata_parses": metadata_path.exists(),
            "all_wavs_exist": not any(str(e["error"]).startswith("missing_wav") for e in errors),
            "field_lengths_match": not any(str(e["error"]).startswith("length_mismatch") for e in errors),
            "durations_match": not any(str(e["error"]).startswith("duration_mismatch") for e in errors),
            "f0_sidecars_nonempty": not any(
                str(e["error"]).startswith("missing_f0") or str(e["error"]).startswith("empty_voiced_f0")
                for e in errors
            ),
            "midi_controls_present": not any(str(e["error"]) == "no_note_pitch" for e in errors),
            "glissando_mask_present_or_explicitly_absent": len(metadata) > 0,
        },
    }
    validation_path = out_dir / "validation.json"
    validation_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return TechSingerValidationResult(
        out_dir=str(out_dir),
        validation_json=str(validation_path),
        item_count=len(metadata),
        error_count=len(errors),
        warning_count=len(warnings),
        has_glissando=has_glissando,
    )
