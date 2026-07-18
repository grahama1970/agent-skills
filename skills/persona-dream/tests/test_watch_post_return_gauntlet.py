"""Packet-shape and verdict-logic tests for the watch post-return gauntlet.

Pure logic only: no /watch, codex, ffmpeg, or memory-daemon calls. Frame files
are tiny fixtures written under tmp_path so the packet builder can hash them.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import watch_post_return_gauntlet as gauntlet  # noqa: E402


DURATION = 10.041667
# Uniform-fallback 12-frame timeline as watch actually produced on the historical return.
FRAME_TIMESTAMPS = [round(i * DURATION / 12, 6) for i in range(12)]
CANONICAL_LINE = "If we paddle now, we're cutting across the lineup."
IDENTITY_WINDOW = [0.0, 3.5]
SPEAKER_WINDOW = [5.0, 7.7]
FA_INTERVAL = [5.0, 7.7]


def _frames_manifest() -> dict[str, Any]:
    return {
        "sampling_mode": "uniform-fallback",
        "frame_count": len(FRAME_TIMESTAMPS),
        "duration_seconds": DURATION,
        "frames": [
            {"index": i, "timestamp_seconds": ts, "path": f"frames/frame_{i + 1:04d}.jpg"}
            for i, ts in enumerate(FRAME_TIMESTAMPS)
        ],
    }


def _transcript() -> dict[str, Any]:
    return {
        "source": "whisper-local (cpu)",
        "segments": [{"text": CANONICAL_LINE, "start": 4.72, "duration": 3.5}],
        "full_text": CANONICAL_LINE,
    }


def _frame_files(tmp_path: Path) -> dict[int, Path]:
    frames_dir = tmp_path / "watch" / "frames_bound"
    frames_dir.mkdir(parents=True, exist_ok=True)
    mapping: dict[int, Path] = {}
    for i in range(len(FRAME_TIMESTAMPS)):
        f = frames_dir / f"frame_{i:04d}.jpg"
        f.write_bytes(f"jpeg-bytes-{i}".encode())
        mapping[i] = f
    return mapping


def _watch_artifacts() -> dict[str, dict[str, Any]]:
    ref = {"path": "watch/x.json", "sha256": "sha256:" + "0" * 64, "size_bytes": 1}
    return {name: dict(ref) for name in ("frames_manifest", "transcript", "scenes", "report")}


def _build(tmp_path: Path, *, vision_review: dict[str, Any], report: dict[str, Any] | None = None):
    return gauntlet.build_observation_packet(
        packet_root=tmp_path,
        frames_manifest=_frames_manifest(),
        transcript=_transcript(),
        report=report or {"visual_descriptions": []},
        frame_files=_frame_files(tmp_path),
        watch_artifacts=_watch_artifacts(),
        source_video_basename="muxed_provider_return.mp4",
        source_video_sha256="sha256:" + "9" * 64,
        source_video_size_bytes=16957429,
        duration_seconds=DURATION,
        run_id="pipeline-complete",
        revision_id="rev_successor_943b01ecd9a3",
        source_revision_id="rev_upstream_bf3b05d47fb8",
        evidence_origin="historical_provider_return",
        requested_mode="scene-change",
        identity_window=IDENTITY_WINDOW,
        speaker_window=SPEAKER_WINDOW,
        speaker="Kai",
        identity_reference={"asset_id": "embry_contact_sheet_v3", "path": "/ref.png",
                            "sha256": "sha256:" + "3" * 64},
        vision_review=vision_review,
        observed_at="2026-07-18T00:00:00+00:00",
    )


DRIFT_REVIEW = {"status": "performed", "verdict": "DRIFT", "model": "gpt-5.3-codex"}
CONSISTENT_REVIEW = {"status": "performed", "verdict": "CONSISTENT", "model": "gpt-5.3-codex"}
DEGRADED_REVIEW = {"status": "not_performed", "reason": "codex unavailable", "verdict": "INDETERMINATE"}
GROUND_TRUTH = {
    "identity_window": IDENTITY_WINDOW,
    "speaker_window": SPEAKER_WINDOW,
    "canonical_line": CANONICAL_LINE,
    "forced_alignment_interval": FA_INTERVAL,
    "expected_vision_verdict": "DRIFT",
}


def test_packet_is_schema_valid(tmp_path):
    packet = _build(tmp_path, vision_review=DRIFT_REVIEW)
    assert gauntlet.validate_observation_packet(packet) == []
    assert packet["schema"] == gauntlet.PACKET_SCHEMA
    assert packet["psychological_interpretation_performed"] is False


def test_frames_localize_both_evidence_windows(tmp_path):
    packet = _build(tmp_path, vision_review=DRIFT_REVIEW)
    id_frames = packet["step_hooks"]["step_36_identity_temporal_continuity"]["identity_review_frames"]
    sp_frames = packet["step_hooks"]["step_38_visible_speaker_lipsync"]["speaker_visibility_frames"]
    # 0.0, 0.836, 1.673, 2.510, 3.347 fall inside [0.0, 3.5]
    assert [f["index"] for f in id_frames] == [0, 1, 2, 3, 4]
    # 5.020, 5.857, 6.694, 7.531 fall inside [5.0, 7.7]
    assert [f["index"] for f in sp_frames] == [6, 7, 8, 9]


def test_step_hooks_present_and_flagged(tmp_path):
    hooks = _build(tmp_path, vision_review=DRIFT_REVIEW)["step_hooks"]
    assert set(hooks) == {
        "step_35_frame_contact_sheet",
        "step_36_identity_temporal_continuity",
        "step_38_visible_speaker_lipsync",
    }
    assert len(hooks["step_35_frame_contact_sheet"]["frame_indices"]) == 12
    sp = hooks["step_38_visible_speaker_lipsync"]
    assert sp["speaker_visibility_flagged"] is True
    assert sp["transcript_line_at_interval"] == CANONICAL_LINE


def test_missing_vlm_recorded_as_coverage_gap(tmp_path):
    packet = _build(tmp_path, vision_review=DRIFT_REVIEW)
    assert any("per_frame_vlm_entities_unavailable" in g for g in packet["coverage_gaps"])
    assert packet["status"] == "DEGRADED_WATCH_GAUNTLET_OBSERVATION"


def test_observed_entities_used_when_descriptions_exist(tmp_path):
    report = {"visual_descriptions": [
        {"description": f"entity {i}", "status": "described"} for i in range(12)
    ]}
    packet = _build(tmp_path, vision_review=DRIFT_REVIEW, report=report)
    assert packet["frame_evidence"][0]["observed_entities"] == ["entity 0"]
    assert not any("per_frame_vlm" in g for g in packet["coverage_gaps"])


def test_evaluate_validation_all_pass_with_drift(tmp_path):
    packet = _build(tmp_path, vision_review=DRIFT_REVIEW)
    scored = gauntlet.evaluate_validation(packet, GROUND_TRUTH)
    assert scored["overall_status"] == "PASS_WATCH_GAUNTLET_VALIDATED"
    assert all(e["verdict"] == "VALIDATED" for e in scored["expectations"])


def test_evaluate_validation_fails_on_consistent_vision(tmp_path):
    packet = _build(tmp_path, vision_review=CONSISTENT_REVIEW)
    scored = gauntlet.evaluate_validation(packet, GROUND_TRUTH)
    assert scored["overall_status"] == "FAIL_WATCH_GAUNTLET_VALIDATION"
    vision_exp = next(e for e in scored["expectations"]
                      if e["id"] == "vision_corroborates_embry_identity_drift_00_03")
    assert vision_exp["verdict"] == "NOT_VALIDATED"


def test_evaluate_validation_degrades_when_vision_unavailable(tmp_path):
    packet = _build(tmp_path, vision_review=DEGRADED_REVIEW)
    scored = gauntlet.evaluate_validation(packet, GROUND_TRUTH)
    # Perception expectations still pass; only vision degrades (no hard fail).
    assert scored["overall_status"] == "PASS_WATCH_GAUNTLET_VALIDATED_WITH_DEGRADED_CAPABILITIES"
    vision_exp = next(e for e in scored["expectations"]
                      if e["id"] == "vision_corroborates_embry_identity_drift_00_03")
    assert vision_exp["verdict"] == "NOT_VALIDATED_DEGRADED"


@pytest.mark.parametrize("text,expected", [
    ("VERDICT: DRIFT\nreason", "DRIFT"),
    ("verdict: consistent\nreason", "CONSISTENT"),
    ("The identity clearly drifts here.", "DRIFT"),
    ("This looks consistent throughout.", "CONSISTENT"),
    ("no clear signal", "INDETERMINATE"),
])
def test_parse_vision_verdict(text, expected):
    assert gauntlet._parse_vision_verdict(text) == expected


def test_transcript_mismatch_fails_canonical_expectation(tmp_path):
    packet = _build(tmp_path, vision_review=DRIFT_REVIEW)
    packet["transcript_facts"] = [{
        "fact_id": "transcript_seg_000", "statement": "totally different words",
        "time_range": [4.72, 8.22], "evidence_refs": ["watch/transcript.json"], "confidence": 0.9,
    }]
    scored = gauntlet.evaluate_validation(packet, GROUND_TRUTH)
    canon = next(e for e in scored["expectations"] if e["id"] == "transcript_recovers_canonical_kai_line")
    assert canon["verdict"] == "NOT_VALIDATED"
