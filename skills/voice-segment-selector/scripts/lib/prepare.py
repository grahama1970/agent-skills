"""Prepare ranked candidate clips from source media."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from lib.audio_io import extract_clip, load_chapters, load_wav, normalize_to_wav, probe_duration_sec
from lib.constants import DEFAULT_MAX_CLIP_SEC, DEFAULT_MIN_CLIP_SEC, SAMPLE_RATE
from lib.gender import ClassifierMode, choose_gender, estimate_f0, load_hf_classifier
from lib.score import rank_score, score_clip
from lib.transcribe import transcribe_clip
from lib.vad import detect_speech_spans


@dataclass
class Candidate:
    id: str
    clip: str
    source: str
    start_sec: float
    end_sec: float
    duration_sec: float
    gender_label: str
    gender_score: float | None
    gender_classifier: str
    f0_guess: str
    median_f0_hz: float | None
    quality_score: float
    quality_metrics: dict[str, float]
    transcript: str
    asr_confidence: float | None
    language: str
    rank_score: float
    status: str


def _process_span_range(
    *,
    y: np.ndarray,
    sr: int,
    source_label: str,
    source_wav: Path,
    raw_dir: Path,
    spans: list[tuple[float, float]],
    classifier: ClassifierMode,
    hf_pipe,
    transcribe: bool,
    language: str,
    start_index: int,
) -> tuple[list[Candidate], int]:
    rows: list[Candidate] = []
    idx = start_index
    for start_sec, end_sec in spans:
        idx += 1
        start = int(start_sec * sr)
        end = int(end_sec * sr)
        clip_arr = y[start:end]
        quality_score, quality_metrics = score_clip(clip_arr, sr)
        median_f0, f0_guess = estimate_f0(clip_arr, sr)
        gender_label, gender_score, gender_classifier = choose_gender(
            classifier, hf_pipe, clip_arr, sr, f0_guess
        )
        clip_name = f"{idx:04d}_{start_sec:08.2f}-{end_sec:08.2f}.wav"
        clip_path = raw_dir / clip_name
        extract_clip(source_wav, start_sec, end_sec, clip_path)
        transcript = ""
        asr_confidence = None
        if transcribe:
            try:
                transcript, asr_confidence = transcribe_clip(clip_path, language=language)
            except RuntimeError:
                transcript, asr_confidence = "", None
        row = Candidate(
            id=f"{idx:04d}",
            clip=str(clip_path.relative_to(raw_dir.parent.parent)),
            source=source_label,
            start_sec=round(start_sec, 3),
            end_sec=round(end_sec, 3),
            duration_sec=round(end_sec - start_sec, 3),
            gender_label=gender_label,
            gender_score=round(gender_score, 4) if gender_score is not None else None,
            gender_classifier=gender_classifier,
            f0_guess=f0_guess,
            median_f0_hz=round(median_f0, 2) if median_f0 is not None else None,
            quality_score=quality_score,
            quality_metrics=quality_metrics,
            transcript=transcript,
            asr_confidence=asr_confidence,
            language=language,
            rank_score=0.0,
            status="pending",
        )
        row.rank_score = round(rank_score(asdict(row)), 5)
        rows.append(row)
    return rows, idx


def prepare_job(
    *,
    input_path: Path,
    job_dir: Path,
    classifier: ClassifierMode = "both",
    min_clip_sec: float = DEFAULT_MIN_CLIP_SEC,
    max_clip_sec: float = DEFAULT_MAX_CLIP_SEC,
    transcribe: bool = True,
    language: str = "en",
    chapters_json: Path | None = None,
    max_duration_sec: float = 7200.0,
) -> dict:
    job_dir.mkdir(parents=True, exist_ok=True)
    workdir = job_dir / "_work"
    workdir.mkdir(parents=True, exist_ok=True)
    raw_dir = job_dir / "clips" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    source_wav = workdir / "source.mono16k.wav"
    normalize_to_wav(input_path, source_wav)
    duration_sec = probe_duration_sec(source_wav)

    hf_pipe = None
    if classifier in {"hf", "both"}:
        hf_pipe = load_hf_classifier()

    candidates: list[Candidate] = []
    idx = 0

    if chapters_json and chapters_json.exists():
        for chapter in load_chapters(chapters_json):
            chapter_start = chapter["start_sec"]
            chapter_end = min(chapter["end_sec"], duration_sec)
            chapter_wav = workdir / f"chapter_{chapter_start:.0f}.wav"
            extract_clip(source_wav, chapter_start, chapter_end, chapter_wav)
            y, sr = load_wav(chapter_wav)
            spans = detect_speech_spans(
                y, sr, min_clip_sec=min_clip_sec, max_clip_sec=max_clip_sec
            )
            shifted = [(chapter_start + s, chapter_start + e) for s, e in spans]
            rows, idx = _process_span_range(
                y=y,
                sr=sr,
                source_label=f"{input_path.name}::{chapter['title']}",
                source_wav=source_wav,
                raw_dir=raw_dir,
                spans=shifted,
                classifier=classifier,
                hf_pipe=hf_pipe,
                transcribe=transcribe,
                language=language,
                start_index=idx,
            )
            candidates.extend(rows)
    else:
        if duration_sec > max_duration_sec:
            raise ValueError(
                f"Input is {duration_sec:.0f}s; use --chapters-json or split input (<={max_duration_sec:.0f}s)."
            )
        y, sr = load_wav(source_wav)
        spans = detect_speech_spans(
            y, sr, min_clip_sec=min_clip_sec, max_clip_sec=max_clip_sec
        )
        candidates, _ = _process_span_range(
            y=y,
            sr=sr,
            source_label=input_path.name,
            source_wav=source_wav,
            raw_dir=raw_dir,
            spans=spans,
            classifier=classifier,
            hf_pipe=hf_pipe,
            transcribe=transcribe,
            language=language,
            start_index=0,
        )

    candidates.sort(key=lambda row: row.rank_score, reverse=True)
    candidates_path = job_dir / "candidates.jsonl"
    with candidates_path.open("w", encoding="utf-8") as handle:
        for row in candidates:
            handle.write(json.dumps(asdict(row)) + "\n")

    manifest = {
        "job_dir": str(job_dir.resolve()),
        "schema_version": "voice-segment-selector.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "input": str(input_path.resolve()),
        "source_wav": str(source_wav.resolve()),
        "duration_sec": round(duration_sec, 3),
        "classifier": classifier,
        "min_clip_sec": min_clip_sec,
        "max_clip_sec": max_clip_sec,
        "transcribe": transcribe,
        "candidate_count": len(candidates),
        "male_count": sum(1 for row in candidates if row.gender_label == "male"),
        "female_count": sum(1 for row in candidates if row.gender_label == "female"),
        "unknown_count": sum(1 for row in candidates if row.gender_label == "unknown"),
        "candidates_jsonl": str(candidates_path.resolve()),
    }
    (job_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest
