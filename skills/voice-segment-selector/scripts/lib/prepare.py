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
from lib.sources import SourceInput, resolve_source_path


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
    plain_caption: str
    transcript_draft: str
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
    slice_offset_sec: float = 0.0,
) -> tuple[list[Candidate], int]:
    rows: list[Candidate] = []
    idx = start_index
    for start_sec, end_sec in spans:
        idx += 1
        local_start_sec = start_sec - slice_offset_sec
        local_end_sec = end_sec - slice_offset_sec
        start = max(0, int(local_start_sec * sr))
        end = min(len(y), int(local_end_sec * sr))
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
            plain_caption=transcript,
            transcript_draft=transcript,
            asr_confidence=asr_confidence,
            language=language,
            rank_score=0.0,
            status="pending",
        )
        row.rank_score = round(rank_score(asdict(row)), 5)
        rows.append(row)
    return rows, idx


def _prepare_one_source(
    *,
    input_path: Path,
    job_dir: Path,
    source_label: str,
    classifier: ClassifierMode,
    min_clip_sec: float,
    max_clip_sec: float,
    transcribe: bool,
    language: str,
    chapters_json: Path | None,
    max_duration_sec: float,
    start_sec: float | None,
    end_sec: float | None,
    hf_pipe,
    raw_dir: Path,
    workdir: Path,
    start_index: int = 0,
) -> tuple[list[Candidate], dict]:
    source_slug = source_label.replace("/", "_").replace(":", "_")
    source_workdir = workdir / "sources" / source_slug
    source_workdir.mkdir(parents=True, exist_ok=True)

    source_wav = source_workdir / "source.mono16k.wav"
    normalize_to_wav(input_path, source_wav)
    duration_sec = probe_duration_sec(source_wav)

    candidates: list[Candidate] = []
    idx = start_index
    range_start = 0.0 if start_sec is None else max(0.0, float(start_sec))
    range_end = duration_sec if end_sec is None else min(duration_sec, float(end_sec))
    if range_end <= range_start:
        raise ValueError(
            f"Invalid source range for {source_label}: start_sec={start_sec}, end_sec={end_sec}"
        )

    if chapters_json and chapters_json.exists():
        for chapter in load_chapters(chapters_json):
            chapter_start = max(chapter["start_sec"], range_start)
            chapter_end = min(chapter["end_sec"], range_end)
            if chapter_end <= chapter_start:
                continue
            chapter_wav = source_workdir / f"chapter_{chapter_start:.0f}.wav"
            extract_clip(source_wav, chapter_start, chapter_end, chapter_wav)
            y, sr = load_wav(chapter_wav)
            spans = detect_speech_spans(
                y, sr, min_clip_sec=min_clip_sec, max_clip_sec=max_clip_sec
            )
            shifted = [(chapter_start + s, chapter_start + e) for s, e in spans]
            rows, idx = _process_span_range(
                y=y,
                sr=sr,
                source_label=f"{source_label}::{chapter['title']}",
                source_wav=source_wav,
                raw_dir=raw_dir,
                spans=shifted,
                classifier=classifier,
                hf_pipe=hf_pipe,
                transcribe=transcribe,
                language=language,
                start_index=idx,
                slice_offset_sec=chapter_start,
            )
            candidates.extend(rows)
    else:
        selected_duration_sec = range_end - range_start
        if selected_duration_sec > max_duration_sec:
            raise ValueError(
                f"Selected input range for {source_label} is {selected_duration_sec:.0f}s; "
                f"use --chapters-json, per-source start/end, or split input (<={max_duration_sec:.0f}s)."
            )
        range_wav = source_wav
        slice_offset = 0.0
        effective_label = source_label
        if start_sec is not None or end_sec is not None:
            range_wav = source_workdir / f"range_{range_start:.0f}_{range_end:.0f}.wav"
            extract_clip(source_wav, range_start, range_end, range_wav)
            slice_offset = range_start
            effective_label = f"{source_label}::{range_start:.3f}-{range_end:.3f}"
        y, sr = load_wav(range_wav)
        spans = detect_speech_spans(
            y, sr, min_clip_sec=min_clip_sec, max_clip_sec=max_clip_sec
        )
        if slice_offset:
            spans = [(slice_offset + s, slice_offset + e) for s, e in spans]
        rows, idx = _process_span_range(
            y=y,
            sr=sr,
            source_label=effective_label,
            source_wav=source_wav,
            raw_dir=raw_dir,
            spans=spans,
            classifier=classifier,
            hf_pipe=hf_pipe,
            transcribe=transcribe,
            language=language,
            start_index=idx,
            slice_offset_sec=slice_offset,
        )
        candidates.extend(rows)

    source_manifest = {
        "input": str(input_path.resolve()),
        "source_label": source_label,
        "source_wav": str(source_wav.resolve()),
        "duration_sec": round(duration_sec, 3),
        "range_start_sec": round(range_start, 3),
        "range_end_sec": round(range_end, 3),
        "selected_duration_sec": round(range_end - range_start, 3),
        "candidate_count": len(candidates),
        "male_count": sum(1 for row in candidates if row.gender_label == "male"),
        "female_count": sum(1 for row in candidates if row.gender_label == "female"),
        "unknown_count": sum(1 for row in candidates if row.gender_label == "unknown"),
    }
    return candidates, source_manifest


def _write_job_outputs(
    *,
    job_dir: Path,
    candidates: list[Candidate],
    manifest: dict,
) -> dict:
    candidates.sort(key=lambda row: row.rank_score, reverse=True)
    candidates_path = job_dir / "candidates.jsonl"
    with candidates_path.open("w", encoding="utf-8") as handle:
        for row in candidates:
            handle.write(json.dumps(asdict(row)) + "\n")

    manifest = {
        **manifest,
        "candidate_count": len(candidates),
        "male_count": sum(1 for row in candidates if row.gender_label == "male"),
        "female_count": sum(1 for row in candidates if row.gender_label == "female"),
        "unknown_count": sum(1 for row in candidates if row.gender_label == "unknown"),
        "candidates_jsonl": str(candidates_path.resolve()),
    }
    (job_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


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
    start_sec: float | None = None,
    end_sec: float | None = None,
) -> dict:
    job_dir.mkdir(parents=True, exist_ok=True)
    workdir = job_dir / "_work"
    workdir.mkdir(parents=True, exist_ok=True)
    raw_dir = job_dir / "clips" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    hf_pipe = None
    if classifier in {"hf", "both"}:
        hf_pipe = load_hf_classifier()

    candidates, source_manifest = _prepare_one_source(
        input_path=input_path,
        job_dir=job_dir,
        source_label=input_path.name,
        classifier=classifier,
        min_clip_sec=min_clip_sec,
        max_clip_sec=max_clip_sec,
        transcribe=transcribe,
        language=language,
        chapters_json=chapters_json,
        max_duration_sec=max_duration_sec,
        start_sec=start_sec,
        end_sec=end_sec,
        hf_pipe=hf_pipe,
        raw_dir=raw_dir,
        workdir=workdir,
        start_index=0,
    )
    manifest = {
        "job_dir": str(job_dir.resolve()),
        "schema_version": "voice-segment-selector.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "input": str(input_path.resolve()),
        "inputs": [source_manifest],
        "source_wav": source_manifest["source_wav"],
        "duration_sec": source_manifest["duration_sec"],
        "range_start_sec": source_manifest["range_start_sec"],
        "range_end_sec": source_manifest["range_end_sec"],
        "selected_duration_sec": source_manifest["selected_duration_sec"],
        "classifier": classifier,
        "min_clip_sec": min_clip_sec,
        "max_clip_sec": max_clip_sec,
        "transcribe": transcribe,
    }
    return _write_job_outputs(job_dir=job_dir, candidates=candidates, manifest=manifest)


def prepare_multi_job(
    *,
    sources: list[SourceInput],
    job_dir: Path,
    classifier: ClassifierMode = "both",
    min_clip_sec: float = DEFAULT_MIN_CLIP_SEC,
    max_clip_sec: float = DEFAULT_MAX_CLIP_SEC,
    transcribe: bool = True,
    language: str = "en",
    max_duration_sec: float = 7200.0,
    download_youtube: bool = True,
) -> dict:
    job_dir.mkdir(parents=True, exist_ok=True)
    workdir = job_dir / "_work"
    workdir.mkdir(parents=True, exist_ok=True)
    raw_dir = job_dir / "clips" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    hf_pipe = None
    if classifier in {"hf", "both"}:
        hf_pipe = load_hf_classifier()

    all_candidates: list[Candidate] = []
    source_manifests: list[dict] = []
    idx = 0
    for source_index, source in enumerate(sources, start=1):
        input_path, source_label = resolve_source_path(
            source,
            job_dir=job_dir,
            source_index=source_index,
            download_youtube=download_youtube,
        )
        rows, source_manifest = _prepare_one_source(
            input_path=input_path,
            job_dir=job_dir,
            source_label=source_label,
            classifier=classifier,
            min_clip_sec=min_clip_sec,
            max_clip_sec=max_clip_sec,
            transcribe=transcribe,
            language=language,
            chapters_json=None,
            max_duration_sec=max_duration_sec,
            start_sec=source.start_sec,
            end_sec=source.end_sec,
            hf_pipe=hf_pipe,
            raw_dir=raw_dir,
            workdir=workdir,
            start_index=idx,
        )
        idx += len(rows)
        all_candidates.extend(rows)
        source_manifests.append(source_manifest)

    manifest = {
        "job_dir": str(job_dir.resolve()),
        "schema_version": "voice-segment-selector.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "input_count": len(sources),
        "inputs": source_manifests,
        "classifier": classifier,
        "min_clip_sec": min_clip_sec,
        "max_clip_sec": max_clip_sec,
        "transcribe": transcribe,
    }
    return _write_job_outputs(job_dir=job_dir, candidates=all_candidates, manifest=manifest)
