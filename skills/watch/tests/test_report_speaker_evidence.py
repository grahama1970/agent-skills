from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from report import build_scene_elements, write_html_report, write_markdown_report, write_report  # noqa: E402
from storage import upsert_scene_elements  # noqa: E402


def frames(tmp_path: Path) -> list[dict]:
    frame = tmp_path / "frame_0001.jpg"
    frame.write_bytes(b"fake image")
    return [{"index": 0, "timestamp_seconds": 0.0, "path": str(frame)}]


def attributed_transcript() -> dict:
    return {
        "source": "whisper-local (test)",
        "segments": [
            {
                "text": "First speaker line.",
                "start": 0.0,
                "duration": 1.0,
                "speaker": "SPEAKER_00",
                "speaker_source": "pyannote_exclusive",
                "speaker_status": "assigned",
                "speaker_overlap_seconds": 1.0,
                "speaker_overlap_ratio": 1.0,
                "speaker_candidates": [
                    {"speaker": "SPEAKER_00", "overlap_seconds": 1.0, "overlap_ratio": 1.0}
                ],
                "overlapping_speech": False,
            },
            {
                "text": "Second speaker line.",
                "start": 1.0,
                "duration": 1.0,
                "speaker": "SPEAKER_01",
                "speaker_source": "pyannote_exclusive",
                "speaker_status": "multiple",
                "speaker_overlap_seconds": 0.8,
                "speaker_overlap_ratio": 0.8,
                "speaker_candidates": [
                    {"speaker": "SPEAKER_01", "overlap_seconds": 0.8, "overlap_ratio": 0.8},
                    {"speaker": "SPEAKER_00", "overlap_seconds": 0.2, "overlap_ratio": 0.2},
                ],
                "overlapping_speech": True,
            },
        ],
        "full_text": "First speaker line. Second speaker line.",
        "diarization_artifact_path": "diarization.json",
    }


def test_scene_elements_expose_bounded_anonymous_speaker_evidence(tmp_path: Path):
    rows = build_scene_elements(frames(tmp_path), 2.0, attributed_transcript())

    assert rows[0]["speaker_ids"] == ["SPEAKER_00", "SPEAKER_01"]
    assert rows[0]["speaker_attribution_status"] == "multiple"
    assert rows[0]["overlapping_speech"] is True
    assert rows[0]["speaker_attribution_source"] == "transcript"
    assert rows[0]["diarization_source"] == "pyannote_exclusive"
    assert rows[0]["diarization_artifact_path"] == "diarization.json"
    assert rows[0]["speaker_turns"] == [
        {"speaker": "SPEAKER_00", "start": 0.0, "end": 1.0},
        {"speaker": "SPEAKER_01", "start": 1.0, "end": 2.0},
    ]


def test_scene_elements_do_not_invent_speakers_without_attribution(tmp_path: Path):
    transcript = {
        "source": "whisper-local (test)",
        "segments": [{"text": "Plain transcript.", "start": 0.0, "duration": 1.0}],
        "full_text": "Plain transcript.",
    }

    rows = build_scene_elements(frames(tmp_path), 1.0, transcript)

    assert "speaker_ids" not in rows[0]
    assert "speaker_attribution_status" not in rows[0]


def test_reports_render_speaker_evidence_without_changing_transcript_text(tmp_path: Path):
    transcript = attributed_transcript()
    markdown_path = tmp_path / "report.md"
    html_path = tmp_path / "report.html"
    json_path = tmp_path / "report.json"

    write_markdown_report(markdown_path, "fixture.mp4", "Fixture", 2.0, "test", frames(tmp_path), transcript)
    write_html_report(html_path, "fixture.mp4", "Fixture", 2.0, "test", frames(tmp_path), transcript)
    write_report(json_path, "fixture.mp4", "Fixture", 2.0, "test", frames(tmp_path), transcript)

    markdown = markdown_path.read_text(encoding="utf-8")
    html = html_path.read_text(encoding="utf-8")
    report = json.loads(json_path.read_text(encoding="utf-8"))

    assert "[SPEAKER_00] First speaker line." in markdown
    assert "First speaker line." in markdown
    assert "SPEAKER_00" in html
    assert "speaker-chip" in html
    assert report["transcript"]["segments"][0]["text"] == "First speaker line."
    assert report["scene_elements"][0]["speaker_ids"] == ["SPEAKER_00", "SPEAKER_01"]


def test_storage_persists_bounded_speaker_fields_and_tags():
    captured: list[dict] = []

    def fake_post(url, **kwargs):
        captured.extend(kwargs["json"]["documents"])
        return type("Resp", (), {"status_code": 200, "text": "ok"})()

    elements = [
        {
            "timecode": "00:00",
            "text": "First speaker line.",
            "srt_text": "",
            "movie_segment": "00:00-00:02",
            "visual_description": "",
            "scene_marker_image_path": "",
            "diff_info": {},
            "speaker_ids": ["SPEAKER_00"],
            "speaker_turns": [{"speaker": "SPEAKER_00", "start": 0.0, "end": 1.0}],
            "speaker_attribution_status": "assigned",
            "overlapping_speech": False,
            "diarization_source": "pyannote_exclusive",
        }
    ]

    with patch("storage.httpx.post", fake_post):
        keys = upsert_scene_elements(elements, "fixture.mp4", "Fixture", "fixture", "2026-07-23T00:00:00Z")

    assert keys
    doc = captured[0]
    assert doc["speaker_ids"] == ["SPEAKER_00"]
    assert json.loads(doc["speaker_turns"]) == [{"speaker": "SPEAKER_00", "start": 0.0, "end": 1.0}]
    assert doc["speaker_attribution_status"] == "assigned"
    assert "diarized" in doc["tags"]
    assert "speaker:SPEAKER_00" in doc["tags"]


def test_storage_does_not_write_speaker_fields_without_attribution():
    captured: list[dict] = []

    def fake_post(url, **kwargs):
        captured.extend(kwargs["json"]["documents"])
        return type("Resp", (), {"status_code": 200, "text": "ok"})()

    elements = [
        {
            "timecode": "00:00",
            "text": "Plain line.",
            "srt_text": "",
            "movie_segment": "00:00-00:02",
            "visual_description": "",
            "scene_marker_image_path": "",
            "diff_info": {},
        }
    ]

    with patch("storage.httpx.post", fake_post):
        upsert_scene_elements(elements, "fixture.mp4", "Fixture", "fixture", "2026-07-23T00:00:00Z")

    doc = captured[0]
    assert "speaker_ids" not in doc
    assert "speaker_turns" not in doc
    assert "diarized" not in doc["tags"]
