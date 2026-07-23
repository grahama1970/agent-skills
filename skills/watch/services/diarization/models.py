from __future__ import annotations

from pydantic import BaseModel, Field


class SpeakerTurn(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    speaker: str


class DiarizationHealth(BaseModel):
    ok: bool
    provider: str = "pyannote"
    model: str
    device: str
    model_loaded: bool
    model_load_count: int


class DiarizationReceipt(BaseModel):
    schema: str = "watch.diarization.v1"
    status: str
    provider: str = "pyannote"
    model: str | None = None
    library_version: str | None = None
    device: str | None = None
    source_audio_path: str | None = None
    source_audio_sha256: str | None = None
    analysis_range: dict | None = None
    duration_seconds: float | None = None
    speaker_count: int | None = None
    speakers: list[str] | None = None
    turns: list[SpeakerTurn] | None = None
    exclusive_turns: list[SpeakerTurn] | None = None
    elapsed_seconds: float | None = None
    error_code: str | None = None
    error: str | None = None
    safe_default: str | None = None
