"""pyannote Community-1 engine wrapper for the Watch diarization service."""
from __future__ import annotations

import hashlib
import importlib.metadata
import os
import time
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "pyannote/speaker-diarization-community-1"
DEFAULT_VERSION = "4.0.7"


class DiarizationEngine:
    def __init__(self, model: str | None = None, device: str | None = None):
        self.model = model or os.getenv("PYANNOTE_MODEL", DEFAULT_MODEL)
        self.device = device or os.getenv("PYANNOTE_DEVICE", "cuda")
        self._pipeline = None
        self.model_load_count = 0

    @property
    def model_loaded(self) -> bool:
        return self._pipeline is not None

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "provider": "pyannote",
            "model": self.model,
            "device": self.device,
            "model_loaded": self.model_loaded,
            "model_load_count": self.model_load_count,
        }

    def load_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline
        try:
            from pyannote.audio import Pipeline
        except Exception as exc:  # pragma: no cover - exercised in service runtime
            raise RuntimeError(f"pyannote.audio import failed: {exc}") from exc

        token = os.getenv("HF_TOKEN") or None
        if token:
            pipeline = Pipeline.from_pretrained(self.model, token=token)
        else:
            pipeline = Pipeline.from_pretrained(self.model)
        try:
            import torch

            pipeline.to(torch.device(self.device))
        except Exception as exc:  # pragma: no cover - hardware-dependent
            raise RuntimeError(f"pyannote pipeline device move failed: {exc}") from exc
        self._pipeline = pipeline
        self.model_load_count += 1
        return pipeline

    def diarize(
        self,
        audio_path: Path,
        *,
        num_speakers: int | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
        timeline_offset_seconds: float = 0.0,
    ) -> dict[str, Any]:
        pipeline = self.load_pipeline()
        kwargs = {
            key: value
            for key, value in {
                "num_speakers": num_speakers,
                "min_speakers": min_speakers,
                "max_speakers": max_speakers,
            }.items()
            if value is not None
        }
        started = time.monotonic()
        output = pipeline(str(audio_path), **kwargs)
        elapsed = time.monotonic() - started
        return build_receipt(
            audio_path,
            output,
            model=self.model,
            device=self.device,
            timeline_offset_seconds=timeline_offset_seconds,
            elapsed_seconds=elapsed,
        )


def build_receipt(
    audio_path: Path,
    output: Any,
    *,
    model: str,
    device: str,
    timeline_offset_seconds: float,
    elapsed_seconds: float,
) -> dict[str, Any]:
    regular = turns_from_annotation(output.speaker_diarization)
    exclusive = turns_from_annotation(output.exclusive_speaker_diarization)
    regular, exclusive = normalize_speaker_labels(regular, exclusive)
    speakers = sorted({turn["speaker"] for turn in regular + exclusive})
    end_seconds = max([0.0] + [turn["end"] for turn in regular + exclusive])
    return {
        "schema": "watch.diarization.v1",
        "status": "complete",
        "provider": "pyannote",
        "model": model,
        "library_version": pyannote_audio_version(),
        "device": device,
        "source_audio_path": str(audio_path),
        "source_audio_sha256": sha256_file(audio_path),
        "analysis_range": {
            "start_seconds": round(float(timeline_offset_seconds), 3),
            "end_seconds": round(float(timeline_offset_seconds) + end_seconds, 3),
            "timeline_offset_seconds": round(float(timeline_offset_seconds), 3),
        },
        "duration_seconds": round(end_seconds, 3),
        "speaker_count": len(speakers),
        "speakers": speakers,
        "turns": shift_turns(regular, timeline_offset_seconds),
        "exclusive_turns": shift_turns(exclusive, timeline_offset_seconds),
        "elapsed_seconds": round(float(elapsed_seconds), 3),
    }


def turns_from_annotation(annotation: Any) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    for segment, _track, label in annotation.itertracks(yield_label=True):
        turns.append(
            {
                "start": round(float(segment.start), 3),
                "end": round(float(segment.end), 3),
                "speaker": str(label),
            }
        )
    turns.sort(key=lambda turn: (turn["start"], turn["end"], turn["speaker"]))
    return turns


def normalize_speaker_labels(
    turns: list[dict[str, Any]],
    exclusive_turns: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mapping: dict[str, str] = {}
    for turn in sorted(turns + exclusive_turns, key=lambda item: (item["start"], item["end"], item["speaker"])):
        speaker = str(turn["speaker"])
        if speaker not in mapping:
            mapping[speaker] = f"SPEAKER_{len(mapping):02d}"
    return _apply_speaker_mapping(turns, mapping), _apply_speaker_mapping(exclusive_turns, mapping)


def shift_turns(turns: list[dict[str, Any]], offset: float) -> list[dict[str, Any]]:
    return [
        {
            "start": round(float(turn["start"]) + offset, 3),
            "end": round(float(turn["end"]) + offset, 3),
            "speaker": turn["speaker"],
        }
        for turn in turns
    ]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def pyannote_audio_version() -> str:
    try:
        return importlib.metadata.version("pyannote.audio")
    except importlib.metadata.PackageNotFoundError:
        return DEFAULT_VERSION


def _apply_speaker_mapping(turns: list[dict[str, Any]], mapping: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {
            "start": turn["start"],
            "end": turn["end"],
            "speaker": mapping[str(turn["speaker"])],
        }
        for turn in turns
    ]
