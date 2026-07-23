from __future__ import annotations

import json
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import watch  # noqa: E402


def base_patches(tmp: Path, transcript: dict):
    video = tmp / "video.mp4"
    audio = tmp / "audio.wav"
    frame = tmp / "frame_0001.jpg"
    video.write_bytes(b"fake video")
    audio.write_bytes(b"fake audio")
    frame.write_bytes(b"fake frame")
    frames = [{"index": 0, "timestamp_seconds": 0.0, "path": str(frame)}]
    visual_receipt = {
        "schema": "watch.visual_description_receipt.v1",
        "status": "all_models_failed",
        "mocked": True,
        "live": False,
        "requested_model": "test",
        "fallback_models": [],
        "frame_count": 1,
        "described_count": 0,
        "gate": {"status": "failed", "reason": "no_frame_descriptions"},
        "frames": [],
    }
    stack = ExitStack()
    stack.enter_context(patch.object(watch, "download", return_value={"video_path": str(video), "subtitle_path": None, "info": {"title": "Diarization Fixture", "uploader": "tests"}}))
    stack.enter_context(patch.object(watch, "get_metadata", return_value={"duration_seconds": 2.0, "width": 640, "height": 360, "codec": "h264"}))
    stack.enter_context(patch.object(watch, "extract_frames", return_value=(frames, "uniform")))
    stack.enter_context(patch.object(watch, "persist_frames", return_value=[]))
    stack.enter_context(patch.object(watch, "extract_and_persist_audio", return_value=str(audio)))
    stack.enter_context(patch.object(watch, "describe_scene_images_with_receipt", return_value=([], visual_receipt)))
    stack.enter_context(patch.object(watch, "generate_playable_segments", return_value=(frames, [])))
    stack.enter_context(patch.object(watch, "transcribe_video", return_value=transcript))
    stack.enter_context(patch.object(watch, "generate_qras", return_value=[]))
    stack.enter_context(patch.object(watch, "upsert_visual_descriptions", return_value=0))
    stack.enter_context(patch.object(watch, "upsert_scene_elements", return_value=[]))
    return stack


def transcript() -> dict:
    return {
        "source": "whisper-local (test)",
        "segments": [{"text": "Hello there.", "start": 0.0, "duration": 2.0}],
        "full_text": "Hello there.",
    }


def complete_diarization() -> dict:
    return {
        "schema": "watch.diarization.v1",
        "status": "complete",
        "provider": "pyannote",
        "model": "pyannote/speaker-diarization-community-1",
        "library_version": "4.0.7",
        "device": "cpu",
        "source_audio_path": "audio.wav",
        "source_audio_sha256": "sha256:" + "a" * 64,
        "analysis_range": {"start_seconds": 0.0, "end_seconds": 2.0, "timeline_offset_seconds": 0.0},
        "duration_seconds": 2.0,
        "speaker_count": 1,
        "speakers": ["SPEAKER_00"],
        "turns": [{"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"}],
        "exclusive_turns": [{"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"}],
        "elapsed_seconds": 0.1,
    }


def failed_diarization() -> dict:
    return {
        "schema": "watch.diarization.v1",
        "status": "unavailable",
        "provider": "pyannote",
        "error_code": "DIARIZATION_SERVICE_UNAVAILABLE",
        "error": "connection refused",
        "safe_default": "continue_without_speaker_attribution",
    }


def test_watch_run_writes_diarization_and_speaker_attributed_reports():
    with tempfile.TemporaryDirectory(prefix="watch-diarization-") as d:
        tmp = Path(d)
        out = tmp / "out"
        with base_patches(tmp, transcript()), patch.object(watch, "diarize_audio", return_value=complete_diarization()):
            code = watch.run_watch(str(tmp / "video.mp4"), out_dir=str(out), whisper=True, diarization="auto")

        assert code == 0
        diarization = json.loads((out / "diarization.json").read_text(encoding="utf-8"))
        enriched_transcript = json.loads((out / "transcript.json").read_text(encoding="utf-8"))
        report = json.loads((out / "report.json").read_text(encoding="utf-8"))
        html = (out / "report.html").read_text(encoding="utf-8")

        assert diarization["status"] == "complete"
        assert enriched_transcript["segments"][0]["speaker"] == "SPEAKER_00"
        assert enriched_transcript["speaker_attribution"]["identity_boundary"]["promotion_allowed"] is False
        assert report["scene_elements"][0]["speaker_ids"] == ["SPEAKER_00"]
        assert "SPEAKER_00" in html


def test_require_diarization_fails_after_writing_receipt_and_report():
    with tempfile.TemporaryDirectory(prefix="watch-diarization-") as d:
        tmp = Path(d)
        out = tmp / "out"
        with base_patches(tmp, transcript()), patch.object(watch, "diarize_audio", return_value=failed_diarization()):
            code = watch.run_watch(
                str(tmp / "video.mp4"),
                out_dir=str(out),
                whisper=True,
                diarization="pyannote",
                require_diarization=True,
            )

        assert code == 1
        diarization = json.loads((out / "diarization.json").read_text(encoding="utf-8"))
        report = json.loads((out / "report.json").read_text(encoding="utf-8"))
        assert diarization["error_code"] == "DIARIZATION_SERVICE_UNAVAILABLE"
        assert "diarization_service_unavailable" in report["watch_report"]["gaps"]
