from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
from jsonschema import Draft202012Validator

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from diarization import diarize_audio, failure_receipt, normalize_diarization_receipt  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
SCHEMAS = ROOT / "skills" / "watch" / "docs" / "architecture" / "schemas"


def validate_receipt(payload: dict) -> None:
    schema = json.loads((SCHEMAS / "watch_diarization.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda error: error.path)
    assert errors == []


def audio_file(tmp_path: Path) -> Path:
    path = tmp_path / "audio.wav"
    path.write_bytes(b"fake wav")
    return path


def service_payload() -> dict:
    return {
        "schema": "watch.diarization.v1",
        "status": "complete",
        "provider": "pyannote",
        "model": "pyannote/speaker-diarization-community-1",
        "library_version": "4.0.7",
        "device": "cpu",
        "analysis_range": {"start_seconds": 0.0, "end_seconds": 2.0, "timeline_offset_seconds": 0.0},
        "duration_seconds": 2.0,
        "turns": [
            {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"},
            {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_01"},
        ],
        "exclusive_turns": [
            {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"},
            {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_01"},
        ],
        "elapsed_seconds": 0.25,
    }


def test_normalize_success_receipt_shifts_focused_range_to_source_timeline(tmp_path: Path):
    receipt = normalize_diarization_receipt(
        service_payload(),
        audio_path=str(audio_file(tmp_path)),
        source_audio_sha256="sha256:" + "a" * 64,
        timeline_offset_seconds=10.0,
        duration_seconds=2.0,
    )

    validate_receipt(receipt)
    assert receipt["analysis_range"] == {
        "start_seconds": 10.0,
        "end_seconds": 12.0,
        "timeline_offset_seconds": 10.0,
    }
    assert receipt["turns"][0]["start"] == 10.0
    assert receipt["exclusive_turns"][1]["end"] == 12.0
    assert receipt["speakers"] == ["SPEAKER_00", "SPEAKER_01"]


def test_diarize_audio_posts_file_and_speaker_count_options(monkeypatch, tmp_path: Path):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["data"] = kwargs["data"]
        captured["files"] = kwargs["files"]
        return httpx.Response(200, json=service_payload())

    monkeypatch.setattr(httpx, "post", fake_post)

    receipt = diarize_audio(
        audio_file(tmp_path),
        mode="pyannote",
        num_speakers=2,
        timeline_offset_seconds=3.0,
        duration_seconds=2.0,
        service_url="http://127.0.0.1:9001/v1/audio/diarizations",
    )

    validate_receipt(receipt)
    assert captured["url"] == "http://127.0.0.1:9001/v1/audio/diarizations"
    assert captured["data"]["num_speakers"] == "2"
    assert captured["data"]["timeline_offset_seconds"] == "3.000"
    assert captured["files"]["file"][0] == "audio.wav"
    assert receipt["turns"][0]["start"] == 3.0
    assert receipt["source_audio_sha256"].startswith("sha256:")


def test_disabled_and_validation_failures_are_schema_valid(tmp_path: Path):
    disabled = diarize_audio(audio_file(tmp_path), mode="none")
    invalid = diarize_audio(audio_file(tmp_path), mode="pyannote", num_speakers=2, min_speakers=1)

    validate_receipt(disabled)
    validate_receipt(invalid)
    assert disabled["error_code"] == "DIARIZATION_DISABLED"
    assert invalid["error_code"] == "DIARIZATION_INFERENCE_FAILED"
    assert disabled["safe_default"] == "continue_without_speaker_attribution"


def test_connect_timeout_auth_and_bad_audio_errors_are_structured(monkeypatch, tmp_path: Path):
    audio = audio_file(tmp_path)

    def connect_error(url, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", connect_error)
    unavailable = diarize_audio(audio, mode="pyannote")
    validate_receipt(unavailable)
    assert unavailable["error_code"] == "DIARIZATION_SERVICE_UNAVAILABLE"

    def timeout(url, **kwargs):
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr(httpx, "post", timeout)
    timed_out = diarize_audio(audio, mode="pyannote")
    validate_receipt(timed_out)
    assert timed_out["error_code"] == "DIARIZATION_TIMEOUT"

    def auth(url, **kwargs):
        return httpx.Response(401, json={"error": "token required"})

    monkeypatch.setattr(httpx, "post", auth)
    auth_required = diarize_audio(audio, mode="pyannote")
    validate_receipt(auth_required)
    assert auth_required["error_code"] == "DIARIZATION_AUTH_REQUIRED"

    def bad_audio(url, **kwargs):
        return httpx.Response(400, json={"error": "invalid wav"})

    monkeypatch.setattr(httpx, "post", bad_audio)
    invalid_audio = diarize_audio(audio, mode="pyannote")
    validate_receipt(invalid_audio)
    assert invalid_audio["error_code"] == "DIARIZATION_AUDIO_INVALID"


def test_duration_limit_and_missing_audio_are_structured(tmp_path: Path):
    too_long = diarize_audio(audio_file(tmp_path), mode="pyannote", duration_seconds=10.0, max_duration_seconds=5.0)
    missing = diarize_audio(tmp_path / "missing.wav", mode="pyannote")

    validate_receipt(too_long)
    validate_receipt(missing)
    assert too_long["error_code"] == "DIARIZATION_DURATION_EXCEEDED"
    assert missing["error_code"] == "DIARIZATION_AUDIO_INVALID"


def test_failure_receipt_uses_safe_default():
    receipt = failure_receipt("failed", "DIARIZATION_INFERENCE_FAILED", "boom")

    validate_receipt(receipt)
    assert receipt["safe_default"] == "continue_without_speaker_attribution"
