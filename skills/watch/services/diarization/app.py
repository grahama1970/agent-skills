from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from engine import DiarizationEngine

app = FastAPI(title="Watch Diarization Service")
engine = DiarizationEngine()


@app.get("/healthz")
def healthz():
    return engine.health()


@app.post("/v1/audio/diarizations")
async def diarize(
    file: UploadFile = File(...),
    num_speakers: int | None = Form(default=None),
    min_speakers: int | None = Form(default=None),
    max_speakers: int | None = Form(default=None),
    timeline_offset_seconds: float = Form(default=0.0),
):
    error = speaker_count_validation_error(num_speakers, min_speakers, max_speakers)
    if error:
        raise HTTPException(status_code=400, detail=error)

    suffix = Path(file.filename or "audio.wav").suffix or ".wav"
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="watch-diarization-", suffix=suffix, delete=False) as temp:
            temp_path = Path(temp.name)
            while chunk := await file.read(1024 * 1024):
                temp.write(chunk)
        return engine.diarize(
            temp_path,
            num_speakers=num_speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
            timeline_offset_seconds=timeline_offset_seconds,
        )
    except HTTPException:
        raise
    except RuntimeError as exc:
        status_code, error_code = classify_runtime_error(str(exc))
        return JSONResponse(
            status_code=status_code,
            content=failure_receipt(error_code, str(exc)),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"diarization inference failed: {exc}") from exc
    finally:
        if temp_path:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass


def speaker_count_validation_error(
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


def classify_runtime_error(message: str) -> tuple[int, str]:
    lowered = message.lower()
    if "401 client error" in lowered or "gated" in lowered or "restricted" in lowered or "authentication token" in lowered:
        return 403, "DIARIZATION_AUTH_REQUIRED"
    if "model" in lowered and "load" in lowered:
        return 503, "DIARIZATION_MODEL_LOAD_FAILED"
    return 500, "DIARIZATION_INFERENCE_FAILED"


def failure_receipt(error_code: str, error: str) -> dict:
    return {
        "schema": "watch.diarization.v1",
        "status": "unavailable" if error_code in {"DIARIZATION_AUTH_REQUIRED", "DIARIZATION_MODEL_LOAD_FAILED"} else "failed",
        "provider": "pyannote",
        "error_code": error_code,
        "error": error,
        "safe_default": "continue_without_speaker_attribution",
    }
