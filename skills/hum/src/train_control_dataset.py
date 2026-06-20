"""Build bounded MIDI/audio control datasets from HumTrans pair manifests."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from contextlib import ExitStack
from io import BytesIO
import json
from pathlib import Path
from typing import Any
import zipfile

import librosa
import numpy as np
import soundfile as sf

from .decompose import _pitch_controls
from .sample_renderer import _load_midi_melody


@dataclass(frozen=True)
class ControlDatasetResult:
    out_dir: str
    manifest_json: str
    train_count: int
    valid_count: int
    test_count: int
    total_count: int
    sample_rate: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _limit_by_split(
    rows: list[dict[str, Any]],
    *,
    train_limit: int | None,
    valid_limit: int | None,
    test_limit: int | None,
) -> list[dict[str, Any]]:
    limits = {"train": train_limit, "valid": valid_limit, "test": test_limit}
    counts = {"train": 0, "valid": 0, "test": 0}
    selected: list[dict[str, Any]] = []
    for row in rows:
        split = str(row.get("split") or "").lower()
        if split not in counts:
            continue
        limit = limits[split]
        if limit is not None and counts[split] >= limit:
            continue
        selected.append(row)
        counts[split] += 1
    return selected


def _read_zip_member(zip_path: Path, member: str) -> bytes:
    with zipfile.ZipFile(zip_path) as zf:
        return zf.read(member)


def _load_audio_member(
    row: dict[str, Any],
    *,
    sample_rate: int,
    max_duration_s: float | None,
    wav_zip: zipfile.ZipFile | None = None,
) -> tuple[np.ndarray, int]:
    data = wav_zip.read(str(row["wav_member"])) if wav_zip else _read_zip_member(Path(row["wav_zip"]), str(row["wav_member"]))
    y, sr = sf.read(BytesIO(data), dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = np.mean(y, axis=1)
    if sr != sample_rate:
        y = librosa.resample(y.astype(np.float32), orig_sr=sr, target_sr=sample_rate)
        sr = sample_rate
    if max_duration_s is not None:
        y = y[: int(round(max_duration_s * sr))]
    return y.astype(np.float32), sr


def _midi_member_to_notes(
    row: dict[str, Any],
    target_path: Path,
    *,
    midi_zip: zipfile.ZipFile | None = None,
) -> dict[str, Any]:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    data = midi_zip.read(str(row["midi_member"])) if midi_zip else _read_zip_member(Path(row["midi_zip"]), str(row["midi_member"]))
    target_path.write_bytes(data)
    return _load_midi_melody(target_path, min_note_duration_s=0.0)


def _audio_pitch_summary(y: np.ndarray, sr: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    hop_length = 256
    frame_length = 2048
    if len(y) < frame_length:
        return {"voiced_ratio": 0.0, "median_f0_hz": None, "glissando_count": 0}, []
    f0 = librosa.yin(
        y,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C6"),
        sr=sr,
        frame_length=frame_length,
        hop_length=hop_length,
    ).astype(np.float32)
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    threshold = max(float(np.percentile(rms, 35)) * 0.8, 1e-4)
    voiced = np.isfinite(f0) & (rms > threshold)
    f0[~voiced] = 0.0
    times = librosa.frames_to_time(np.arange(len(f0)), sr=sr, hop_length=hop_length).astype(np.float32)
    _, glissando_events = _pitch_controls(times, f0)
    voiced_f0 = f0[f0 > 0]
    summary = {
        "voiced_ratio": round(float(len(voiced_f0) / max(len(f0), 1)), 6),
        "median_f0_hz": round(float(np.median(voiced_f0)), 4) if len(voiced_f0) else None,
        "p10_f0_hz": round(float(np.percentile(voiced_f0, 10)), 4) if len(voiced_f0) else None,
        "p90_f0_hz": round(float(np.percentile(voiced_f0, 90)), 4) if len(voiced_f0) else None,
        "glissando_count": len(glissando_events),
    }
    return summary, glissando_events


def build_train_control_dataset(
    pairs_jsonl: Path,
    out_dir: Path,
    *,
    train_limit: int | None = 1024,
    valid_limit: int | None = 128,
    test_limit: int | None = 128,
    sample_rate: int = 22050,
    max_duration_s: float | None = 14.0,
) -> ControlDatasetResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = _limit_by_split(
        _read_jsonl(pairs_jsonl),
        train_limit=train_limit,
        valid_limit=valid_limit,
        test_limit=test_limit,
    )
    clips_dir = out_dir / "clips"
    midi_dir = out_dir / "midi"
    items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    zip_paths = {
        "wav": sorted({str(row["wav_zip"]) for row in rows if row.get("wav_zip")}),
        "midi": sorted({str(row["midi_zip"]) for row in rows if row.get("midi_zip")}),
    }
    with ExitStack() as stack:
        wav_zips = {path: stack.enter_context(zipfile.ZipFile(path)) for path in zip_paths["wav"]}
        midi_zips = {path: stack.enter_context(zipfile.ZipFile(path)) for path in zip_paths["midi"]}
        for index, row in enumerate(rows):
            clip_id = str(row["id"])
            split = str(row["split"]).lower()
            try:
                y, sr = _load_audio_member(
                    row,
                    sample_rate=sample_rate,
                    max_duration_s=max_duration_s,
                    wav_zip=wav_zips.get(str(row.get("wav_zip"))),
                )
                wav_path = clips_dir / split / f"{clip_id}.wav"
                wav_path.parent.mkdir(parents=True, exist_ok=True)
                sf.write(wav_path, y, sr)
                midi_path = midi_dir / split / f"{clip_id}.mid"
                melody = _midi_member_to_notes(
                    row,
                    midi_path,
                    midi_zip=midi_zips.get(str(row.get("midi_zip"))),
                )
                pitch_summary, glissando_events = _audio_pitch_summary(y, sr)
                duration_s = round(float(len(y) / sr), 4)
                notes = list(melody.get("notes", []))
                items.append(
                    {
                        "id": clip_id,
                        "split": split,
                        "source_index": index,
                        "audio_path": str(wav_path),
                        "midi_path": str(midi_path),
                        "duration_s": duration_s,
                        "note_count": len(notes),
                        "midi_pitch_bend_note_count": sum(1 for note in notes if note.get("pitch_bend_points")),
                        "audio_pitch": pitch_summary,
                        "audio_glissando_events": glissando_events[:24],
                        "source": row.get("source"),
                        "license": row.get("license"),
                        "speaker_id": row.get("speaker_id"),
                    }
                )
            except Exception as exc:  # keep bounded dataset build moving
                errors.append({"id": clip_id, "split": split, "error": f"{type(exc).__name__}: {exc}"})

    split_counts = {
        split: sum(1 for item in items if item["split"] == split)
        for split in ("train", "valid", "test")
    }
    manifest = {
        "schema": "hum.train_control_dataset.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pairs_jsonl": str(pairs_jsonl),
        "out_dir": str(out_dir),
        "sample_rate": sample_rate,
        "max_duration_s": max_duration_s,
        "requested_limits": {"train": train_limit, "valid": valid_limit, "test": test_limit},
        "split_counts": split_counts,
        "total_count": len(items),
        "error_count": len(errors),
        "errors": errors[:100],
        "items": items,
        "control_representation": {
            "midi": "note start/duration/pitch/velocity plus pitch_bend_points when present",
            "audio": "measured F0, loudness, glissando events, and articulation proxies are derived from WAV during training/evaluation",
            "glissando": "continuous F0/pitch-bend controls, not only discrete MIDI notes",
        },
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return ControlDatasetResult(
        out_dir=str(out_dir),
        manifest_json=str(manifest_path),
        train_count=split_counts["train"],
        valid_count=split_counts["valid"],
        test_count=split_counts["test"],
        total_count=len(items),
        sample_rate=sample_rate,
    )
