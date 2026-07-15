#!/usr/bin/env python3
"""Deterministic failure-mode sanity checks for the watch pipeline.

These tests monkeypatch expensive or external seams so product hardening does
not depend on live YouTube, movie-library, Whisper, model, or memory services.
"""
from __future__ import annotations

import json
import inspect
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

import watch  # noqa: E402
import video_memory  # noqa: E402
from transcribe import align_segments_to_reference  # noqa: E402


def _fake_video(tmp: Path) -> Path:
    video = tmp / "video.mp4"
    video.write_bytes(b"not a real video; all media calls are monkeypatched")
    return video


def _fake_frames(tmp: Path) -> list[dict]:
    frame = tmp / "frame_0001.jpg"
    frame.write_bytes(b"fake jpg")
    return [{"index": 0, "timestamp_seconds": 0.0, "path": str(frame), "source": "test"}]


def _base_patches(tmp: Path, *, transcript: dict | None = None, transcribe_error: Exception | None = None):
    video = _fake_video(tmp)
    frames = _fake_frames(tmp)
    visual_receipt = {
        "schema": "watch.visual_description_receipt.v1",
        "status": "all_models_failed",
        "mocked": True,
        "live": False,
        "requested_model": "test-vlm",
        "fallback_models": [],
        "frame_count": len(frames),
        "described_count": 0,
        "gate": {"status": "failed", "reason": "no_frame_descriptions"},
        "frames": [],
    }
    stack = ExitStack()
    stack.enter_context(patch.object(watch, "download", return_value={"video_path": str(video), "subtitle_path": None, "info": {"title": "Failure Fixture", "uploader": "tests"}}))
    stack.enter_context(patch.object(watch, "get_metadata", return_value={"duration_seconds": 30.0, "width": 640, "height": 360, "codec": "h264"}))
    stack.enter_context(patch.object(watch, "extract_frames", return_value=(frames, "uniform")))
    stack.enter_context(patch.object(watch, "persist_frames", return_value=[]))
    stack.enter_context(patch.object(watch, "extract_and_persist_audio", return_value=None))
    stack.enter_context(patch.object(watch, "generate_playable_segments", return_value=(frames, [])))
    stack.enter_context(patch.object(watch, "describe_scene_images", return_value=[]))
    stack.enter_context(patch.object(watch, "describe_scene_images_with_receipt", return_value=([], visual_receipt)))
    stack.enter_context(patch.object(watch, "upsert_visual_descriptions", return_value=0))
    stack.enter_context(patch.object(watch, "upsert_scene_elements", return_value=[]))
    stack.enter_context(patch.object(watch, "upsert_persona_watch_record", return_value=None))
    if transcribe_error is not None:
        stack.enter_context(patch.object(watch, "transcribe_video", side_effect=transcribe_error))
    elif transcript is not None:
        stack.enter_context(patch.object(watch, "transcribe_video", return_value=transcript))
    return stack, video


def _report(out_dir: Path) -> dict:
    return json.loads((out_dir / "report.json").read_text())


def _gaps(out_dir: Path) -> list[str]:
    return _report(out_dir)["watch_report"].get("gaps", [])


def _assert_scene_table(out_dir: Path) -> None:
    assert (out_dir / "report.html").exists(), "HTML report missing"
    report = _report(out_dir)
    rows = report.get("scene_elements", [])
    assert rows, "scene_elements missing"
    required = {
        "timecode", "text", "scene_marker_image", "movie_segment", "sound",
        "scene_marker_image_path", "visual_description", "visual_description_source",
        "visual_description_status", "audio_path", "sound_description_source",
    }
    missing = required - set(rows[0])
    assert not missing, f"scene_elements missing fields: {sorted(missing)}"


def check_unresolvable_movie_returns_nonzero() -> None:
    with tempfile.TemporaryDirectory(prefix="watch-fail-") as d:
        out = Path(d) / "out"
        with patch.object(watch, "_resolve_movie_source", return_value=None):
            code = watch.run_watch("Movie That Does Not Exist 2099", out_dir=str(out), whisper=False)
        assert code == 1


def check_movie_title_resolution_does_not_call_radarr() -> None:
    with patch.object(watch, "_find_movie_in_library", return_value=None), \
         patch.dict(watch.os.environ, {"RADARR_API_KEY": "sentinel"}, clear=False):
        resolved = watch._resolve_movie_source("Movie That Does Not Exist 2099")
    assert resolved is None
    assert not hasattr(watch, "_check_radarr_library"), "Watch must not own direct Radarr access"


def check_doc2qra_is_disabled_until_delegated_receipts_exist() -> None:
    with tempfile.TemporaryDirectory(prefix="watch-fail-") as d:
        out = Path(d) / "out"
        with patch.object(watch, "download", side_effect=AssertionError("doc2qra should fail before media work")):
            code = watch.run_watch("anything.mp4", out_dir=str(out), doc2qra=True)
    assert code == 1


def check_run_watch_default_frame_budget_matches_cli_contract() -> None:
    assert inspect.signature(watch.run_watch).parameters["max_frames"].default == 100


def check_wikipedia_cast_lookup_uses_parse_quote() -> None:
    calls: list[str] = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps({
                "parse": {
                    "text": {
                        "*": '<li><a href="/wiki/Actor">Actor Name</a> as Character Name</li>'
                    }
                }
            }).encode("utf-8")

    def fake_urlopen(req, timeout=15):
        calls.append(req.full_url)
        return FakeResponse()

    watch._CAST_CACHE.clear()
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        cast = watch._fetch_cast_map("Bad Santa: Test")
    assert cast == {"Character Name": "Actor Name"}
    assert calls and "Bad_Santa%3A_Test" in calls[0]


def check_youtube_download_failure_returns_nonzero() -> None:
    with tempfile.TemporaryDirectory(prefix="watch-fail-") as d:
        out = Path(d) / "out"
        with patch.object(watch, "download", side_effect=RuntimeError("video unavailable")):
            code = watch.run_watch("https://youtu.be/does-not-exist", out_dir=str(out), whisper=False)
        assert code == 1


def check_corrupt_local_file_returns_nonzero() -> None:
    with tempfile.TemporaryDirectory(prefix="watch-fail-") as d:
        tmp = Path(d)
        video = _fake_video(tmp)
        out = tmp / "out"
        with patch.object(watch, "download", return_value={"video_path": str(video), "subtitle_path": None, "info": {"title": "Corrupt"}}), \
             patch.object(watch, "get_metadata", side_effect=RuntimeError("ffprobe failed")):
            code = watch.run_watch(str(video), out_dir=str(out), whisper=False)
        assert code == 1


def check_frame_extraction_failure_returns_nonzero() -> None:
    with tempfile.TemporaryDirectory(prefix="watch-fail-") as d:
        tmp = Path(d)
        video = _fake_video(tmp)
        out = tmp / "out"
        with patch.object(watch, "download", return_value={"video_path": str(video), "subtitle_path": None, "info": {"title": "Frame Fail"}}), \
             patch.object(watch, "get_metadata", return_value={"duration_seconds": 30.0, "width": 640, "height": 360, "codec": "h264"}), \
             patch.object(watch, "extract_frames", side_effect=RuntimeError("ffmpeg failed")):
            code = watch.run_watch(str(video), out_dir=str(out), whisper=False)
        assert code == 1


def check_missing_english_srt_or_transcript_is_reported() -> None:
    with tempfile.TemporaryDirectory(prefix="watch-fail-") as d:
        tmp = Path(d)
        out = tmp / "out"
        stack, video = _base_patches(tmp)
        with stack, patch.object(watch, "generate_qras", side_effect=AssertionError("QRA should not run without transcript")), \
             patch.object(watch, "upsert_qras", side_effect=AssertionError("memory upsert should not run")):
            code = watch.run_watch(str(video), out_dir=str(out), whisper=False)
        assert code == 0
        assert "missing_transcript" in _gaps(out)
        assert "image_descriptions_missing" in _gaps(out)
        assert _report(out)["visual_description_receipt"]["gate"]["status"] == "failed"
        assert "transcript" not in _report(out)
        _assert_scene_table(out)
        assert _report(out)["scene_elements"][0]["visual_description_status"] == "not_analyzed"


def check_whisper_failure_is_degraded_not_crash() -> None:
    with tempfile.TemporaryDirectory(prefix="watch-fail-") as d:
        tmp = Path(d)
        out = tmp / "out"
        stack, video = _base_patches(tmp, transcribe_error=RuntimeError("open-whisper failed"))
        with stack, patch.object(watch, "generate_qras", side_effect=AssertionError("QRA should not run without transcript")), \
             patch.object(watch, "upsert_qras", side_effect=AssertionError("memory upsert should not run")):
            code = watch.run_watch(str(video), out_dir=str(out), whisper=True)
        assert code == 0
        gaps = _gaps(out)
        assert "transcription_failed" in gaps
        assert "missing_transcript" in gaps
        _assert_scene_table(out)


def check_malformed_srt_is_reported() -> None:
    with tempfile.TemporaryDirectory(prefix="watch-fail-") as d:
        tmp = Path(d)
        out = tmp / "out"
        bad_srt = tmp / "bad.en.srt"
        bad_srt.write_text("this is not a parseable SRT")
        stack, video = _base_patches(tmp)
        with stack, patch.object(watch, "parse_captions", side_effect=RuntimeError("bad SRT")), \
             patch.object(watch, "generate_qras", side_effect=AssertionError("QRA should not run without transcript")), \
             patch.object(watch, "upsert_qras", side_effect=AssertionError("memory upsert should not run")):
            code = watch.run_watch(str(video), subtitle=str(bad_srt), out_dir=str(out), whisper=False)
        assert code == 0
        gaps = _gaps(out)
        assert "caption_parse_failed" in gaps
        assert "missing_transcript" in gaps
        _assert_scene_table(out)


def check_empty_qra_generation_skips_memory_upsert() -> None:
    transcript = {
        "source": "whisper-local (test)",
        "segments": [{"text": "This is a long enough transcript sentence for deterministic QRA failure testing. " * 2, "start": 0.0, "duration": 5.0}],
        "full_text": "This is a long enough transcript sentence for deterministic QRA failure testing. " * 3,
    }
    with tempfile.TemporaryDirectory(prefix="watch-fail-") as d:
        tmp = Path(d)
        out = tmp / "out"
        stack, video = _base_patches(tmp, transcript=transcript)
        with stack, patch.object(watch, "generate_qras", return_value=[]), \
             patch.object(watch, "upsert_qras", side_effect=AssertionError("memory upsert should not run")):
            code = watch.run_watch(str(video), out_dir=str(out), whisper=True)
        assert code == 0
        assert "qra_generation_failed" in _gaps(out)
        assert _report(out)["transcript"]["segment_count"] == 1
        _assert_scene_table(out)


def check_srt_whisper_alignment_offset_is_corrected() -> None:
    captions = {
        "source": "english-srt:test.en.srt",
        "segments": [
            {"text": "I've been married twice.", "start": 92.655, "duration": 2.126},
            {"text": "I was once drafted by Lyndon Johnson", "start": 95.074, "duration": 2.084},
            {"text": "and had to live in shit-ass Mexico", "start": 97.243, "duration": 1.959},
            {"text": "for two and a half years for no reason.", "start": 99.328, "duration": 1.960},
            {"text": "I've had my eye socket punched in, a kidney taken out,", "start": 101.747, "duration": 3.503},
        ],
    }
    whisper = {
        "source": "whisper-local (test)",
        "segments": [
            {"text": "I've been married twice.", "start": 112.750, "duration": 2.600},
            {"text": "I was once drafted by Linda Johnson", "start": 115.350, "duration": 1.840},
            {"text": "and had to live in shit ass Mexico", "start": 117.190, "duration": 1.600},
            {"text": "for two and a half years for no reason.", "start": 118.790, "duration": 3.160},
            {"text": "I've had my eye socket punched in, a kidney taken out,", "start": 121.950, "duration": 3.640},
        ],
    }
    aligned, alignment = align_segments_to_reference(captions, whisper, min_matches=5)
    assert alignment and alignment["status"] == "shifted"
    assert 19.0 < alignment["offset_seconds"] < 21.0
    assert aligned["segments"][0]["original_start"] == 92.655
    assert 112.0 < aligned["segments"][0]["start"] < 114.0


def check_video_memory_recall_targets_watch_content_items() -> None:
    calls = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"found": True, "items": [{"_source": "watch_content"}], "confidence": 1.0}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            calls.append({"init": kwargs})

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, path: str, json: dict):
            calls.append({"path": path, "json": json})
            return FakeResponse()

    with patch.object(video_memory.httpx, "Client", FakeClient):
        data = video_memory.recall_video_question("What happened at 00:30?", k=3)

    assert data["items"][0]["_source"] == "watch_content"
    post_call = next(call for call in calls if call.get("path") == "/recall")
    assert post_call["json"]["collections"] == ["watch_content"]
    assert post_call["json"]["k"] == 3
    assert post_call["json"]["q"] == "What happened at 00:30?"


def check_video_memory_rejects_wrong_media_hits() -> None:
    calls = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "found": True,
                "items": [
                    {"_key": "watch-wrong", "title": "Blade.Runner.Black.Out.2022", "scores": {"bm25": 9.0}},
                    {"_key": "watch-right", "title": "Bad.Santa.Unrated.2003.BRRip.XvidHD.720p-NPW", "tags": ["watch_history", "badsantaunrated2003brripxvidhd720p-npw"]},
                ],
                "confidence": 9.0,
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            calls.append({"init": kwargs})

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, path: str, json: dict):
            calls.append({"path": path, "json": json})
            return FakeResponse()

    with patch.object(video_memory.httpx, "Client", FakeClient):
        data = video_memory.recall_video_question(
            "What does Marcus do with the money?",
            media_title="Bad Santa (2003)",
            media_slug="badsantaunrated2003brripxvidhd720p-npw",
        )

    assert data["found"] is True
    assert len(data["items"]) == 1
    assert data["items"][0]["_key"] == "watch-right"
    assert data["wrong_media_items"][0]["_key"] == "watch-wrong"
    post_call = next(call for call in calls if call.get("path") == "/recall")
    assert post_call["json"]["tags"] == ["badsantaunrated2003brripxvidhd720p-npw"]


def check_video_memory_fails_when_only_wrong_media_returns() -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "found": True,
                "items": [{"_key": "watch-wrong", "title": "Blade.Runner.Black.Out.2022"}],
                "confidence": 8.0,
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, path: str, json: dict):
            return FakeResponse()

    with patch.object(video_memory.httpx, "Client", FakeClient):
        data = video_memory.recall_video_question("Who is Bad Santa?", media_title="Bad Santa (2003)")

    assert data["found"] is False
    assert data["failure"] == "wrong_media_or_missing_media_match"
    assert data["items"] == []
    assert data["wrong_media_items"][0]["title"] == "Blade.Runner.Black.Out.2022"


def check_movie_question_can_use_brave_corroboration() -> None:
    class FakeBrave:
        @staticmethod
        def web_search(query: str, count: int = 5) -> dict:
            return {
                "query": query,
                "results": [
                    {
                        "title": "Expected movie fact",
                        "description": "A public source snippet for sanity-checking the expected response.",
                        "url": "https://example.invalid/movie",
                    }
                ],
            }

    recall_packet = {"found": True, "items": [{"_source": "watch_content"}], "confidence": 0.9}
    with patch.object(video_memory, "recall_video_question", return_value=recall_packet), \
         patch.object(video_memory, "_load_brave_search_client", return_value=FakeBrave):
        data = video_memory.ask_movie_question("why did the character leave?", movie_title="Example Film", k=3)

    assert data["watch_recall"] is recall_packet
    corroboration = data["brave_corroboration"]
    assert corroboration["available"] is True
    assert corroboration["query"] == "Example Film movie why did the character leave?"
    assert corroboration["results"][0]["title"] == "Expected movie fact"
    assert "watch_recall evidence" in data["answer_contract"]


CHECKS = [
    check_unresolvable_movie_returns_nonzero,
    check_movie_title_resolution_does_not_call_radarr,
    check_doc2qra_is_disabled_until_delegated_receipts_exist,
    check_run_watch_default_frame_budget_matches_cli_contract,
    check_wikipedia_cast_lookup_uses_parse_quote,
    check_youtube_download_failure_returns_nonzero,
    check_corrupt_local_file_returns_nonzero,
    check_frame_extraction_failure_returns_nonzero,
    check_missing_english_srt_or_transcript_is_reported,
    check_whisper_failure_is_degraded_not_crash,
    check_malformed_srt_is_reported,
    check_empty_qra_generation_skips_memory_upsert,
    check_srt_whisper_alignment_offset_is_corrected,
    check_video_memory_recall_targets_watch_content_items,
    check_video_memory_rejects_wrong_media_hits,
    check_video_memory_fails_when_only_wrong_media_returns,
    check_movie_question_can_use_brave_corroboration,
]


def main() -> int:
    failed = 0
    for check in CHECKS:
        try:
            check()
        except Exception as exc:
            failed += 1
            print(f"FAIL {check.__name__}: {exc}")
        else:
            print(f"PASS {check.__name__}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
