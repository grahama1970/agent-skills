"""Optional faster-whisper transcription per clip."""

from __future__ import annotations

from pathlib import Path


def transcribe_clip(clip_path: Path, language: str = "en") -> tuple[str, float]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Install transcribe extras: uv sync --extra transcribe") from exc

    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(clip_path), language=language, vad_filter=True)
    text_parts: list[str] = []
    confidences: list[float] = []
    for segment in segments:
        text_parts.append(segment.text.strip())
        if segment.avg_logprob is not None:
            confidences.append(float(min(max((segment.avg_logprob + 1.0) / 1.0, 0.0), 1.0)))
    transcript = " ".join(part for part in text_parts if part).strip()
    confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return transcript, round(confidence, 4)
