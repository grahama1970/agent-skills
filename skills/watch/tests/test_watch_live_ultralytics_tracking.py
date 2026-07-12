import json
import sys
from argparse import Namespace
from pathlib import Path

from jsonschema import Draft202012Validator

WATCH_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WATCH_DIR))

from scripts.live_ultralytics_tracking import (
    _candidate_entities,
    _event_validator,
    _frame_summary,
    color_for_id,
    parse_source,
)


SCHEMA_PATH = WATCH_DIR / "docs" / "architecture" / "watch_track_observations.schema.json"


def test_parse_source_converts_camera_index_only() -> None:
    assert parse_source("0") == 0
    assert parse_source("rtsp://camera.local/stream") == "rtsp://camera.local/stream"
    assert parse_source("/tmp/clip.mp4") == "/tmp/clip.mp4"


def test_color_for_id_is_stable() -> None:
    assert color_for_id("track_7") == color_for_id("track_7")
    assert color_for_id("track_7") != color_for_id("track_8")


def test_candidate_entities_are_provisional_identity_hints_only() -> None:
    args = Namespace(
        attach_domain_candidate=True,
        candidate_name="Willie",
        candidate_actor_name="Billy Bob Thornton",
        candidate_entity_id=None,
    )

    assert _candidate_entities(args) == [
        {
            "entity_id": "movie_domain_entities/willie_provisional",
            "name": "Willie",
            "kind": "CHARACTER",
            "actor_name": "Billy Bob Thornton",
            "confidence": 0.5,
            "status": "PROVISIONAL",
            "basis": ["movie_domain_memory"],
        }
    ]


def test_watch_live_track_event_contract_accepts_stage1_person_track() -> None:
    event = {
        "event_type": "track_update",
        "schema_version": "watch.live_track_update.v1",
        "stream_id": "watch_stream_modal_live",
        "asset_uid": "bad_santa_unrated_2003",
        "segment_id": "seg_0005",
        "media_time_seconds": 96.2,
        "track_id": "track_1",
        "bbox_xyxy": [10, 20, 200, 300],
        "detected_class": "person",
        "candidate_entities": [],
        "status": "PROVISIONAL",
        "emitted_at": "2026-06-28T15:00:00Z",
    }

    validator = _event_validator(SCHEMA_PATH)
    assert isinstance(validator, Draft202012Validator)
    validator.validate(event)


def test_sse_track_update_frame_is_json_parseable() -> None:
    event = {
        "event_type": "track_update",
        "schema_version": "watch.live_track_update.v1",
        "stream_id": "watch_stream_modal_live",
        "asset_uid": "bad_santa_unrated_2003",
        "segment_id": "seg_0005",
        "media_time_seconds": 96.2,
        "track_id": "track_1",
        "bbox_xyxy": [10, 20, 200, 300],
        "detected_class": "person",
        "candidate_entities": [],
        "status": "PROVISIONAL",
        "emitted_at": "2026-06-28T15:00:00Z",
    }
    frame = f"event: track_update\ndata: {json.dumps(event, sort_keys=True)}\n\n"
    assert frame.startswith("event: track_update\n")
    payload = frame.split("data: ", 1)[1].strip()
    assert json.loads(payload)["track_id"] == "track_1"


def test_canvas_frame_summary_tracks_stage1_scope(tmp_path: Path) -> None:
    args = Namespace(
        source="/tmp/clip.mp4",
        model="yolo11n.pt",
        tracker="bytetrack.yaml",
        sample_fps=5.0,
    )
    frames = [
        {
            "type": "frame",
            "media_time_seconds": 96.0,
            "tracks": [{"track_id": "track_7"}],
        }
    ]
    summary = _frame_summary(args=args, frames=frames, frame_log_path=tmp_path / "frames.jsonl")

    assert summary["stage"] == "STAGE_1_DETECT_AND_TRACK_CANVAS_STREAM"
    assert summary["frame_count"] == 1
    assert summary["track_ids"] == ["track_7"]
    assert summary["mocked"] is False
    assert summary["live"] is True
