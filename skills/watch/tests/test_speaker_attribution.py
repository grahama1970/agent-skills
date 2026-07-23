from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from skills.watch.scripts.speaker_attribution import attribute_speakers

ROOT = Path(__file__).resolve().parents[3]
SCHEMAS = ROOT / "skills" / "watch" / "docs" / "architecture" / "schemas"


def schema_validator() -> Draft202012Validator:
    schema = json.loads((SCHEMAS / "watch_speaker_attribution.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def diarization_payload() -> dict:
    return {
        "schema": "watch.diarization.v1",
        "status": "complete",
        "provider": "pyannote",
        "artifact_path": "diarization.json",
        "turns": [
            {"start": 0.0, "end": 4.0, "speaker": "SPEAKER_00"},
            {"start": 3.0, "end": 6.0, "speaker": "SPEAKER_01"},
            {"start": 7.0, "end": 9.0, "speaker": "SPEAKER_01"},
        ],
        "exclusive_turns": [
            {"start": 0.0, "end": 3.0, "speaker": "SPEAKER_00"},
            {"start": 3.0, "end": 6.0, "speaker": "SPEAKER_01"},
            {"start": 7.0, "end": 9.0, "speaker": "SPEAKER_01"},
        ],
    }


def transcript_payload(segments: list[dict]) -> dict:
    return {
        "source": "whisper",
        "segments": segments,
        "full_text": " ".join(segment["text"] for segment in segments),
    }


def assert_schema_valid(payload: dict) -> None:
    errors = sorted(schema_validator().iter_errors(payload), key=lambda e: e.path)
    assert errors == []


def test_assigns_dominant_exclusive_speaker_without_changing_text():
    transcript = transcript_payload([
        {"text": "What are you doing here?", "start": 0.5, "duration": 2.0}
    ])

    result = attribute_speakers(transcript, diarization_payload())

    assert result is not None
    assert_schema_valid(result)
    segment = result["segments"][0]
    assert segment["text"] == "What are you doing here?"
    assert segment["speaker"] == "SPEAKER_00"
    assert segment["speaker_status"] == "assigned"
    assert segment["speaker_overlap_ratio"] == 1.0
    assert segment["overlapping_speech"] is False


def test_segment_crossing_boundary_marks_multiple_when_both_speakers_are_material():
    transcript = transcript_payload([
        {"text": "Boundary crossing line.", "start": 2.0, "duration": 2.0}
    ])

    result = attribute_speakers(transcript, diarization_payload())

    assert result is not None
    segment = result["segments"][0]
    assert segment["speaker"] == "SPEAKER_00"
    assert segment["speaker_status"] == "multiple"
    assert segment["speaker_candidates"] == [
        {"speaker": "SPEAKER_00", "overlap_seconds": 1.0, "overlap_ratio": 0.5},
        {"speaker": "SPEAKER_01", "overlap_seconds": 1.0, "overlap_ratio": 0.5},
    ]
    assert segment["overlapping_speech"] is True


def test_mixed_segment_when_two_speakers_exceed_mixed_ratio():
    transcript = transcript_payload([
        {"text": "Both speakers are in this cue.", "start": 2.6, "duration": 1.2}
    ])

    result = attribute_speakers(transcript, diarization_payload())

    assert result is not None
    segment = result["segments"][0]
    assert segment["speaker"] == "SPEAKER_01"
    assert segment["speaker_status"] == "multiple"
    assert segment["speaker_candidates"] == [
        {"speaker": "SPEAKER_01", "overlap_seconds": 0.8, "overlap_ratio": 0.667},
        {"speaker": "SPEAKER_00", "overlap_seconds": 0.4, "overlap_ratio": 0.333},
    ]
    assert segment["overlapping_speech"] is True
    assert result["mixed_count"] == 1


def test_unassigned_when_no_exclusive_overlap():
    transcript = transcript_payload([
        {"text": "No one is speaking here.", "start": 6.2, "duration": 0.5}
    ])

    result = attribute_speakers(transcript, diarization_payload())

    assert result is not None
    segment = result["segments"][0]
    assert segment["speaker"] is None
    assert segment["speaker_source"] == "none"
    assert segment["speaker_status"] == "unassigned"
    assert segment["speaker_candidates"] == []
    assert result["unassigned_count"] == 1


def test_zero_duration_caption_uses_point_membership():
    transcript = transcript_payload([
        {"text": "A zero-duration caption.", "start": 7.5, "duration": 0.0}
    ])

    result = attribute_speakers(transcript, diarization_payload())

    assert result is not None
    segment = result["segments"][0]
    assert segment["speaker"] == "SPEAKER_01"
    assert segment["speaker_status"] == "assigned"
    assert segment["speaker_overlap_seconds"] == 0.0
    assert segment["speaker_overlap_ratio"] == 1.0


def test_invalid_or_unavailable_inputs_return_none():
    transcript = transcript_payload([
        {"text": "Hello.", "start": 0.0, "duration": 1.0}
    ])

    assert attribute_speakers(None, diarization_payload()) is None
    assert attribute_speakers(transcript, None) is None
    assert attribute_speakers(transcript, {"schema": "watch.diarization.v1", "status": "unavailable"}) is None


def test_identity_boundary_never_promotes_anonymous_speaker_to_character():
    transcript = transcript_payload([
        {"text": "Marcus is mentioned in the text only.", "start": 0.5, "duration": 2.0}
    ])

    result = attribute_speakers(transcript, diarization_payload())

    assert result is not None
    assert result["identity_boundary"]["anonymous_speakers_are_identity"] is False
    assert result["identity_boundary"]["promotion_allowed"] is False
    assert result["segments"][0]["speaker"] == "SPEAKER_00"
    assert result["segments"][0]["text"] == "Marcus is mentioned in the text only."
