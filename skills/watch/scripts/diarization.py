"""Watch-side diarization service client and receipt normalization."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import httpx

from config import (
    WATCH_DIARIZATION_MAX_SECONDS,
    WATCH_DIARIZATION_MODEL,
    WATCH_DIARIZATION_TIMEOUT_SECONDS,
    WATCH_DIARIZATION_URL,
)
from diarization_contract import (
    DEFAULT_DIARIZATION_MODEL,
    DIARIZATION_SCHEMA,
    PINNED_PYANNOTE_AUDIO_VERSION,
)

SAFE_DEFAULT = "continue_without_speaker_attribution"


def diarize_audio(
    audio_path: str | Path,
    *,
    mode: str = "auto",
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    timeline_offset_seconds: float = 0.0,
    duration_seconds: float | None = None,
    service_url: str = WATCH_DIARIZATION_URL,
    timeout_seconds: float = WATCH_DIARIZATION_TIMEOUT_SECONDS,
    max_duration_seconds: float = WATCH_DIARIZATION_MAX_SECONDS,
) -> dict[str, Any]:
    """Call the configured diarization service and return a Watch receipt.

    This client does not import pyannote or load a model. It only talks to the
    local service contract and records structured failure receipts.
    """
    if mode == "none":
        return failure_receipt("disabled", "DIARIZATION_DISABLED", "diarization disabled by request")
    if mode not in {"auto", "pyannote"}:
        return failure_receipt("failed", "DIARIZATION_INFERENCE_FAILED", f"unsupported diarization mode: {mode}")

    validation_error = _speaker_count_validation_error(num_speakers, min_speakers, max_speakers)
    if validation_error:
        return failure_receipt("failed", "DIARIZATION_INFERENCE_FAILED", validation_error)

    audio = Path(audio_path)
    if not audio.exists():
        return failure_receipt("failed", "DIARIZATION_AUDIO_INVALID", f"audio file not found: {audio}")
    if duration_seconds is not None and duration_seconds > max_duration_seconds:
        return failure_receipt(
            "failed",
            "DIARIZATION_DURATION_EXCEEDED",
            f"audio duration {duration_seconds:.3f}s exceeds limit {max_duration_seconds:.3f}s",
        )

    audio_sha = sha256_file(audio)
    data: dict[str, str] = {"timeline_offset_seconds": f"{timeline_offset_seconds:.3f}"}
    for key, value in (
        ("num_speakers", num_speakers),
        ("min_speakers", min_speakers),
        ("max_speakers", max_speakers),
    ):
        if value is not None:
            data[key] = str(value)

    try:
        with audio.open("rb") as handle:
            response = httpx.post(
                service_url,
                files={"file": (audio.name, handle, "audio/wav")},
                data=data,
                timeout=timeout_seconds,
            )
    except httpx.TimeoutException as exc:
        return failure_receipt("unavailable", "DIARIZATION_TIMEOUT", str(exc) or "diarization request timed out")
    except httpx.ConnectError as exc:
        return failure_receipt("unavailable", "DIARIZATION_SERVICE_UNAVAILABLE", str(exc) or "connection failed")
    except httpx.HTTPError as exc:
        return failure_receipt("unavailable", "DIARIZATION_SERVICE_UNAVAILABLE", str(exc))

    if response.status_code in {401, 403}:
        return failure_receipt("unavailable", "DIARIZATION_AUTH_REQUIRED", _response_error(response))
    if response.status_code in {408, 504}:
        return failure_receipt("unavailable", "DIARIZATION_TIMEOUT", _response_error(response))
    if response.status_code == 400:
        return failure_receipt("failed", "DIARIZATION_AUDIO_INVALID", _response_error(response))
    if response.status_code != 200:
        return failure_receipt("failed", "DIARIZATION_INFERENCE_FAILED", _response_error(response))

    try:
        payload = response.json()
    except ValueError as exc:
        return failure_receipt("failed", "DIARIZATION_INFERENCE_FAILED", f"invalid diarization JSON: {exc}")

    if payload.get("status") != "complete":
        code = payload.get("error_code") or "DIARIZATION_INFERENCE_FAILED"
        error = payload.get("error") or "diarization service did not return a complete receipt"
        status = payload.get("status") if payload.get("status") in {"disabled", "unavailable", "failed"} else "failed"
        return failure_receipt(status, code, error)

    return normalize_diarization_receipt(
        payload,
        audio_path=str(audio),
        source_audio_sha256=audio_sha,
        timeline_offset_seconds=timeline_offset_seconds,
        duration_seconds=duration_seconds,
    )


def normalize_diarization_receipt(
    payload: dict[str, Any],
    *,
    audio_path: str,
    source_audio_sha256: str,
    timeline_offset_seconds: float = 0.0,
    duration_seconds: float | None = None,
) -> dict[str, Any]:
    """Normalize a successful service payload to the durable Watch schema."""
    shifted_turns = _shift_turns(payload.get("turns") or [], timeline_offset_seconds)
    shifted_exclusive = _shift_turns(payload.get("exclusive_turns") or [], timeline_offset_seconds)
    speakers = sorted({turn["speaker"] for turn in shifted_turns + shifted_exclusive})
    analysis_range = payload.get("analysis_range") or {}
    start = float(analysis_range.get("start_seconds", 0.0) or 0.0) + timeline_offset_seconds
    if duration_seconds is None:
        payload_duration = payload.get("duration_seconds")
        duration_seconds = float(payload_duration or 0.0)
    end = float(analysis_range.get("end_seconds", duration_seconds) or duration_seconds) + timeline_offset_seconds

    return {
        "schema": DIARIZATION_SCHEMA,
        "status": "complete",
        "provider": "pyannote",
        "model": payload.get("model") or WATCH_DIARIZATION_MODEL or DEFAULT_DIARIZATION_MODEL,
        "library_version": payload.get("library_version") or PINNED_PYANNOTE_AUDIO_VERSION,
        "device": payload.get("device") or "unknown",
        "source_audio_path": audio_path,
        "source_audio_sha256": source_audio_sha256,
        "analysis_range": {
            "start_seconds": round(start, 3),
            "end_seconds": round(end, 3),
            "timeline_offset_seconds": round(float(timeline_offset_seconds), 3),
        },
        "duration_seconds": round(float(duration_seconds or 0.0), 3),
        "speaker_count": len(speakers),
        "speakers": speakers,
        "turns": shifted_turns,
        "exclusive_turns": shifted_exclusive,
        "elapsed_seconds": round(float(payload.get("elapsed_seconds", 0.0) or 0.0), 3),
    }


def failure_receipt(status: str, error_code: str, error: str) -> dict[str, Any]:
    return {
        "schema": DIARIZATION_SCHEMA,
        "status": status,
        "provider": "pyannote",
        "error_code": error_code,
        "error": error,
        "safe_default": SAFE_DEFAULT,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _shift_turns(turns: list[dict[str, Any]], offset: float) -> list[dict[str, Any]]:
    shifted: list[dict[str, Any]] = []
    for turn in turns:
        speaker = str(turn.get("speaker", ""))
        if not speaker:
            continue
        shifted.append(
            {
                "start": round(float(turn.get("start", 0.0) or 0.0) + offset, 3),
                "end": round(float(turn.get("end", 0.0) or 0.0) + offset, 3),
                "speaker": speaker,
            }
        )
    return shifted


def _speaker_count_validation_error(
    num_speakers: int | None,
    min_speakers: int | None,
    max_speakers: int | None,
) -> str | None:
    if num_speakers is not None and (min_speakers is not None or max_speakers is not None):
        return "num_speakers cannot be combined with min_speakers or max_speakers"
    if min_speakers is not None and max_speakers is not None and min_speakers > max_speakers:
        return "min_speakers cannot exceed max_speakers"
    for name, value in (("num_speakers", num_speakers), ("min_speakers", min_speakers), ("max_speakers", max_speakers)):
        if value is not None and value <= 0:
            return f"{name} must be positive"
    return None


def _response_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text or f"HTTP {response.status_code}"
    return str(payload.get("error") or payload.get("detail") or payload)
